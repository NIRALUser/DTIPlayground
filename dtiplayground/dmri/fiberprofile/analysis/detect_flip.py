#
#   fiberprofile/analysis/detect_flip.py
#
#   Find the correction of the tensor frame that makes a diffusion tensor NRRD correctly oriented: a flip of x, y, z
#   (and their combinations) of the stored components, in the measurement frame of the header or in the frame of the
#   voxel axes (components estimated in voxel coordinates while the header gives another frame: on an oblique grid
#   this is a rotation that no flip corrects). Every candidate is scored with up to two criteria:
#
#   - coherence (no reference needed): in a correctly oriented tensor field, stepping from a white matter voxel along
#     its principal direction reaches a voxel with a similar principal direction (the tract continues). A wrong flip
#     points the directions across curved tracts (corpus callosum, cingulum, ...), and the continuity drops.
#   - atlas agreement (with --reference): the angle between the principal directions of the image and of a reference
#     tensor (atlas, normative mean tensor) in white matter. The two images are matched by their physical coordinates,
#     so the image has to be registered to the reference (e.g. registered_dti.nrrd of DTI_Register), or --transform
#     gives the affine transform from the reference to the image (ITK text file, e.g. initialAffine.txt of DTI_Register;
#     it is computed from FA, which a flip doesn't change).
#
#   A correction is applied as by 'flip-tensor' (D' = R D R^T, R = diag(+-1), then with the voxel frame the rotation
#   into the space of the header); R and -R give the same tensor, so the 8 flip combinations form 4 distinct results
#   (e.g. 'x,y' equals 'z'), and on an axis-aligned grid the voxel frame equals a flip of the header frame. Candidates
#   giving the same tensors are marked 'same as' the first one (header frame first).
#

import itertools
import logging

import numpy as np

from dtiplayground.dmri.fiberprofile.analysis.flip_tensor import COMPONENTS, correction_name

log = logging.getLogger("detect-tensor-flip")

FLIPS = [c for n in range(4) for c in itertools.combinations("xyz", n)]  # (), (x,), ..., (x,y,z)


def flip_name(axes):
    return ",".join(axes) if axes else "none"


def flip_signs(axes):
    return np.array([-1.0 if a in axes else 1.0 for a in "xyz"])


def header_frames(header):
    """(header frame, voxel frame, voxel axes, origin) of a tensor NRRD header, in physical LPS coordinates: the
    frames map the stored components to physical space (measurement frame of the header, or the unit voxel axes);
    the voxel axes are the space directions (columns)."""
    space = str(header.get("space", "left-posterior-superior")).lower()
    to_lps = np.diag([-1.0 if space in ("right-anterior-superior", "ras") else 1.0] * 2 + [1.0])
    sd = header.get("space directions")
    sd = [d for d in (sd if sd is not None else []) if d is not None and np.all(np.isfinite(np.asarray(d, dtype=float)))]
    directions = to_lps @ (np.array(sd, dtype=np.float64).T if len(sd) == 3 else np.eye(3))
    origin = header.get("space origin")
    origin = to_lps @ (np.asarray(origin, dtype=np.float64) if origin is not None else np.zeros(3))
    mf = header.get("measurement frame")
    frame = to_lps @ (np.asarray(mf, dtype=np.float64).T if mf is not None else np.eye(3))
    return frame, directions / np.linalg.norm(directions, axis=0), directions, origin


def correction_matrix(header, correction="none"):
    """Stored components -> physical LPS directions for a correction ('none', 'x', 'voxel,x', ...)."""
    from dtiplayground.dmri.fiberprofile.analysis.flip_tensor import parse_correction
    frame, axes = parse_correction(correction)
    header_frame, voxel_frame, _, _ = header_frames(header)
    return (voxel_frame if frame == "voxel" else header_frame) @ np.diag(flip_signs(axes))


def candidate_corrections(header):
    """Distinct corrections of a tensor NRRD header: [(name, matrix)], the header frame first; corrections giving the
    same tensors (R and -R, voxel frame equal to a flip) are listed once."""
    out, seen = [], set()
    for frame in ("header", "voxel"):
        for axes in FLIPS:
            name = correction_name(frame, axes)
            E = correction_matrix(header, name)
            key = matrix_key(E)
            if key not in seen:
                seen.add(key)
                out.append((name, E))
    return out


def matrix_key(E):
    """Key of the stored -> physical matrix E up to its sign (E and -E give the same tensors)."""
    flat = E.ravel()
    return tuple(np.round(E * np.sign(flat[np.argmax(np.abs(flat))]), 4).ravel())


