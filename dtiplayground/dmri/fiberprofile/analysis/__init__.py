#
#   fiberprofile/analysis
#
#   Fiber profile analysis tools (from the FiberProfileAnalysis scripts), available as dmrifiberprofile commands:
#     flip-tensor      reflect the tensor frame of a DTI along axes
#     parametrize-fibers  resample fiber tracts on the arc length grid (as EXTRACT_Profile)
#     compute-axis     1D axis (average curve) of fiber tracts, parametrized by arc length
#     gather           collect subject profiles into one CSV per tract and metric
#     impute           fill missing profile values (per-dataset SIREN)
#     qc-registration  QC of the registration of subjects to the atlas
#     qc-profiles      age-binned profile statistics and profile QC
#

import logging
import sys

COMMANDS = ['flip_tensor', 'parametrize', 'fiber_axis', 'gather', 'impute', 'registration_qc', 'profile_qc']


def add_commands(subparsers):
    """Register the analysis commands on an argparse subparsers object."""
    import importlib
    for name in COMMANDS:
        importlib.import_module('dtiplayground.dmri.fiberprofile.analysis.' + name).add_parser(subparsers)


def setup_logging(verbose=False):
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(levelname)s | %(message)s" if verbose else "%(message)s",
                        stream=sys.stdout)
