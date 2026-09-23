#   Quality metrics of the preprocessed DWI (per volume tables and one-row summaries)
#
#   eddy_motion   : head motion from eddy (framewise displacement, translations/rotations) and its outlier slices
#   eddy_cnr      : b=0 SNR and CNR per shell from the eddy --cnr_maps output, mean inside the eddy mask
#   tensor_fit    : agreement of each volume (and each slice) with the signal predicted by a WLS tensor fit
#   image_qc      : neighboring DWI correlation, bad slices and the b-table fiber coherence index of one image,
#                   computed on the raw input and on the preprocessed output so the two can be compared
#
#   Units: translations in mm, rotations in degrees, framewise displacement in mm (Power et al. 2012, head radius
#   50 mm; the rotations in radians times the radius).

import csv
from pathlib import Path

import numpy as np

HEAD_RADIUS = 50.0 # mm, framewise displacement


def write_tsv(path, rows, columns=None):
    columns = columns or (list(rows[0].keys()) if rows else [])
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, dialect='excel-tab', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    return path


def read_tsv(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f, dialect='excel-tab'))


def _round(x, digits=4):
    return None if x is None or not np.isfinite(x) else round(float(x), digits)


def shells(bvals, b0_threshold=50, b_range=50):
    """Shell b-values (rounded means) of the b-values above b0_threshold; values within b_range of each other form a shell."""
    values = sorted(float(b) for b in bvals if b > b0_threshold)
    groups = []
    for b in values:
        if groups and b - groups[-1][-1] <= b_range:
            groups[-1].append(b)
        else:
            groups.append([b])
    return [int(round(np.mean(g))) for g in groups]


def shell_of(bvals, shell_values, b0_threshold=50):
    """Shell b-value of each volume (0 for the b=0 volumes)."""
    out = []
    for b in bvals:
        if b <= b0_threshold or not shell_values:
            out.append(0)
        else:
            out.append(min(shell_values, key=lambda s: abs(s - b)))
    return out


### eddy

def eddy_arguments(eddy_base):
    """--name=value arguments of the eddy command (from <base>.eddy_command_txt)."""
    path = Path(str(eddy_base) + '.eddy_command_txt')
    args = {}
    if path.is_file():
        for token in path.read_text().split():
            if token.startswith('--') and '=' in token:
                k, v = token[2:].split('=', 1)
                args[k] = v
    return args


def eddy_motion(eddy_base, bvals, original_indexes=None):
    """Per volume motion rows and summary from <base>.eddy_parameters (movement relative to the first volume),
    <base>.eddy_movement_rms and <base>.eddy_outlier_map (only with --repol). None if eddy_parameters is missing."""
    par_path = Path(str(eddy_base) + '.eddy_parameters')
    if not par_path.is_file():
        return None, None
    par = np.atleast_2d(np.loadtxt(par_path))
    trans, rot = par[:, 0:3], par[:, 3:6] # mm, radians
    n = par.shape[0]
    delta_t = np.vstack([np.zeros((1, 3)), np.diff(trans, axis=0)])
    delta_r = np.vstack([np.zeros((1, 3)), np.diff(rot, axis=0)])
    fd = np.abs(delta_t).sum(axis=1) + HEAD_RADIUS * np.abs(delta_r).sum(axis=1)
    rms_path = Path(str(eddy_base) + '.eddy_movement_rms')
    rms = np.atleast_2d(np.loadtxt(rms_path)) if rms_path.is_file() else np.full((n, 2), np.nan)
    outliers = None
    map_path = Path(str(eddy_base) + '.eddy_outlier_map')
    if map_path.is_file():
        lines = [l for l in map_path.read_text().splitlines()[1:] if l.strip()]
        outliers = np.array([[int(x) for x in l.split()] for l in lines])
    if original_indexes is None or len(original_indexes) != n:
        original_indexes = list(range(n))
    rows = []
    for i in range(n):
        rows.append({'volume': i, 'original_index': original_indexes[i],
                     'bval': int(round(float(bvals[i]))) if i < len(bvals) else '',
                     'trans_x': _round(trans[i, 0]), 'trans_y': _round(trans[i, 1]), 'trans_z': _round(trans[i, 2]),
                     'rot_x': _round(np.degrees(rot[i, 0])), 'rot_y': _round(np.degrees(rot[i, 1])),
                     'rot_z': _round(np.degrees(rot[i, 2])),
                     'framewise_displacement': _round(fd[i]),
                     'rms_relative_to_first': _round(rms[i, 0]), 'rms_relative_to_previous': _round(rms[i, 1]),
                     'outlier_slices': int(outliers[i].sum()) if outliers is not None and i < len(outliers) else ''})
    summary = {'mean_fd': _round(fd[1:].mean() if n > 1 else 0.0),
               'max_fd': _round(fd.max()),
               'max_translation': _round(np.linalg.norm(trans, axis=1).max()),
               'max_rotation': _round(np.degrees(np.linalg.norm(rot, axis=1).max())),
               'max_rel_translation': _round(np.linalg.norm(delta_t, axis=1).max()),
               'max_rel_rotation': _round(np.degrees(np.linalg.norm(delta_r, axis=1).max()))}
    if outliers is not None:
        summary['outlier_slices'] = int(outliers.sum())
        summary['outlier_slices_percent'] = _round(100.0 * outliers.sum() / max(outliers.size, 1), 3)
    return rows, summary