class TensorField:
    """Tensor NRRD: principal direction (stored frame), FA, and the voxel <-> physical mapping."""

    def __init__(self, path, fa_min=0.0):
        import nrrd
        data, header = nrrd.read(str(path))
        kinds = [str(k).lower() for k in header.get("kinds", [])]
        axes = [i for i, k in enumerate(kinds) if k in COMPONENTS]
        if len(axes) == 1:
            comp_axis, kind = axes[0], kinds[axes[0]]
        elif data.ndim == 4 and data.shape[0] == 6:
            comp_axis, kind = 0, "3d-symmetric-matrix"
        else:
            raise ValueError("{} is not a tensor NRRD (shape {}, kinds {})".format(path, data.shape, header.get("kinds")))
        data = np.moveaxis(np.asarray(data, dtype=np.float64), comp_axis, -1)
        self.shape = data.shape[:3]
        D = np.zeros(self.shape + (3, 3))
        for c, ij in enumerate(COMPONENTS[kind]):
            if ij is not None:
                D[..., ij[0], ij[1]] = data[..., c]
                D[..., ij[1], ij[0]] = data[..., c]
        w, v = np.linalg.eigh(D)  # ascending
        w = np.clip(w, 0, None)
        md = w.mean(-1)
        norm = np.sqrt((w ** 2).sum(-1))
        with np.errstate(invalid="ignore", divide="ignore"):
            fa = np.sqrt(1.5 * ((w - md[..., None]) ** 2).sum(-1)) / norm
        self.fa = np.nan_to_num(fa).astype(np.float32)
        self.e1 = v[..., :, -1]  # principal direction in the stored (measurement) frame
        self.mask = self.fa > fa_min

        ## physical space: LPS (as ITK); frames: stored components -> physical; directions: voxel axes (columns)
        self.frame, self.voxel_frame, self.directions, self.origin = header_frames(header)
        self.spacing = np.linalg.norm(self.directions, axis=0)

    def frame_matrix(self, frame="header"):
        return self.voxel_frame if frame == "voxel" else self.frame

    def physical_directions(self, signs, idx, frame="header"):
        """Flipped principal directions of the voxels idx (tuple of index arrays), in physical space, with the stored
        components in the measurement frame of the header or in the voxel frame."""
        return (self.e1[idx] * signs) @ self.frame_matrix(frame).T

    def to_index(self, points):
        return np.linalg.solve(self.directions, (points - self.origin).T).T

    def to_physical(self, index):
        return index @ self.directions.T + self.origin


def coherence(field, signs, fa_min, frame="header"):
    """Mean |cos| between the principal direction of each white matter voxel and that of the voxels one step ahead and
    behind along it (FA weighted; a step leaving the white matter counts as 0)."""
    idx = np.nonzero(field.fa > fa_min)
    e = field.physical_directions(signs, idx, frame)  # (N,3) physical
    e_all = np.zeros(field.shape + (3,))
    e_all[idx] = e
    wm = field.fa > fa_min
    start = np.stack(idx, axis=1).astype(np.float64)
    step = field.spacing.min()
    step_idx = np.linalg.solve(field.directions, (e * step).T).T  # physical step -> voxel step
    weight = field.fa[idx].astype(np.float64)
    total = 0.0
    for sign in (1.0, -1.0):
        q = np.rint(start + sign * step_idx).astype(int)
        inside = np.all((q >= 0) & (q < np.array(field.shape)), axis=1)
        dot = np.zeros(len(e))
        qi = tuple(q[inside].T)
        dot[inside] = np.abs(np.sum(e[inside] * e_all[qi], axis=1)) * wm[qi]
        total += np.sum(weight * dot) / weight.sum()
    return total / 2.0


def read_itk_affine(path):
    """(A, b) of an ITK text transform file (AffineTransform / MatrixOffsetTransform / Euler / Similarity written as a
    matrix + translation): maps a physical point x of the fixed image (LPS) to A x + b in the moving image."""
    params = fixed = None
    with open(path) as fh:
        for line in fh:
            if line.startswith("Parameters:"):
                params = np.array(line.split(":", 1)[1].split(), dtype=np.float64)
            elif line.startswith("FixedParameters:"):
                fixed = np.array(line.split(":", 1)[1].split(), dtype=np.float64)
    if params is None or len(params) != 12:
        raise ValueError("{} is not a 3D affine ITK text transform (12 parameters)".format(path))
    A = params[:9].reshape(3, 3)
    center = fixed[:3] if fixed is not None and len(fixed) >= 3 else np.zeros(3)
    return A, params[9:12] + center - A @ center


def atlas_agreement(field, signs, reference, fa_min, transform=None, frame="header"):
    """Median angle (degrees) between the principal directions of the reference and the flipped ones of the image,
    over the reference voxels with FA > fa_min whose position in the image (identity, or the affine transform (A, b)
    from the reference to the image) has FA > fa_min; directions of the image are brought back with A^-1."""
    ridx = np.nonzero(reference.fa > fa_min)
    pts = reference.to_physical(np.stack(ridx, axis=1).astype(np.float64))
    A, b = transform if transform is not None else (np.eye(3), np.zeros(3))
    q = np.rint(field.to_index(pts @ A.T + b)).astype(int)
    inside = np.all((q >= 0) & (q < np.array(field.shape)), axis=1)
    qi = tuple(q[inside].T)
    both = field.fa[qi] > fa_min
    if both.sum() < 100:
        return np.nan, int(both.sum())
    e = field.physical_directions(signs, tuple(a[both] for a in qi), frame)
    if transform is not None:
        e = np.linalg.solve(A, e.T).T
        e /= np.linalg.norm(e, axis=1, keepdims=True)
    e_ref = reference.physical_directions(np.ones(3), tuple(a[inside][both] for a in ridx))
    dot = np.clip(np.abs(np.sum(e * e_ref, axis=1)), 0, 1)
    return float(np.median(np.degrees(np.arccos(dot)))), int(both.sum())


