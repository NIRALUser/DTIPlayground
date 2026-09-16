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


def flip_tensor_file(input_path, output_path, axes):
    """Flip the tensor frame of a DTI NRRD file; the header is written back unchanged."""
    import nrrd
    data, header = nrrd.read(str(input_path))
    kinds = [str(k).lower() for k in header.get("kinds", [])]
    tensor_axes = [i for i, k in enumerate(kinds) if k in COMPONENTS]
    if len(tensor_axes) == 1:
        component_axis, kind = tensor_axes[0], kinds[tensor_axes[0]]
    elif data.ndim == 4 and data.shape[0] == 6:  # no kinds: 6 components first
        component_axis, kind = 0, "3d-symmetric-matrix"
    else:
        raise ValueError("expected a tensor NRRD (kind 3D-symmetric-matrix, 3D-masked-symmetric-matrix or 3D-matrix); "
                         "got shape {} with kinds {}".format(data.shape, header.get("kinds")))
    flipped = flip_tensor(data, axes, component_axis, kind)
    nrrd.write(str(output_path), flipped, header)
    return parse_axes(axes)


### command line

def add_parser(subparsers):
    p = subparsers.add_parser("flip-tensor", help="Reflect the tensor frame of a DTI NRRD along axes",
                              description="Reflect the orientation frame of a diffusion tensor NRRD along one or more axes "
                                          "(D' = R D R^T with R = diag(+-1)). The voxel layout and header are unchanged.")
    p.add_argument("input", help="Input tensor NRRD")
    p.add_argument("output", help="Output tensor NRRD")
    p.add_argument("--axes", required=True, help="Axes to flip: comma-separated among x,y,z (e.g. 'x' or 'x,z')")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
    axes = flip_tensor_file(args.input, args.output, args.axes)
    log.info("Flipped tensor axes %s; wrote %s", axes, args.output)
    return 0
