#
#   fiberprofile/analysis/flip_tensor.py  (from FiberProfileAnalysis/flip_tensor.py)
#
#   Reflect the orientation frame of a diffusion tensor NRRD along one or more axes.
#
#   This reflects the tensor directions, not the voxel layout: R = diag(sx, sy, sz) is applied to every voxel's
#   tensor, D' = R D R^T, i.e. each component D_ij is multiplied by s_i * s_j. A single-axis flip negates that axis's
#   off-diagonal terms and leaves the diagonal (and FA, MD, eigenvalues) unchanged. It corrects a tensor-frame
#   handedness / LPS-RAS sign-convention mismatch (e.g. the flip detected by qc-registration).
#
#   With the voxel frame (--voxel-frame, correction 'voxel'), the stored components are taken to be in the frame of the
#   voxel axes (as written by a tensor estimation in voxel coordinates) instead of the measurement frame of the header,
#   and are rotated into the space of the header: D' = M D M^T, M = unit space directions; the measurement frame is set
#   to the identity. On an oblique grid this corrects the rotation between the voxel axes and the space, which no flip
#   does. Flips are applied first, in the stored frame.
#

import logging

import numpy as np

log = logging.getLogger("flip-tensor")

AXIS = {"x": 0, "y": 1, "z": 2}
COMPONENTS = {  # tensor kind -> (row, col) of each stored component (None: mask component)
    "3d-symmetric-matrix": [(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)],
    "3d-masked-symmetric-matrix": [None, (0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)],
    "3d-matrix": [(i, j) for i in range(3) for j in range(3)],
}


def parse_axes(axes):
    if isinstance(axes, str):
        axes = axes.split(",")
    axes = [a.strip().lower() for a in axes if a.strip()]
    bad = [a for a in axes if a not in AXIS]
    if bad or not axes:
        raise ValueError("invalid axes {}; choose from x,y,z".format(bad if bad else axes))
    return axes


def flip_tensor(data, axes, component_axis=0, kind="3d-symmetric-matrix"):
    """Reflect the tensor frame of a tensor field along axes ('x', 'y', 'z').
    data: tensor field with the tensor components along component_axis; kind: NRRD kind of that axis."""
    kind = kind.lower()
    if kind not in COMPONENTS:
        raise ValueError("unsupported tensor kind: {}".format(kind))
    if data.shape[component_axis] != len(COMPONENTS[kind]):
        raise ValueError("{} expects {} components, found {}".format(kind, len(COMPONENTS[kind]), data.shape[component_axis]))
    signs = np.ones(3)
    for a in parse_axes(axes):
        signs[AXIS[a]] = -1.0
    out = np.moveaxis(data.copy(), component_axis, 0)
    for c, ij in enumerate(COMPONENTS[kind]):
        if ij is not None and signs[ij[0]] * signs[ij[1]] != 1.0:
            out[c] *= -1
    return np.moveaxis(out, 0, component_axis)


def parse_correction(spec):
    """Correction of the tensor frame from a spec like 'none', 'x', 'x,z', 'voxel' or 'voxel,x': (frame, axes) with frame
    'header' or 'voxel'."""
    tokens = [t.strip().lower() for t in (spec.split(",") if isinstance(spec, str) else spec) if t.strip()]
    frame = "voxel" if "voxel" in tokens else "header"
    axes = [t for t in tokens if t not in ("voxel", "none")]
    return frame, (parse_axes(axes) if axes else [])


def correction_name(frame, axes):
    parts = (["voxel"] if frame == "voxel" else []) + list(axes)
    return ",".join(parts) if parts else "none"


def rotate_tensor(data, M, component_axis=0, kind="3d-symmetric-matrix"):
    """D' = M D M^T for every voxel of a tensor field (components along component_axis)."""
    kind = kind.lower()
    out = np.moveaxis(np.asarray(data, dtype=np.float64).copy(), component_axis, -1)
    D = np.zeros(out.shape[:-1] + (3, 3))
    for c, ij in enumerate(COMPONENTS[kind]):
        if ij is not None:
            D[..., ij[0], ij[1]] = out[..., c]
            if kind != "3d-matrix":
                D[..., ij[1], ij[0]] = out[..., c]
    R = np.einsum("ab,...bc,dc->...ad", M, D, M)
    for c, ij in enumerate(COMPONENTS[kind]):
        if ij is not None:
            out[..., c] = R[..., ij[0], ij[1]]
    return np.moveaxis(out, -1, component_axis).astype(data.dtype)