def detect_flip(image, reference=None, fa_min=0.3, transform=None):
    """Score all corrections of the tensor frame of the tensor NRRD image (flip combinations, in the header frame and in
    the voxel frame), optionally against a reference tensor NRRD with the affine transform from the reference to the
    image (an ITK text file or (A, b)).
    Returns (rows, best, by_coherence): one row per candidate with 'correction', 'frame', 'flip', 'same_as',
    'coherence', 'angle' (deg), 'voxels'; the name of the best correction (smallest angle to the reference when there is
    one, else highest coherence; e.g. 'x' or 'voxel,x', usable with DTI_Register tensorFlip) and the one of the highest
    coherence."""
    field = TensorField(image)
    ref = TensorField(reference) if reference else None
    if isinstance(transform, str):
        transform = read_itk_affine(transform)
    if (field.fa > fa_min).sum() < 100:
        raise ValueError("fewer than 100 voxels with FA > {} in {}".format(fa_min, image))
    rows, scores, first = [], {}, {}
    for frame in ("header", "voxel"):
        for axes in FLIPS:
            name = correction_name(frame, axes)
            signs = flip_signs(axes)
            key = matrix_key(field.frame_matrix(frame) @ np.diag(signs))
            if key not in scores:
                first[key] = name
                coh = coherence(field, signs, fa_min, frame)
                ang, n = atlas_agreement(field, signs, ref, fa_min, transform, frame) if ref is not None else (np.nan, 0)
                scores[key] = (coh, ang, n)
            coh, ang, n = scores[key]
            rows.append({"correction": name, "frame": frame, "flip": flip_name(axes),
                         "same_as": first[key] if first[key] != name else "", "coherence": coh, "angle": ang, "voxels": n})
    if ref is not None and np.isfinite([s[1] for s in scores.values()]).all():
        best = min(scores, key=lambda k: scores[k][1])
    else:
        best = max(scores, key=lambda k: scores[k][0])
    by_coh = max(scores, key=lambda k: scores[k][0])
    return rows, first[best], first[by_coh]


### command line

def add_parser(subparsers):
    p = subparsers.add_parser("detect-tensor-flip", help="Find the correction of the tensor frame that orients a DTI correctly",
                              description="Score every flip combination of the tensor frame (none, x, y, z, x,y, x,z, y,z, "
                                          "x,y,z) of a DTI NRRD, with the components in the measurement frame of the "
                                          "header and in the frame of the voxel axes (oblique grids), by the coherence of "
                                          "the principal directions along the tracts and, with --reference, by their "
                                          "agreement with a reference tensor (atlas or normative mean tensor; the image "
                                          "registered to it, or --transform). The correction found can be applied with "
                                          "'flip-tensor' or DTI_Register tensorFlip.")
    p.add_argument("input", help="Tensor NRRD to check")
    p.add_argument("--reference", help="Reference tensor NRRD (atlas) in the same physical space as the input")
    p.add_argument("--transform", help="Affine ITK text transform from the reference to the input (e.g. initialAffine.txt "
                                       "of DTI_Register), when the input is not registered to the reference")
    p.add_argument("--fa-min", type=float, default=0.3, help="FA threshold of the white matter voxels used (default 0.3)")
    p.add_argument("--output", help="Write the scores to this CSV file")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
    rows, best, by_coh = detect_flip(args.input, args.reference, args.fa_min, args.transform)
    has_ref = args.reference is not None
    log.info("%-14s %-10s %10s %s", "correction", "same as", "coherence", "atlas angle (deg)" if has_ref else "")
    for r in rows:
        log.info("%-14s %-10s %10.4f %s", r["correction"], r["same_as"], r["coherence"],
                 "{:8.1f}".format(r["angle"]) if has_ref else "")
    if has_ref:
        log.info("Best correction by atlas agreement: %s ; by coherence: %s%s", best, by_coh,
                 "" if best == by_coh else "  (the criteria disagree, check the registration to the reference)")
    else:
        log.info("Best correction by coherence: %s", best)
    if best != "none":
        axes = [a for a in best.split(",") if a != "voxel"]
        log.info("Apply it with: dmrifiberprofile flip-tensor %s <output>%s%s", args.input,
                 " --voxel-frame" if best.startswith("voxel") else "", " --axes " + ",".join(axes) if axes else "")
    if args.output:
        import csv
        with open(args.output, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        log.info("Wrote %s", args.output)
    return 0