def eddy_cnr(eddy_base, bvals, mask_path=None, b0_threshold=50, b_range=50):
    """{'snr_b0': .., 'cnr_b<shell>': ..}: mean of the eddy CNR maps inside the mask (eddy --cnr_maps writes the
    b=0 SNR then one CNR volume per shell, in increasing b-value). {} if the maps are missing."""
    import nibabel as nib
    path = next((p for p in (Path(str(eddy_base) + '.eddy_cnr_maps' + e) for e in ('.nii.gz', '.nii')) if p.is_file()), None)
    if path is None:
        return {}
    maps = np.asanyarray(nib.load(str(path)).dataobj).astype(float)
    if maps.ndim == 3:
        maps = maps[..., None]
    if mask_path is not None and Path(mask_path).is_file():
        mask = np.squeeze(np.asanyarray(nib.load(str(mask_path)).dataobj)) > 0
    else:
        mask = np.all(np.isfinite(maps), axis=-1) & (maps[..., 0] > 0)
    shell_values = shells(bvals, b0_threshold, b_range)
    names = (['snr_b0'] if min(bvals) <= b0_threshold else []) + ['cnr_b{}'.format(s) for s in shell_values]
    if len(names) != maps.shape[-1]: # eddy grouped the shells differently: don't guess the b-values
        names = ['cnr_map{}'.format(i) for i in range(maps.shape[-1])]
    out = {}
    for i, name in enumerate(names):
        v = maps[..., i][mask]
        v = v[np.isfinite(v)]
        out[name] = _round(v.mean() if v.size else np.nan, 3)
    return out


### tensor fit

