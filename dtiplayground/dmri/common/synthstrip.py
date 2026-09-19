#   SynthStrip brain extraction: FreeSurfer's mri_synthstrip when it is installed, otherwise the SynthStrip network run
#   in Python (torch) with the preprocessing of mri_synthstrip reimplemented with numpy/scipy/nibabel.
#
#   SynthStrip: Skull-Stripping for Any Brain Image. A Hoopes, JS Mora, AV Dalca, B Fischl, M Hoffmann.
#   NeuroImage 206 (2022), 119474. https://doi.org/10.1016/j.neuroimage.2022.119474  -  https://synthstrip.io
#
#   The model weights (synthstrip.1.pt, synthstrip.nocsf.1.pt) are downloaded from
#   https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/ (MIT or CC BY 4.0 license) unless FreeSurfer provides them.
#
#   All or portions of this licensed product (such portions are the "Software") have been obtained under license from
#   The General Hospital Corporation and are subject to the following terms and conditions: see
#   dtiplayground/dmri/common/LICENSE.freesurfer.txt (FreeSurfer Software License Agreement, Version 1.0). The network
#   (StripModel, ConvBlock) and the processing steps (conform, crop, reshape, normalization, extend_sdt, resampling,
#   largest connected component) are adapted from mri_synthstrip of FreeSurfer (python/scripts/mri_synthstrip) and the
#   surfa library; this is a modified version: the surfa image operations are reimplemented with numpy/scipy/nibabel.

import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

import numpy as np
import nibabel as nib
import scipy.ndimage

MODEL_URL = 'https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/requirements/{}'
MODEL_FILES = {False: 'synthstrip.1.pt', True: 'synthstrip.nocsf.1.pt'}  # keyed by no_csf


def find_mri_synthstrip(path=None):
    """Path of FreeSurfer's mri_synthstrip: *path* (the executable or a FreeSurfer home), $FREESURFER_HOME/bin, or the
    PATH; None if not found."""
    candidates = []
    if path:
        p = Path(str(path)).expanduser()
        candidates += [p, p.joinpath('bin', 'mri_synthstrip')]
    if os.environ.get('FREESURFER_HOME'):
        candidates.append(Path(os.environ['FREESURFER_HOME']).joinpath('bin', 'mri_synthstrip'))
    found = shutil.which('mri_synthstrip')
    if found:
        candidates.append(Path(found))
    for c in candidates:
        if c.is_file() and os.access(str(c), os.X_OK):
            return str(c)
    return None


def run_mri_synthstrip(executable, image_path, mask_path, border=1.0, no_csf=False, threads=None):
    """Brain mask of *image_path* with FreeSurfer's mri_synthstrip, written to *mask_path*."""
    env = dict(os.environ)
    fshome = Path(executable).resolve().parent.parent
    if not env.get('FREESURFER_HOME') or not Path(env['FREESURFER_HOME']).joinpath('bin', 'mri_synthstrip').exists():
        env['FREESURFER_HOME'] = str(fshome)  # mri_synthstrip needs it (python and model weights)
    command = [str(executable), '-i', str(image_path), '-m', str(mask_path), '-b', str(border)]
    if no_csf:
        command.append('--no-csf')
    if threads:
        command += ['-t', str(int(threads))]
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode != 0 or not Path(mask_path).exists():
        raise RuntimeError('mri_synthstrip failed ({}):\n{}{}'.format(' '.join(command), result.stdout, result.stderr))
    return command, result.stdout


def model_weights(no_csf=False, cache_dir=None):
    """Path of the SynthStrip weights: from $FREESURFER_HOME/models, else from *cache_dir* (default
    ~/.niral-dti/models/synthstrip), downloaded there on first use."""
    name = MODEL_FILES[bool(no_csf)]
    if os.environ.get('FREESURFER_HOME'):
        p = Path(os.environ['FREESURFER_HOME']).joinpath('models', name)
        if p.is_file():
            return str(p)
    cache = Path(cache_dir) if cache_dir else Path.home().joinpath('.niral-dti', 'models', 'synthstrip')
    target = cache.joinpath(name)
    if not target.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix('.download')
        with urllib.request.urlopen(MODEL_URL.format(name), timeout=120) as response, open(tmp, 'wb') as f:
            shutil.copyfileobj(response, f)
        if tmp.stat().st_size < 1000000:
            tmp.unlink()
            raise RuntimeError('download of the SynthStrip weights {} failed'.format(MODEL_URL.format(name)))
        tmp.rename(target)
    return str(target)


