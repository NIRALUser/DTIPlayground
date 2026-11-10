#
#   common/tensor_registration.py
#
#   Diffeomorphic registration of a diffusion tensor image to a reference tensor (atlas or age bin mean tensor of a
#   normative model), optionally with a free water term (multi-shell data with a free water fraction map), in PyTorch
#   (GPU when available, CPU otherwise).
#
#   The DTI is first resampled through the initial affine transform onto the grid of the reference
#   (ResampleDTIlogEuclidean). The deformation x -> x + u(x) is the exponential of a stationary velocity field v
#   (scaling and squaring; v on a half resolution grid, Gaussian smoothed), optimised with Adam over 3 resolutions.
#   The moved tensor at x is R^T L_s(x + u) R, with L the matrix logarithm of the tensor and R the rotation of the polar
#   decomposition of J = I + grad u (finite strain reorientation). Loss over the reference brain mask:
#
#     |dev L'/|dev L'| - dev L_r/|dev L_r||^2 |dev L_r|^2      orientation and shape of the tensors (normalised
#                                                               deviatoric part), weighted by the reference anisotropy
#   + w_fw (C_s(x + u) - C_r(x))^2                              free water fraction (subject map, reference mean map)
#   + w_reg |grad v|^2
#
#   The normalised deviatoric term makes the match independent of the anisotropy differences between the subject and
#   the reference (age, resolution); the free water term aligns the ventricles. Evaluated on 139 scans of 4 studies
#   (0-12 years) against DTI-Reg (ANTS on FA) and DTI-TK: white matter principal direction angle 7.2 deg vs 10.5 deg
#   (DTI-Reg) and 8.0 deg (DTI-TK), ventricle overlap (Dice) with the free water term 0.81 vs 0.70.
#
#   The total transform aff(x + u(x)) is written as a displacement field on the reference grid (for every reference
#   position, the displacement to the corresponding position in the DTI, as DTI-Reg writes it), its inverse on the grid
#   of the DTI, and the DTI is resampled once with ResampleDTIlogEuclidean through the total field.
#

import json
import subprocess
import time
from pathlib import Path

import numpy as np

DEFAULTS = dict(w_fw=1.0, w_reg=0.15, smooth=0.5, levels=(4, 2, 1), iters=(200, 150, 100), lr=0.5, steps=7, vstride=2)
BACKGROUND_MD = 0.02  # isotropic tensor (1e-3 mm^2/s) of the background: no deviatoric part


def _torch():
    import torch
    import torch.nn.functional as F
    return torch, F


def read_tensor_nrrd(path):
    """Physical (LPS) tensors (X,Y,Z,3,3) in 1e-3 mm^2/s of a tensor NRRD, and the sitk image of its grid."""
    import nrrd
    import SimpleITK as sitk
    from dtiplayground.dmri.fiberprofile.analysis.detect_flip import header_frames
    from dtiplayground.dmri.fiberprofile.analysis.flip_tensor import COMPONENTS, tensor_axis
    data, header = nrrd.read(str(path))
    ax, kind = tensor_axis(data, header)
    data = np.moveaxis(np.asarray(data, dtype=np.float64), ax, -1)
    T = np.zeros(data.shape[:3] + (3, 3))
    for c, ij in enumerate(COMPONENTS[kind]):
        if ij is not None:
            T[..., ij[0], ij[1]] = data[..., c]
            T[..., ij[1], ij[0]] = data[..., c]
    frame, _, directions, origin = header_frames(header)
    T = frame @ T @ frame.T
    md = np.trace(T, axis1=-2, axis2=-1) / 3
    nz = md[np.abs(T).sum((-1, -2)) > 0]
    if nz.size and np.median(np.abs(nz)) < 0.1:  # mm^2/s -> 1e-3 mm^2/s
        T = T * 1000.0
    spacing = np.linalg.norm(directions, axis=0)
    grid = sitk.Image([int(s) for s in T.shape[:3]], sitk.sitkFloat32)
    grid.SetSpacing([float(s) for s in spacing])
    grid.SetOrigin([float(o) for o in origin])
    grid.SetDirection([float(d) for d in (directions / spacing).ravel()])
    return T, grid