def tensor_fit(data, bvals, bvecs, mask, b0_threshold=50, slice_axis=2, chunk=20000, min_slice_voxels=100, z_limit=4.0):
    """Agreement of the DWI with the signal predicted by a WLS tensor fit (with S0) inside the mask. Voxels with a
    non-positive value in some volume (e.g. thresholded at 0 after eddy) can't be fitted on the log signal and are left
    out, as are voxels whose prediction exceeds 10 times their largest value (degenerate fits).

    Returns (rows, summary, slice_r2, poor):
      rows     : per volume fit_r2 (1 - residual / total sum of squares) and fit_corr (Pearson correlation)
      slice_r2 : (slices, volumes) R2 of each slice (NaN if fewer than min_slice_voxels mask voxels); unlike the
                 correlation it also drops when the intensity of a slice drops (signal dropout)
      poor     : (slices, volumes) slices whose R2 is more than z_limit scaled MADs below the median of that slice
                 position over the volumes of the same shell
      summary  : fit_r2 / fit_corr mean and minimum, poor_fit_slices (number of poor slices)
    """
    import dipy.reconst.dti as dti
    from dipy.core.gradients import gradient_table
    bvals = np.asarray(bvals, dtype=float)
    gtab = gradient_table(bvals, np.asarray(bvecs, dtype=float), b0_threshold=b0_threshold)
    model = dti.TensorModel(gtab, fit_method='WLS', return_S0_hat=True)
    mask = np.asarray(mask) > 0
    coords = np.nonzero(mask)
    slice_index = coords[slice_axis]
    nslices, nvol = data.shape[slice_axis], data.shape[-1]
    ## sums over the voxels: per volume and per (slice, volume)
    keys = ('n', 'o', 'p', 'oo', 'pp', 'op')
    vol = {k: np.zeros(nvol) for k in keys}
    excluded = 0
    sl = {k: np.zeros((nslices, nvol)) for k in keys}
    for start in range(0, len(slice_index), chunk):
        idx = tuple(c[start:start + chunk] for c in coords)
        o = data[idx].astype(np.float64)
        s = slice_index[start:start + chunk]
        positive = np.all(o > 0, axis=1) & np.all(np.isfinite(o), axis=1)
        o, s = o[positive], s[positive]
        if len(o) == 0:
            continue
        fit = model.fit(o)
        with np.errstate(over='ignore', invalid='ignore'):
            p = fit.predict(gtab, S0=fit.S0_hat)
            good = np.all(np.isfinite(p), axis=1) & (p.max(axis=1) <= 10 * o.max(axis=1))
        o, p, s = o[good], p[good], s[good]
        excluded += len(positive) - len(o)
        terms = {'n': np.ones_like(o), 'o': o, 'p': p, 'oo': o * o, 'pp': p * p, 'op': o * p}
        for k, t in terms.items():
            vol[k] += t.sum(axis=0)
            np.add.at(sl[k], s, t)

    def stats(a):
        with np.errstate(invalid='ignore', divide='ignore'):
            n = a['n']
            cov = a['op'] - a['o'] * a['p'] / n
            var_o = a['oo'] - a['o'] ** 2 / n
            var_p = a['pp'] - a['p'] ** 2 / n
            corr = cov / np.sqrt(var_o * var_p)
            r2 = 1.0 - (a['oo'] - 2 * a['op'] + a['pp']) / var_o
        return r2, corr

    r2, corr = stats(vol)
    slice_r2, _ = stats(sl)
    slice_r2[sl['n'] < min_slice_voxels] = np.nan
    ## poorly fitted slices, per slice position and shell
    shell_values = shells(bvals, b0_threshold)
    shell_ids = np.array(shell_of(bvals, shell_values, b0_threshold))
    poor = np.zeros_like(slice_r2, dtype=bool)
    for s in np.unique(shell_ids):
        cols = np.nonzero(shell_ids == s)[0]
        if len(cols) < 5:
            continue
        c = slice_r2[:, cols]
        with np.errstate(invalid='ignore'):
            median = np.nanmedian(c, axis=1, keepdims=True)
            mad = np.maximum(1.4826 * np.nanmedian(np.abs(c - median), axis=1, keepdims=True), 0.01)
            poor[:, cols] = (c - median) / mad < -z_limit
    rows = [{'volume': v, 'bval': int(round(bvals[v])), 'fit_r2': _round(r2[v]), 'fit_corr': _round(corr[v]),
             'poor_fit_slices': int(poor[:, v].sum())} for v in range(nvol)]
    summary = {'fit_r2_mean': _round(np.nanmean(r2)), 'fit_r2_min': _round(np.nanmin(r2)),
               'fit_corr_mean': _round(np.nanmean(corr)), 'fit_corr_min': _round(np.nanmin(corr)),
               'poor_fit_slices': int(poor.sum()),
               'fit_excluded_voxels_percent': _round(100.0 * excluded / max(len(slice_index), 1), 2)}
    return rows, summary, slice_r2, poor