def _strip_model():
    import torch
    import torch.nn as nn

    class ConvBlock(nn.Module):
        def __init__(self, ndims, in_channels, out_channels, stride=1, activation='leaky'):
            super().__init__()
            Conv = getattr(nn, 'Conv%dd' % ndims)
            self.conv = Conv(in_channels, out_channels, 3, stride, 1)
            if activation == 'leaky':
                self.activation = nn.LeakyReLU(0.2)
            elif activation is None:
                self.activation = None
            else:
                raise ValueError(f'Unknown activation: {activation}')

        def forward(self, x):
            out = self.conv(x)
            if self.activation is not None:
                out = self.activation(out)
            return out

    class StripModel(nn.Module):
        def __init__(self, nb_features=16, nb_levels=7, feat_mult=2, max_features=64, nb_conv_per_level=2,
                     max_pool=2):
            super().__init__()
            ndims = 3
            feats = np.round(nb_features * feat_mult ** np.arange(nb_levels)).astype(int)
            feats = np.clip(feats, 1, max_features)
            enc_nf = np.repeat(feats[:-1], nb_conv_per_level)
            dec_nf = np.repeat(np.flip(feats), nb_conv_per_level)
            nb_dec_convs = len(enc_nf)
            final_convs = dec_nf[nb_dec_convs:]
            dec_nf = dec_nf[:nb_dec_convs]
            self.nb_levels = int(nb_dec_convs / nb_conv_per_level) + 1
            max_pool = [max_pool] * self.nb_levels
            MaxPooling = getattr(nn, 'MaxPool%dd' % ndims)
            self.pooling = [MaxPooling(s) for s in max_pool]
            self.upsampling = [nn.Upsample(scale_factor=s, mode='nearest') for s in max_pool]
            prev_nf = 1
            encoder_nfs = [prev_nf]
            self.encoder = nn.ModuleList()
            for level in range(self.nb_levels - 1):
                convs = nn.ModuleList()
                for conv in range(nb_conv_per_level):
                    nf = enc_nf[level * nb_conv_per_level + conv]
                    convs.append(ConvBlock(ndims, prev_nf, nf))
                    prev_nf = nf
                self.encoder.append(convs)
                encoder_nfs.append(prev_nf)
            encoder_nfs = np.flip(encoder_nfs)
            self.decoder = nn.ModuleList()
            for level in range(self.nb_levels - 1):
                convs = nn.ModuleList()
                for conv in range(nb_conv_per_level):
                    nf = dec_nf[level * nb_conv_per_level + conv]
                    convs.append(ConvBlock(ndims, prev_nf, nf))
                    prev_nf = nf
                self.decoder.append(convs)
                if level < (self.nb_levels - 1):
                    prev_nf += encoder_nfs[level]
            self.remaining = nn.ModuleList()
            for num, nf in enumerate(final_convs):
                self.remaining.append(ConvBlock(ndims, prev_nf, nf))
                prev_nf = nf
            self.remaining.append(ConvBlock(ndims, prev_nf, 1, activation=None))

        def forward(self, x):
            x_history = [x]
            for level, convs in enumerate(self.encoder):
                for conv in convs:
                    x = conv(x)
                x_history.append(x)
                x = self.pooling[level](x)
            for level, convs in enumerate(self.decoder):
                for conv in convs:
                    x = conv(x)
                if level < (self.nb_levels - 1):
                    x = self.upsampling[level](x)
                    x = torch.cat([x, x_history.pop()], dim=1)
            for conv in self.remaining:
                x = conv(x)
            return x

    return StripModel()


## image geometry as in surfa: the world center of a grid is vox2world @ (shape / 2)
def _center(affine, shape):
    return (affine @ np.append(np.asarray(shape, dtype=np.float64) / 2, 1))[:3]