def voxel_axes(header):
    """Unit space directions of the header (columns), in the space of the header."""
    sd = [np.asarray(d, dtype=np.float64) for d in header.get("space directions", [])
          if d is not None and np.all(np.isfinite(np.asarray(d, dtype=float)))]
    if len(sd) != 3:
        raise ValueError("the header has no 3 space directions: {}".format(header.get("space directions")))
    M = np.array(sd).T
    return M / np.linalg.norm(M, axis=0)


def reorient_tensor_file(input_path, output_path, spec):
    """Apply a correction (parse_correction) to a DTI NRRD file: flips of the stored frame, then with the voxel frame
    the rotation of the components into the space of the header (measurement frame set to the identity).
    Returns the name of the correction."""
    import nrrd
    frame, axes = parse_correction(spec)
    data, header = nrrd.read(str(input_path))
    component_axis, kind = tensor_axis(data, header)
    if axes:
        data = flip_tensor(data, axes, component_axis, kind)
    if frame == "voxel":
        data = rotate_tensor(data, voxel_axes(header), component_axis, kind)
        header["measurement frame"] = np.eye(3)
    nrrd.write(str(output_path), data, header)
    return correction_name(frame, axes)


def tensor_axis(data, header):
    """(component axis, kind) of a tensor NRRD."""
    kinds = [str(k).lower() for k in header.get("kinds", [])]
    tensor_axes = [i for i, k in enumerate(kinds) if k in COMPONENTS]
    if len(tensor_axes) == 1:
        component_axis, kind = tensor_axes[0], kinds[tensor_axes[0]]
    elif data.ndim == 4 and data.shape[0] == 6:  # no kinds: 6 components first
        component_axis, kind = 0, "3d-symmetric-matrix"
    else:
        raise ValueError("expected a tensor NRRD (kind 3D-symmetric-matrix, 3D-masked-symmetric-matrix or 3D-matrix); "
                         "got shape {} with kinds {}".format(data.shape, header.get("kinds")))
    return component_axis, kind


def flip_tensor_file(input_path, output_path, axes):
    """Flip the tensor frame of a DTI NRRD file; the header is written back unchanged."""
    import nrrd
    data, header = nrrd.read(str(input_path))
    component_axis, kind = tensor_axis(data, header)
    flipped = flip_tensor(data, axes, component_axis, kind)
    nrrd.write(str(output_path), flipped, header)
    return parse_axes(axes)


### command line

def add_parser(subparsers):
    p = subparsers.add_parser("flip-tensor", help="Reflect the tensor frame of a DTI NRRD along axes",
                              description="Reflect the orientation frame of a diffusion tensor NRRD along one or more axes "
                                          "(D' = R D R^T with R = diag(+-1)). The voxel layout and header are unchanged. "
                                          "With --voxel-frame, the components are taken to be in the frame of the voxel "
                                          "axes and are rotated into the space of the header after the flips (the "
                                          "measurement frame is set to the identity).")
    p.add_argument("input", help="Input tensor NRRD")
    p.add_argument("output", help="Output tensor NRRD")
    p.add_argument("--axes", help="Axes to flip: comma-separated among x,y,z (e.g. 'x' or 'x,z')")
    p.add_argument("--voxel-frame", action="store_true", help="The components are in the frame of the voxel axes: rotate "
                                                               "them into the space of the header (oblique grids)")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
    if not args.axes and not args.voxel_frame:
        log.error("Give --axes and/or --voxel-frame")
        return 1
    spec = (["voxel"] if args.voxel_frame else []) + (args.axes.split(",") if args.axes else [])
    name = reorient_tensor_file(args.input, args.output, spec)
    log.info("Applied tensor frame correction '%s'; wrote %s", name, args.output)
    return 0