def logm(T, floor=BACKGROUND_MD):
    w, v = np.linalg.eigh(T)
    return (v * np.log(np.clip(w, floor, None))[..., None, :]) @ np.swapaxes(v, -1, -2)


def fa_of(T):
    w = np.clip(np.linalg.eigvalsh(T), 0, None)
    md = w.mean(-1, keepdims=True)
    with np.errstate(invalid='ignore', divide='ignore'):
        fa = np.sqrt(1.5 * ((w - md) ** 2).sum(-1) / (w ** 2).sum(-1))
    return np.nan_to_num(fa)


def to_array(img):
    """sitk image -> (X,Y,Z[,C]) array."""
    import SimpleITK as sitk
    a = sitk.GetArrayFromImage(img)
    return (a.transpose(2, 1, 0) if a.ndim == 3 else a.transpose(2, 1, 0, 3)).astype(np.float32)


def _to_t(a, dev):
    """(X,Y,Z[,C]) -> (1,C,Z,Y,X) float tensor (torch order D,H,W = z,y,x)."""
    torch, _ = _torch()
    a = np.asarray(a, np.float32)
    a = a.reshape(a.shape[:3] + (-1,))
    return torch.from_numpy(np.ascontiguousarray(a.transpose(3, 2, 1, 0)))[None].to(dev)


def _grid_identity(shape, dev):
    """Voxel coordinates (1,3,D,H,W), channel order (x,y,z)."""
    torch, _ = _torch()
    zz, yy, xx = torch.meshgrid(*[torch.arange(s, device=dev, dtype=torch.float32) for s in shape], indexing='ij')
    return torch.stack([xx, yy, zz])[None]


def _sample(img, disp, ident):
    """img(x + disp) in voxel units; img (1,C,D,H,W), disp (1,3,D,H,W) (x,y,z)."""
    torch, F = _torch()
    D, H, W = img.shape[2:]
    p = ident + disp
    norm = torch.stack([2 * p[:, 0] / (W - 1) - 1, 2 * p[:, 1] / (H - 1) - 1, 2 * p[:, 2] / (D - 1) - 1], -1)
    return F.grid_sample(img, norm, mode='bilinear', padding_mode='border', align_corners=True)


def _expv(v, steps, ident):
    u = v / (2 ** steps)
    for _ in range(steps):
        u = u + _sample(u, u, ident)
    return u


def _gauss(x, sigma):
    torch, F = _torch()
    if sigma <= 0:
        return x
    r = int(np.ceil(2.5 * sigma))
    k = torch.exp(-torch.arange(-r, r + 1, device=x.device, dtype=x.dtype) ** 2 / (2 * sigma ** 2))
    k = k / k.sum()
    C = x.shape[1]
    for dim in range(3):
        shape = [1, 1, 1, 1, 1]
        shape[2 + dim] = len(k)
        w = k.view(shape).repeat(C, 1, 1, 1, 1)
        pad = [0] * 6
        pad[2 * (2 - dim)] = pad[2 * (2 - dim) + 1] = r
        x = F.conv3d(F.pad(x, pad, mode='replicate'), w, groups=C)
    return x


def _jac(u):
    """J = I + grad u in voxel coordinates, (D,H,W,3,3), J[i,j] = d(x_i + u_i)/d x_j (x,y,z order)."""
    torch, _ = _torch()
    g = [torch.gradient(u[0], dim=d)[0] for d in (3, 2, 1)]  # d/dx (W), d/dy (H), d/dz (D)
    return torch.stack(g, -1).permute(1, 2, 3, 0, 4) + torch.eye(3, device=u.device)