def _interpolate(source, vox2vox, target_shape, method, fill=0.0):
    """Resample *source* onto a grid of *target_shape*, *vox2vox* mapping target to source voxel coordinates, with
    the conventions of surfa's interpolate: float32 coordinates, nearest rounds half away from zero within [0, n),
    linear needs floor(coordinate) within [0, n-1] (the upper neighbour clamped), *fill* outside."""
    m = np.asarray(vox2vox, dtype=np.float32)
    x, y, z = [a.astype(np.float32) for a in np.indices(tuple(target_shape), dtype=np.int64)]
    s = [m[i, 0] * x + m[i, 1] * y + m[i, 2] * z + m[i, 3] for i in range(3)]
    n = source.shape
    out = np.full(tuple(target_shape), fill, dtype=np.float32)
    if method == 'nearest':
        valid = (s[0] >= 0) & (s[0] < n[0]) & (s[1] >= 0) & (s[1] < n[1]) & (s[2] >= 0) & (s[2] < n[2])
        idx = [np.minimum(np.floor(c[valid] + np.float32(0.5)).astype(np.int64), d - 1) for c, d in zip(s, n)]
        out[valid] = source[idx[0], idx[1], idx[2]]
        return out
    low = [np.floor(c).astype(np.int64) for c in s]
    valid = np.ones(tuple(target_shape), dtype=bool)
    for l, d in zip(low, n):
        valid &= (l >= 0) & (l <= d - 1)
    lo = [l[valid] for l in low]
    hi = [np.where(l == d - 1, l, l + 1) for l, d in zip(lo, n)]
    t = [c[valid] - l.astype(np.float32) for c, l in zip(s, lo)]
    d = [np.float32(1) - v for v in t]
    src = source.astype(np.float32)
    v = (d[0] * d[1] * d[2] * src[lo[0], lo[1], lo[2]] + t[0] * d[1] * d[2] * src[hi[0], lo[1], lo[2]] +
         d[0] * t[1] * d[2] * src[lo[0], hi[1], lo[2]] + d[0] * d[1] * t[2] * src[lo[0], lo[1], hi[2]] +
         t[0] * d[1] * t[2] * src[hi[0], lo[1], hi[2]] + d[0] * t[1] * t[2] * src[lo[0], hi[1], hi[2]] +
         t[0] * t[1] * d[2] * src[hi[0], hi[1], lo[2]] + t[0] * t[1] * t[2] * src[hi[0], hi[1], hi[2]])
    out[valid] = v
    return out


def _conform(data, affine, zooms):
    """Reorient to LIA and resample to 1 mm (nearest neighbour) about the same world center, as surfa's
    conform(voxsize=1.0, orientation='LIA', method='nearest'); the voxel size is that of the header (*zooms*)."""
    ornt = nib.orientations.ornt_transform(nib.orientations.io_orientation(affine),
                                           nib.orientations.axcodes2ornt(('L', 'I', 'A')))
    affine = affine @ nib.orientations.inv_ornt_aff(ornt, data.shape)
    data = nib.orientations.apply_orientation(data, ornt)
    voxsize = np.zeros(3)
    for axis, (new_axis, _) in enumerate(ornt):
        voxsize[int(new_axis)] = zooms[axis]
    if np.allclose(voxsize, 1.0, atol=1e-5, rtol=0):
        return data.astype(np.float32), affine
    shape = tuple(np.ceil(voxsize * np.asarray(data.shape) / 1.0).astype(int))
    ## rotation and center as surfa's decompose_centered_affine, target grid as its compose_centered_affine
    q, r = np.linalg.qr(affine[:3, :3])
    di = np.diag_indices(3)
    p = np.eye(3)
    p[di] = r[di] / np.abs(r[di])
    rotation = q @ p
    target = np.eye(4)
    target[:3, :3] = rotation @ (np.diag(np.ones(3)) @ np.eye(3))
    offset = target @ np.append(np.asarray(shape) / 2, 1)
    target[:3, 3] = _center(affine, data.shape) - offset[:3]
    return _interpolate(data, np.linalg.inv(affine) @ target, shape, 'nearest'), target


def _crop_to_bbox(data, affine):
    mask = data > 0
    if not np.any(mask):
        return data, affine
    box = scipy.ndimage.find_objects(mask.astype(np.int8))[0]
    start = np.array([s.start for s in box], dtype=np.float64)
    out = affine.copy()
    out[:3, 3] = affine[:3, :3] @ start + affine[:3, 3]
    return data[box], out