def carpet_plot(path, slice_r2, poor, bvals, fit_r2, title=''):
    """Slice x volume R2 of the tensor prediction (poorly fitted slices circled) and fit_r2 per volume."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    nslices, nvol = slice_r2.shape
    fig, (ax_r2, ax) = plt.subplots(2, 1, figsize=(max(6, min(18, nvol * 0.12)), 6.5), sharex=True,
                                    gridspec_kw={'height_ratios': [1, 3]})
    shell = np.array(shell_of(bvals, shells(bvals)))
    fit_r2 = np.array([np.nan if r is None else r for r in fit_r2], dtype=float)
    ax_r2.plot(np.arange(nvol), fit_r2, '-', lw=0.6, color='#adb5bd')
    for i, s in enumerate(sorted(set(shell))): # points colored by shell
        v = np.nonzero(shell == s)[0]
        ax_r2.plot(v, fit_r2[v], 'o', ms=3, color='#495057' if s == 0 else plt.cm.tab10(i % 10), label='b={}'.format(s))
    ax_r2.legend(fontsize=7, loc='lower right', ncol=min(6, len(set(shell))), frameon=False)
    ax_r2.set_ylabel('fit R²')
    ax_r2.set_title(title, fontsize=10)
    finite = slice_r2[np.isfinite(slice_r2)]
    vmin = np.percentile(finite, 1) if finite.size else 0
    im = ax.imshow(slice_r2, aspect='auto', origin='lower', cmap='viridis', vmin=vmin, vmax=1,
                   interpolation='nearest', extent=(-0.5, nvol - 0.5, -0.5, nslices - 0.5))
    ys, xs = np.nonzero(poor)
    ax.scatter(xs, ys, s=18, facecolors='none', edgecolors='#e8590c', linewidths=1.0)
    ax.set_xlabel('volume')
    ax.set_ylabel('slice')
    fig.colorbar(im, ax=[ax_r2, ax], label='slice R² of the tensor prediction', shrink=0.8)
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


### image QC (the same numbers on the raw input and on the preprocessed output)

def neighboring_correlation(data, bvals, bvecs, mask, b0_threshold=50, b_range=50):
    """Neighboring DWI correlation (NDC, as DSI Studio): the correlation inside the mask between each volume and the
    volume of the same shell whose gradient direction is the closest (opposite directions measure the same signal).
    The b=0 volumes form their own group, where the neighbor is the closest one in acquisition order.

    Returns (rows, summary): per volume its neighbor and their correlation, and the mean over the volumes ('ndc', and
    'ndc_b0' / 'ndc_b<shell>' per shell). A volume alone in its shell has no neighbor and is left out.
    """
    bvals = np.asarray(bvals, dtype=float)
    bvecs = np.asarray(bvecs, dtype=float)
    x = np.asarray(data)[np.asarray(mask) > 0].astype(np.float32) # (voxels, volumes)
    x -= x.mean(axis=0, keepdims=True)
    norm = np.linalg.norm(x, axis=0)
    x /= np.where(norm > 0, norm, np.nan)
    with np.errstate(invalid='ignore'):
        corr = np.clip(x.T @ x, -1.0, 1.0)
    shell_values = shells(bvals, b0_threshold, b_range)
    shell_ids = np.array(shell_of(bvals, shell_values, b0_threshold))
    rows = []
    for i in range(len(bvals)):
        same = np.nonzero(shell_ids == shell_ids[i])[0]
        same = same[same != i]
        if len(same) == 0:
            rows.append({'volume': i, 'bval': int(round(bvals[i])), 'neighbor': '', 'ndc': None})
            continue
        if shell_ids[i] == 0: # b=0: no direction to compare
            neighbor = int(same[np.argmin(np.abs(same - i))])
        else:
            neighbor = int(same[np.argmax(np.abs(bvecs[same] @ bvecs[i]))])
        rows.append({'volume': i, 'bval': int(round(bvals[i])), 'neighbor': neighbor,
                     'ndc': _round(corr[i, neighbor])})
    summary = {}
    all_volumes = np.ones(len(rows), dtype=bool)
    for name, keep in [('ndc', all_volumes)] + [('ndc_b{}'.format(s), shell_ids == s) for s in sorted(set(shell_ids))]:
        values = [r['ndc'] for i, r in enumerate(rows) if keep[i] and r['ndc'] is not None]
        summary[name] = _round(np.mean(values)) if values else None
    return rows, summary


def _below_shell_median(values, shell_ids, z_limit, mad_floor=0.01, min_volumes=5):
    """(slices, volumes) values that are more than z_limit scaled MADs below the median of the same slice position
    over the other volumes of the same shell. The MAD is kept at *mad_floor* at least, so that a slice position where
    all the volumes agree closely (or hold nothing but noise) doesn't turn small fluctuations into findings."""
    out = np.zeros(values.shape, dtype=bool)
    for s in np.unique(shell_ids):
        cols = np.nonzero(shell_ids == s)[0]
        if len(cols) < min_volumes:
            continue
        c = values[:, cols]
        usable = np.isfinite(c).sum(axis=1) >= min_volumes # the slice positions that are compared at all
        if not usable.any():
            continue
        c = c[usable]
        with np.errstate(invalid='ignore'):
            median = np.nanmedian(c, axis=1, keepdims=True)
            mad = np.maximum(1.4826 * np.nanmedian(np.abs(c - median), axis=1, keepdims=True), mad_floor)
            out[np.ix_(usable, cols)] = (c - median) / mad < -z_limit
    return out