def _inv_t(M):
    """Batched 3x3 inverse transpose (cofactor matrix / determinant)."""
    torch, _ = _torch()
    a, b, c = M[..., 0, 0], M[..., 0, 1], M[..., 0, 2]
    d, e, f = M[..., 1, 0], M[..., 1, 1], M[..., 1, 2]
    g, h, i = M[..., 2, 0], M[..., 2, 1], M[..., 2, 2]
    cof = torch.stack([torch.stack([e * i - f * h, f * g - d * i, d * h - e * g], -1),
                       torch.stack([c * h - b * i, a * i - c * g, b * g - a * h], -1),
                       torch.stack([b * f - c * e, c * d - a * f, a * e - b * d], -1)], -2)
    det = a * cof[..., 0, 0] + b * cof[..., 0, 1] + c * cof[..., 0, 2]
    det = torch.where(det.abs() < 1e-6, torch.full_like(det, 1e-6), det)
    return cof / det[..., None, None]


def _polar_rot(Jm, n=5):
    """Rotation of the polar decomposition J = R S (Higham iteration; J near the identity)."""
    R = Jm
    for _ in range(n):
        R = 0.5 * (R + _inv_t(R))
    return R


def _sym(L):
    """(1,6,D,H,W) -> (D,H,W,3,3)."""
    torch, _ = _torch()
    xx, xy, xz, yy, yz, zz = L[0]
    return torch.stack([torch.stack([xx, xy, xz], -1), torch.stack([xy, yy, yz], -1),
                        torch.stack([xz, yz, zz], -1)], -2)


def _six(L):
    return np.stack([L[..., 0, 0], L[..., 0, 1], L[..., 0, 2], L[..., 1, 1], L[..., 1, 2], L[..., 2, 2]], -1)


def resolve_device(device='auto'):
    torch, _ = _torch()
    device = str(device or 'auto').strip().lower()
    if device == 'auto':
        return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if device.startswith('cuda') and not torch.cuda.is_available():
        raise RuntimeError("device {} requested but CUDA is not available".format(device))
    return torch.device(device)


def register_arrays(Lr, Ls, mask, grid_matrix, params, device, fw_ref=None, fw_sub=None, log=None):
    """Optimise the stationary velocity field. Lr, Ls: (X,Y,Z,3,3) log tensors of the reference and of the affinely
    resampled subject (physical frame), mask (X,Y,Z), grid_matrix: direction @ diag(spacing) of the grid (voxel ->
    physical). Returns (u, u_inverse), each (X,Y,Z,3) in voxels (x,y,z)."""
    torch, F = _torch()
    p = dict(DEFAULTS, **params)
    use_fw = bool(p['w_fw']) and fw_ref is not None and fw_sub is not None
    shape = Lr.shape[:3]
    arrays = dict(Lr=_six(Lr), Ls=_six(Ls), mask=mask)
    if use_fw:
        arrays.update(fwr=fw_ref, fws=fw_sub)
    tt = {k: _to_t(a, device) for k, a in arrays.items()}
    Dm = torch.tensor(np.asarray(grid_matrix, np.float32), device=device)
    Dinv = torch.linalg.inv(Dm)
    eye = torch.eye(3, device=device)
    v, v_scale = None, 1
    for lev, iters in zip(p['levels'], p['iters']):
        size = [int(np.ceil(s / lev)) for s in shape[::-1]]  # D,H,W
        rs = (lambda x: F.interpolate(x, size=size, mode='trilinear', align_corners=True)) if lev > 1 else (lambda x: x)
        A = {k: rs(x) for k, x in tt.items()}
        mm = (A['mask'] > 0.5).float()[0, 0]
        n = mm.sum().clamp(min=1)
        ident = _grid_identity(size, device)
        vsize = [int(np.ceil(s / p['vstride'])) for s in size]
        if v is None:
            vp = torch.zeros((1, 3) + tuple(vsize), device=device)
        else:
            vp = F.interpolate(v.detach(), size=vsize, mode='trilinear', align_corners=True) * (v_scale / lev)
        v_scale = lev
        vp.requires_grad_(True)
        opt = torch.optim.Adam([vp], lr=p['lr'] / lev)
        Lrm = _sym(A['Lr'])
        dev_r = Lrm - Lrm.diagonal(dim1=-2, dim2=-1).sum(-1)[..., None, None] / 3 * eye
        nr = dev_r.square().sum((-1, -2)).add(1e-8).sqrt()
        dev_r_unit = dev_r / nr[..., None, None]
        # voxel -> physical Jacobian at this level: the coarse voxel is lev voxels of the full grid
        Dl, Dli = Dm * lev, Dinv / lev
        for it in range(iters):
            opt.zero_grad()
            vf = _gauss(F.interpolate(vp, size=size, mode='trilinear', align_corners=True), p['smooth'])
            u = _expv(vf, p['steps'], ident)
            Lw = _sym(_sample(A['Ls'], u, ident))
            Jp = Dl @ _jac(u) @ Dli  # physical frame
            R = _polar_rot(Jp)
            Lm = R.transpose(-1, -2) @ Lw @ R
            dv = Lm - Lm.diagonal(dim1=-2, dim2=-1).sum(-1)[..., None, None] / 3 * eye
            ns = dv.square().sum((-1, -2)).add(1e-8).sqrt()
            diff = (dv / ns[..., None, None] - dev_r_unit).square().sum((-1, -2))
            loss = (diff * nr.square() * mm).sum() / n
            if use_fw:
                fw = _sample(A['fws'], u, ident)
                loss = loss + p['w_fw'] * (((fw - A['fwr']) ** 2)[0, 0] * mm).sum() / n
            loss = loss + p['w_reg'] * sum(((vp.diff(dim=d)) ** 2).mean() for d in (2, 3, 4))
            loss.backward()
            opt.step()
        if log is not None:
            log("  level 1/{}: {} iterations, loss {:.4f}".format(lev, iters, float(loss.detach())))
        v = _gauss(F.interpolate(vp.detach(), size=size, mode='trilinear', align_corners=True), p['smooth'])
    ident = _grid_identity(list(shape[::-1]), device)
    with torch.no_grad():
        u = _expv(v, p['steps'], ident)
        ui = _expv(-v, p['steps'], ident)
    out = lambda x: x[0].permute(3, 2, 1, 0).cpu().numpy().astype(np.float64)
    return out(u), out(ui)