def _reshape(data, affine, shape):
    """Pad/crop to *shape* keeping the image centered, as surfa's reshape(center='image')."""
    shape = tuple(int(s) for s in shape)
    if tuple(data.shape) == shape:
        return data, affine
    delta = (np.array(shape) - np.array(data.shape)) / 2
    low = np.floor(delta).astype(int)
    high = np.ceil(delta).astype(int)
    padding = list(zip(np.clip(low, 0, None), np.clip(high, 0, None)))
    padded = np.pad(data, padding, mode='constant')
    c_low = np.clip(-high, 0, None)
    c_high = np.array(padded.shape) - np.clip(-low, 0, None)
    out = padded[tuple(slice(a, b) for a, b in zip(c_low, c_high))]
    matrix = np.eye(4)
    matrix[:3, :3] = affine[:3, :3]
    p0crs = np.clip(-high, 0, None) - np.clip(low, 0, None)
    matrix[:3, 3] = (affine @ np.append(p0crs, 1))[:3]
    pcrs = np.append(np.array(out.shape) / 2, 1)
    cras = (matrix @ pcrs)[:3]
    matrix[:3, 3] = 0
    matrix[:3, 3] = cras - (matrix @ pcrs)[:3]
    return out, matrix


def _extend_sdt(sdt, border=1.0):
    """Recompute the outer part of SynthStrip's narrow-band signed distance transform for borders beyond the band."""
    if border < int(sdt.max()):
        return sdt
    mask = sdt < 1
    keep = np.nonzero(mask)
    low = np.min(keep, axis=-1)
    upp = np.max(keep, axis=-1)
    gap = int(border + 0.5)
    low = [max(i - gap, 0) for i in low]
    upp = [min(i + gap, d - 1) for i, d in zip(upp, mask.shape)]
    ind = tuple(slice(a, b + 1) for a, b in zip(low, upp))
    out = np.full_like(sdt, fill_value=100)
    out[ind] = scipy.ndimage.distance_transform_edt(1 - mask[ind])  # 1 mm voxels
    out[keep] = sdt[keep]
    return out


def _resample_like(data, affine, target_affine, target_shape, fill=100.0):
    """Linear resampling of *data* (grid *affine*) onto the target grid, *fill* outside."""
    return _interpolate(data, np.linalg.inv(affine) @ target_affine, target_shape, 'linear', fill)


def run_builtin(image_path, mask_path, border=1.0, no_csf=False, threads=None, model_file=None):
    """Brain mask of the 3D image *image_path* (NIfTI) with the SynthStrip network, written to *mask_path* (NIfTI,
    uint8, same grid)."""
    import torch
    if threads:
        torch.set_num_threads(int(threads))
    image = nib.load(str(image_path))
    data = np.asanyarray(image.dataobj, dtype=np.float32)
    if data.ndim == 4 and data.shape[3] == 1:
        data = data[..., 0]
    if data.ndim != 3:
        raise ValueError('SynthStrip needs a 3D image, got shape {}'.format(data.shape))
    affine = image.affine.astype(np.float64)

    conformed, c_affine = _conform(data, affine, np.asarray(image.header.get_zooms()[:3], dtype=np.float64))
    conformed, c_affine = _crop_to_bbox(conformed, c_affine)
    target_shape = np.clip(np.ceil(np.array(conformed.shape[:3]) / 64).astype(int) * 64, 192, 320)
    conformed, c_affine = _reshape(conformed, c_affine, target_shape)
    conformed = conformed - conformed.min()
    conformed = np.clip(conformed / np.percentile(conformed, 99), 0, 1).astype(np.float32)

    model = _strip_model()
    checkpoint = torch.load(model_file or model_weights(no_csf), map_location=torch.device('cpu'))
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    with torch.no_grad():
        sdt = model(torch.from_numpy(conformed[np.newaxis, np.newaxis])).squeeze().cpu().numpy()

    sdt = _extend_sdt(sdt, border=border)
    sdt = _resample_like(sdt, c_affine, affine, data.shape, fill=100.0)
    labels, n = scipy.ndimage.label(sdt < border)
    if n == 0:
        raise RuntimeError('SynthStrip found no brain in {}'.format(image_path))
    largest = np.argmax(np.bincount(labels.flat)[1:]) + 1
    mask = scipy.ndimage.binary_fill_holes(labels == largest)
    nib.save(nib.Nifti1Image(mask.astype(np.uint8), affine), str(mask_path))
    return mask
