#
#   fiberprofile/analysis/frame_align.py
#
#   Alignment of the tensor frame to a reference after an affine registration: the rotation R (physical LPS, any
#   element of SO(3); flips are covered since R and -R give the same tensor) that best aligns the principal directions
#   of the DTI with those of the reference tensor (atlas, age bin mean tensor) in white matter, through the affine
#   transform (fixed = reference, moving = DTI). This generalises the flip detection of detect_flip (a discrete
#   correction of the frame) to the frame rotations no flip corrects (e.g. tensors estimated in the frame of an oblique
#   acquisition, or gradient tables rotated against the image).
#
#   Search: the 24 rotations of the octahedral group (every flip and axis swap), then a continuous refinement (Powell on
#   a rotation vector) from the best 3. Cost: FA weighted mean angle (deg) between A^-1 R e_s (normalised) and e_ref over
#   the voxels with reference FA > fa_ref and DTI FA > fa_sub, each angle capped at 60 deg so that misregistered voxels
#   don't dominate.
#

import itertools

import numpy as np

CAP = 60.0


def octahedral():
    """The 24 proper rotations that permute and flip the axes."""
    out = []
    for perm in itertools.permutations(range(3)):
        for s in itertools.product([1, -1], repeat=3):
            R = np.zeros((3, 3))
            for i, j in enumerate(perm):
                R[i, j] = s[i]
            if np.linalg.det(R) > 0:
                out.append(R)
    return out


def pairs(sub, ref, transform, fa_ref=0.3, fa_sub=0.2, n_max=40000, seed=0):
    """(DTI physical directions, reference physical directions, A^-1, weights) at matched white matter voxels;
    sub, ref: detect_flip.TensorField, transform: (A, b) reference -> DTI."""
    A, b = transform
    ridx = np.nonzero(ref.fa > fa_ref)
    pts = ref.to_physical(np.stack(ridx, axis=1).astype(np.float64))
    q = np.rint(sub.to_index(pts @ A.T + b)).astype(int)
    inside = np.all((q >= 0) & (q < np.array(sub.shape)), axis=1)
    keep = np.zeros(len(q), bool)
    keep[inside] = sub.fa[tuple(q[inside].T)] > fa_sub
    sel = np.flatnonzero(keep)
    if len(sel) > n_max:
        sel = np.random.default_rng(seed).choice(sel, n_max, replace=False)
    e_s = sub.physical_directions(np.ones(3), tuple(q[sel].T))
    e_r = ref.physical_directions(np.ones(3), tuple(a[sel] for a in ridx))
    w = ref.fa[tuple(a[sel] for a in ridx)].astype(float)
    return e_s, e_r, np.linalg.inv(A), w


def cost_fn(e_s, e_r, Ainv, w):
    def cost(R):
        u = (e_s @ R.T) @ Ainv.T
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        ang = np.degrees(np.arccos(np.clip(np.abs((u * e_r).sum(1)), 0, 1)))
        return float((np.minimum(ang, CAP) * w).sum() / w.sum())
    return cost


def estimate(tensor, reference, transform, fa_ref=0.3, fa_sub=0.2):
    """Frame rotation of the DTI tensor (NRRD path) against reference (NRRD path); transform: (A, b) reference -> DTI
    (detect_flip.read_itk_affine of the initial affine). Returns a dict with R (physical rotation applied to the
    tensors: D' = R D R^T), the angles (deg) with the identity, the best discrete and the refined rotation."""
    from scipy.optimize import minimize
    from scipy.spatial.transform import Rotation
    from dtiplayground.dmri.fiberprofile.analysis.detect_flip import TensorField
    sub, ref = TensorField(str(tensor)), TensorField(str(reference))
    e_s, e_r, Ainv, w = pairs(sub, ref, transform, fa_ref, fa_sub)
    if len(e_s) < 100:
        raise ValueError("too few white matter voxels ({}) to align the tensor frame".format(len(e_s)))
    cost = cost_fn(e_s, e_r, Ainv, w)
    disc = sorted(((cost(R), i, R) for i, R in enumerate(octahedral())), key=lambda t: t[0])
    best = None
    for c0, _, R0 in disc[:3]:
        f = lambda r, R0=R0: cost(Rotation.from_rotvec(r).as_matrix() @ R0)
        res = minimize(f, np.zeros(3), method='Powell', options={'xtol': 1e-4, 'ftol': 1e-4})
        R = Rotation.from_rotvec(res.x).as_matrix() @ R0
        if best is None or res.fun < best[0]:
            best = (res.fun, R, R0, c0)
    c, R, R0, c0 = best
    return dict(n_voxels=len(e_s), angle_identity=cost(np.eye(3)), angle_discrete=c0, angle_rotation=c,
                discrete=R0.round().astype(int).tolist(), R=R.tolist(),
                refine_deg=float(np.degrees(Rotation.from_matrix(R @ R0.T).magnitude())),
                total_deg=float(np.degrees(Rotation.from_matrix(R).magnitude())))


def rotate_tensor_file(input_path, output_path, R):
    """Write the tensor NRRD with its physical tensors rotated, D' = R D R^T (header kept): the stored components are
    rotated by M = F^-1 R F, F the measurement frame of the header (physical LPS)."""
    import nrrd
    from dtiplayground.dmri.fiberprofile.analysis.detect_flip import header_frames
    from dtiplayground.dmri.fiberprofile.analysis.flip_tensor import rotate_tensor, tensor_axis
    data, header = nrrd.read(str(input_path))
    frame = header_frames(header)[0]
    M = np.linalg.inv(frame) @ np.asarray(R, dtype=np.float64) @ frame
    ax, kind = tensor_axis(data, header)
    nrrd.write(str(output_path), rotate_tensor(data, M, ax, kind).astype(np.float32), header)