def register(reference_tensor, moving_tensor, affine_file, output_dir, resample_path, *, reference_fa=None,
             reference_fw=None, moving_fw=None, params=None, device='auto', threads=None, correction='abs', log=print):
    """Register moving_tensor (NRRD) to reference_tensor (NRRD) after affine_file (ITK transform, fixed = reference,
    moving = DTI). reference_fw / moving_fw: free water fraction images (reference mean map on the reference grid, map
    of the DTI on its grid) for the free water term (params w_fw), reference_fa: FA of the reference for the brain mask
    (default: FA of the reference tensor). Writes displacementField.nrrd (reference grid), inverse_displacementField.nrrd
    (grid of the DTI) and registered_dti.nrrd to output_dir; returns their paths and a summary."""
    import SimpleITK as sitk
    from scipy import ndimage
    torch, _ = _torch()
    t0 = time.time()
    p = dict(DEFAULTS, **(params or {}))
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dev = resolve_device(device)
    if dev.type == 'cpu' and threads:
        torch.set_num_threads(int(threads))
    log("Tensor registration on {} ({})".format(dev, 'tensor + free water' if (p['w_fw'] and moving_fw) else 'tensor only'))

    def run(cmd):
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("{} failed:\n{}{}".format(Path(str(cmd[0])).name, r.stdout[-2000:], r.stderr[-2000:]))

    Tr, grid = read_tensor_nrrd(reference_tensor)
    Lr = logm(np.where((np.abs(Tr).sum((-1, -2)) == 0)[..., None, None], np.eye(3) * BACKGROUND_MD, Tr))
    if reference_fa is not None:
        fa_r = to_array(sitk.Resample(sitk.ReadImage(str(reference_fa), sitk.sitkFloat32), grid, sitk.Transform(),
                                      sitk.sitkLinear, 0.0))
    else:
        fa_r = fa_of(Tr)
    ball = np.sum(np.mgrid[-3:4, -3:4, -3:4] ** 2, 0) <= 9  # radius 3 voxels
    mask = ndimage.binary_dilation(fa_r > 0.05, structure=ball).astype(np.float32)

    affine_dti = out / 'tensorreg_affine_dti.nrrd'
    cmd = [resample_path, moving_tensor, affine_dti, '-R', reference_tensor, '--correction', correction]
    if affine_file is not None:
        cmd += ['-f', affine_file]
    run(cmd)
    Ts, _ = read_tensor_nrrd(affine_dti)
    affine_dti.unlink()
    bg = np.abs(Ts).sum((-1, -2)) == 0
    Ts[bg] = np.eye(3) * BACKGROUND_MD
    Ls = logm(Ts)
    aff = sitk.ReadTransform(str(affine_file)) if affine_file is not None else sitk.AffineTransform(3)

    fw_r = fw_s = None
    if p['w_fw'] and reference_fw is not None and moving_fw is not None:
        fw_r = to_array(sitk.Resample(sitk.ReadImage(str(reference_fw), sitk.sitkFloat32), grid, sitk.Transform(),
                                      sitk.sitkLinear, 0.0))
        fw_s = to_array(sitk.Resample(sitk.ReadImage(str(moving_fw), sitk.sitkFloat32), grid, aff, sitk.sitkLinear, 0.0))

    gm = np.array(grid.GetDirection()).reshape(3, 3) @ np.diag(grid.GetSpacing())
    t1 = time.time()
    u, ui = register_arrays(Lr, Ls, mask, gm, p, dev, fw_r, fw_s, log=log)
    t2 = time.time()

    def field_image(a, ref):  # voxel displacements -> physical
        img = sitk.GetImageFromArray(np.ascontiguousarray((a @ gm.T).transpose(2, 1, 0, 3)), isVector=True)
        img.CopyInformation(ref)
        return sitk.DisplacementFieldTransform(img)

    total = sitk.CompositeTransform([aff, field_image(u, grid)])  # x -> aff(x + u(x))
    field = sitk.TransformToDisplacementField(total, sitk.sitkVectorFloat64, grid.GetSize(), grid.GetOrigin(),
                                              grid.GetSpacing(), grid.GetDirection())
    field_path = out / 'displacementField.nrrd'
    sitk.WriteImage(sitk.Cast(field, sitk.sitkVectorFloat32), str(field_path), True)
    _, moving_grid = read_tensor_nrrd(moving_tensor)
    inverse = sitk.CompositeTransform([field_image(ui, grid), aff.GetInverse()])  # y -> phi^-1(aff^-1(y))
    ifield = sitk.TransformToDisplacementField(inverse, sitk.sitkVectorFloat64, moving_grid.GetSize(),
                                               moving_grid.GetOrigin(), moving_grid.GetSpacing(),
                                               moving_grid.GetDirection())
    ifield_path = out / 'inverse_displacementField.nrrd'
    sitk.WriteImage(sitk.Cast(ifield, sitk.sitkVectorFloat32), str(ifield_path), True)
    registered = out / 'registered_dti.nrrd'
    run([resample_path, moving_tensor, registered, '-R', reference_tensor, '--correction', correction,
         '--defField', field_path, '--hfieldtype', 'displacement'])

    J = np.linalg.det(np.stack(np.gradient(u, axis=(0, 1, 2)), -1) + np.eye(3))[mask > 0]
    summary = dict(device=str(dev), free_water=fw_r is not None, params={k: list(v) if isinstance(v, tuple) else v
                                                                         for k, v in p.items()},
                   jacobian_min=float(J.min()), jacobian_nonpositive=int((J <= 0).sum()),
                   seconds=time.time() - t0, optimisation_seconds=t2 - t1)
    json.dump(summary, open(out / 'tensor_registration.json', 'w'), indent=1)
    log("Tensor registration done in {:.0f} s (optimisation {:.0f} s), Jacobian min {:.2f}".format(
        summary['seconds'], summary['optimisation_seconds'], summary['jacobian_min']))
    return dict(displacement_field=str(field_path), inverse_displacement_field=str(ifield_path),
                registered_dti=str(registered), summary=summary)
