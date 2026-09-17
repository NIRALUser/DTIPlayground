#
#   fiberprofile/analysis/parametrize.py
#
#   Parametrize fiber tracts by arc length (replaces dtitractstat -f): the plane of origin and the arc length of every
#   fiber point are computed like EXTRACT_Profile, and each fiber is resampled on the arc length grid (multiples of the
#   step size from the plane): every output point is the average position of the fiber points in one arc length bin,
#   with point data FiberLocationIndex (grid index) and SamplingDistance2Origin (average arc length).
#   Fibers that don't cross the plane are left out.
#

import logging
from pathlib import Path

import numpy as np

import dtiplayground.dmri.common.fibers as fibers

log = logging.getLogger("parametrize-fibers")


def parametrize_fibers(fiber_file, output_file, plane_of_origin="median", step_size=1.0):
    """Write the arc length parametrized fibers of fiber_file. Returns (number of fibers in, number of fibers out)."""
    bundle = fibers.read_fibers(fiber_file)
    origin, normal = fibers.find_plane(bundle, plane_of_origin)
    arcs = fibers.arc_lengths(bundle, origin, normal)
    grid = fibers.profile_grid(arcs, step_size)
    fibers.write_parameterized_fibers(bundle, arcs, grid, output_file)
    used = sum(1 for i in range(bundle.number_of_fibers) if not np.all(np.isnan(arcs[bundle.fiber_slice(i)])))
    log.info("%s: %d of %d fibers parametrized on %d arc length samples (%g..%g) -> %s",
             Path(fiber_file).name, used, bundle.number_of_fibers, len(grid), grid[0], grid[-1], output_file)
    return bundle.number_of_fibers, used


### command line

def add_parser(subparsers):
    p = subparsers.add_parser("parametrize-fibers", help="Resample fiber tracts on the arc length grid",
                              description="Parametrize fiber tracts by arc length like EXTRACT_Profile: each fiber is "
                                          "resampled to one point per arc length bin (average position), with point "
                                          "data FiberLocationIndex and SamplingDistance2Origin.")
    p.add_argument("inputs", nargs="+", help="Fiber files (.vtk/.vtp) or folders of fiber files")
    p.add_argument("-o", "--output", required=True,
                   help="Output fiber file (single input) or folder (written with the input file names)")
    p.add_argument("--plane-of-origin", choices=["median", "cog"], default="median",
                   help="Plane of origin (default: median, as EXTRACT_Profile)")
    p.add_argument("--step-size", type=float, default=1.0, help="Arc length step in mm (default: 1)")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    from dtiplayground.dmri.fiberprofile.analysis.fiber_axis import _fiber_files
    setup_logging(args.verbose)
    files = _fiber_files(args.inputs)
    if not files:
        raise ValueError("No fiber files found in {}".format(args.inputs))
    output = Path(args.output)
    single = len(files) == 1 and output.suffix in (".vtk", ".vtp") and not output.is_dir()
    if not single:
        output.mkdir(parents=True, exist_ok=True)
    for f in files:
        parametrize_fibers(f, output if single else output.joinpath(f.name), args.plane_of_origin, args.step_size)
    return 0