def bad_slices(data, bvals, mask=None, b0_threshold=50, b_range=50, head_skip=0.1, tail_skip=0.1, z_limit=3.5,
               slice_axis=2):
    """Slices whose normalized correlation with the slice below it (same volume, as SLICE_Check) or whose mean
    intensity is far below the median of the same slice position over the other volumes of the shell (more than
    z_limit scaled MADs). The correlation catches a corrupted slice, the intensity a signal dropout: the normalized
    correlation doesn't change when a slice is scaled down. Unlike SLICE_Check this only counts the slices, it never
    excludes a volume, and the first and last slices are skipped.

    Returns (slice_corr, bad, summary): the (slices, volumes) correlations (NaN where none is computed), the bad
    slices, and {'bad_slices', 'bad_slices_percent', 'bad_slice_volumes'}.
    """
    bvals = np.asarray(bvals, dtype=float)
    nslices, nvol = data.shape[slice_axis], data.shape[-1]
    inside = None if mask is None else np.moveaxis(np.asarray(mask) > 0, slice_axis, 0).reshape(nslices, -1)
    slice_corr = np.full((nslices, nvol), np.nan)
    intensity = np.full((nslices, nvol), np.nan)
    first = int(np.floor(nslices * head_skip)) + 1
    last = int(np.floor(nslices * (1 - tail_skip)))
    for k in range(first, last):
        a = np.take(data, k, axis=slice_axis).reshape(-1, nvol).astype(np.float64)
        b = np.take(data, k - 1, axis=slice_axis).reshape(-1, nvol).astype(np.float64)
        denominator = np.sqrt((a * a).sum(axis=0) * (b * b).sum(axis=0))
        with np.errstate(invalid='ignore', divide='ignore'):
            slice_corr[k] = np.where(denominator > 0, (a * b).sum(axis=0) / denominator, np.nan)
        voxels = a if inside is None else a[inside[k]]
        if len(voxels):
            intensity[k] = voxels.mean(axis=0)
    if np.isfinite(intensity).any():
        with np.errstate(invalid='ignore', divide='ignore'):
            ## relative to the median slice of the volume: the signal of a whole volume changes with its gradient
            ## direction, a dropout only with the slice (the median so that a few corrupted slices don't move the scale)
            intensity /= np.nanmedian(intensity, axis=0, keepdims=True)
    shell_ids = np.array(shell_of(bvals, shells(bvals, b0_threshold, b_range), b0_threshold))
    ## both are on the scale of a correlation and of a ratio to the median slice, so the same floor fits them
    bad = (_below_shell_median(slice_corr, shell_ids, z_limit, mad_floor=0.01)
           | _below_shell_median(intensity, shell_ids, z_limit, mad_floor=0.01))
    checked = np.isfinite(slice_corr).sum()
    summary = {'bad_slices': int(bad.sum()),
               'bad_slices_percent': _round(100.0 * bad.sum() / max(checked, 1), 3),
               'bad_slice_volumes': int((bad.sum(axis=0) > 0).sum())}
    return slice_corr, bad, summary


def voxel_spacing(information):
    """Voxel size along the axes of a DWI, from the space directions of its information. In the pipeline these hold a
    row per axis of the stored image, so the row of the gradient axis (not a direction: NaN, or None in the header) is
    left out. None when three directions don't come out of it."""
    rows = [r for r in (information or {}).get('space_directions') or [] if r is not None]
    directions = np.array(rows, dtype=float) if rows else np.zeros((0, 3))
    if directions.ndim != 2 or directions.shape[1] != 3:
        return None
    directions = directions[np.all(np.isfinite(directions), axis=1)]
    return np.linalg.norm(directions[:3], axis=1) if len(directions) >= 3 else None


def _coherence(fa, directions, spacing, fa_min, min_voxels=100):
    """Mean |cos| (FA weighted) between the principal direction of each white matter voxel and that of the voxels one
    step ahead and behind along it; a step leaving the white matter counts as 0. The directions are the components
    along the voxel axes, the step is the smallest voxel size."""
    wm = fa > fa_min
    idx = np.nonzero(wm)
    if len(idx[0]) < min_voxels:
        return None
    start = np.stack(idx, axis=1).astype(np.float64)
    d = directions[idx]
    step = spacing.min() / spacing # one step of the smallest voxel size, in index units
    weight = fa[idx].astype(np.float64)
    total = 0.0
    for sign in (1.0, -1.0):
        q = np.rint(start + sign * d * step).astype(int)
        inside = np.all((q >= 0) & (q < np.array(fa.shape)), axis=1)
        dot = np.zeros(len(d))
        qi = tuple(q[inside].T)
        dot[inside] = np.abs(np.sum(d[inside] * directions[qi], axis=1)) * wm[qi]
        total += float(np.sum(weight * dot) / weight.sum())
    return total / 2.0


def fiber_coherence(data, bvals, bvecs, mask, spacing=None, fa_min=0.3, b0_threshold=50):
    """Fiber coherence index of the b-table (Schilling et al. 2019, as DSI Studio's b-table check): stepping from a
    white matter voxel along the principal direction of a tensor fit reaches a voxel with a similar direction, and a
    wrong sign in the b-vectors points the directions across the curved tracts, which lowers the index. It is computed
    for the b-vectors as given and with the sign of one axis flipped; flipping two axes gives the same tensors as
    flipping the third, so these four are all the candidates.

    The b-vectors have to be the components along the voxel axes ('nifti_gradient'), *spacing* their voxel size.
    The tensors are fitted once: flipping the sign of an axis of the b-vectors mirrors the fitted tensors
    (D -> M D M with M = diag(+-1)), so the principal direction of the flipped b-table is the mirrored one and the
    eigenvalues, hence FA, don't change.

    Returns {'coherence', 'coherence_best', 'coherence_best_flip'}: the index of the b-table as given, the highest of
    the four, and the flip reaching it ('none' when the b-table as given wins, anything else is a warning sign).
    """
    import dipy.reconst.dti as dti
    from dipy.core.gradients import gradient_table
    bvals = np.asarray(bvals, dtype=float)
    bvecs = np.asarray(bvecs, dtype=float)
    mask = np.asarray(mask) > 0
    spacing = np.ones(3) if spacing is None else np.abs(np.asarray(spacing, dtype=float)).ravel()
    if spacing.shape != (3,) or not np.all(np.isfinite(spacing) & (spacing > 0)):
        spacing = np.ones(3)
    gtab = gradient_table(bvals, bvecs, b0_threshold=b0_threshold)
    fit = dti.TensorModel(gtab, fit_method='WLS').fit(np.asarray(data)[mask].astype(np.float64))
    fa = np.zeros(mask.shape)
    fa[mask] = np.nan_to_num(fit.fa)
    e1 = np.zeros(mask.shape + (3,))
    e1[mask] = np.nan_to_num(fit.evecs[..., 0])
    values = {}
    for flip in ('none', 'x', 'y', 'z'):
        signs = np.array([-1.0 if a == flip else 1.0 for a in 'xyz'])
        values[flip] = _coherence(fa, e1 * signs, spacing, fa_min)
    given = values['none']
    best = max((f for f in values if values[f] is not None), key=lambda f: values[f], default=None)
    return {'coherence': _round(given), 'coherence_best': _round(values[best]) if best else None,
            'coherence_best_flip': best or ''}


def image_qc(data, bvals, bvecs, mask, spacing=None, coherence=True, b0_threshold=50, fa_min=0.3):
    """Neighboring DWI correlation, bad slices and (with *coherence*) the b-table fiber coherence index of one image.
    The b-vectors have to be the components along the voxel axes ('nifti_gradient').

    Returns (rows, summary): the per volume correlations with their bad slice count, and a one row summary.
    """
    rows, summary = neighboring_correlation(data, bvals, bvecs, mask, b0_threshold=b0_threshold)
    _, bad, bad_summary = bad_slices(data, bvals, mask=mask, b0_threshold=b0_threshold)
    for r in rows:
        r['bad_slices'] = int(bad[:, r['volume']].sum())
    summary = dict({'volumes': int(len(rows))}, **summary)
    summary.update(bad_summary)
    if coherence:
        summary.update(fiber_coherence(data, bvals, bvecs, mask, spacing=spacing, fa_min=fa_min,
                                       b0_threshold=b0_threshold))
    return rows, summary


def image_qc_plot(path, stages, title=''):
    """Neighboring DWI correlation and bad slice count of each volume, for the stages {label: rows of image_qc}.
    The volumes are placed at their original index, so the raw input and the preprocessed output line up and the
    volumes excluded on the way leave a gap."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = ['#495057', '#1c7ed6', '#e8590c']
    fig, (ax, ax_bad) = plt.subplots(2, 1, figsize=(max(6, min(18, max(len(r) for r in stages.values()) * 0.14)), 5.5),
                                     sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    for i, (label, rows) in enumerate(stages.items()):
        x = [r.get('original_index', r['volume']) for r in rows]
        ax.plot(x, [np.nan if r['ndc'] is None else r['ndc'] for r in rows], 'o-', ms=3, lw=0.8,
                color=colors[i % len(colors)], label=label)
        ax_bad.bar(np.array(x) + (i - 0.5) * 0.4, [r.get('bad_slices', 0) for r in rows], width=0.4,
                   color=colors[i % len(colors)], label=label)
    ax.set_ylabel('neighboring DWI\ncorrelation')
    ax.legend(fontsize=8, frameon=False, loc='lower right')
    ax.set_title(title, fontsize=10)
    ax_bad.set_ylabel('bad slices')
    ax_bad.set_xlabel('volume (original index)')
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return path


### denoising / Gibbs removal

def brain_mask(data, bvals, b0_threshold=50):
    """Rough brain mask (median_otsu of the mean b=0 image, or of the mean image without b=0 volumes)."""
    from dipy.segment.mask import median_otsu
    bvals = np.asarray(bvals, dtype=float)
    b0 = bvals <= max(bvals.min(), b0_threshold)
    _, mask = median_otsu(data[..., b0].mean(axis=-1), median_radius=2, numpass=1)
    return mask


def before_after_plot(path, before, after, bvals, labels=('input', 'output', 'difference'), title='', slice_axis=2):
    """Middle slice of the first b=0 volume and of a volume of the highest shell: before, after and after - before
    (the difference with a symmetric color scale)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    bvals = np.asarray(bvals, dtype=float)
    volumes = [int(np.argmin(bvals)), int(np.argmax(bvals))]
    k = before.shape[slice_axis] // 2
    fig, axes = plt.subplots(2, 3, figsize=(9, 6.4))
    for row, v in enumerate(volumes):
        b = np.take(before[..., v], k, axis=slice_axis).T
        a = np.take(after[..., v], k, axis=slice_axis).T
        d = a - b
        vmax = np.percentile(b, 99.5) or 1
        dmax = np.percentile(np.abs(d), 99.5) or 1
        for col, (img, kw) in enumerate([(b, dict(cmap='gray', vmin=0, vmax=vmax)), (a, dict(cmap='gray', vmin=0, vmax=vmax)),
                                         (d, dict(cmap='RdBu_r', vmin=-dmax, vmax=dmax))]):
            ax = axes[row, col]
            im = ax.imshow(img, origin='lower', interpolation='nearest', **kw)
            ax.set_xticks([]), ax.set_yticks([])
            ax.set_title('{} (b={})'.format(labels[col], int(round(bvals[v]))), fontsize=9)
            if col == 2:
                fig.colorbar(im, ax=ax, shrink=0.8)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)
    return path
