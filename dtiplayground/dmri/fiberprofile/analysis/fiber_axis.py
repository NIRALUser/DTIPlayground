#
#   fiberprofile/analysis/fiber_axis.py  (from FiberProfileAnalysis/compute_fiber_axis.py)
#
#   1D curved-line axis of a fiber tract: the fiber points are binned by arc length, the coordinates are averaged
#   within each bin, and the averaged points are written as a single polyline ordered by arc length with the bin arc
#   length as point data 'SamplingDistance2Origin'.
#
#   The arc length is by default computed like EXTRACT_Profile (plane of origin + signed arc length along the fibers,
#   dtiplayground.dmri.common.fibers), so the axis matches the profiles computed by dtiplayground. With
#   arc_source='stored' the 'SamplingDistance2Origin' array of the fiber file is used (parametrized fibers written by
#   the older C++ dtitractstat).
#

import csv
import logging
from pathlib import Path

import numpy as np

import dtiplayground.dmri.common.fibers as fibers

log = logging.getLogger("compute-axis")

ARRAY_NAME = "SamplingDistance2Origin"


def fiber_arc_lengths(bundle, arc_source="dtiplayground", plane_of_origin="median"):
    """Arc length of every fiber point (NaN for points of fibers that don't cross the plane)."""
    if arc_source == "stored":
        if ARRAY_NAME not in bundle.point_data:
            raise ValueError("Point-data array '{}' not found. Available arrays: {}".format(ARRAY_NAME, sorted(bundle.point_data)))
        return np.asarray(bundle.point_data[ARRAY_NAME], dtype=np.float64).reshape(-1)
    if arc_source != "dtiplayground":
        raise ValueError("Unknown arc length source: {} (dtiplayground or stored)".format(arc_source))
    origin, normal = fibers.find_plane(bundle, plane_of_origin)
    return fibers.arc_lengths(bundle, origin, normal)


def compute_axis(points, arclength, bin_width=1.0, method="mean", outlier_sigma=3.0):
    """Average (method 'mean': outlier-cleaned mean, 'median') fiber point per arc length bin.
    Returns (axis points, bin arc lengths, number of outlier points dropped)."""
    if bin_width <= 0:
        raise ValueError("bin width must be > 0 (got {})".format(bin_width))
    if method not in {"mean", "median"}:
        raise ValueError("Unknown method: {!r}".format(method))
    valid = np.isfinite(arclength)
    points, arclength = points[valid], arclength[valid]

    bin_indices = np.round(arclength / bin_width).astype(np.int64)
    unique_bins = np.unique(bin_indices)
    axis_points = np.zeros((unique_bins.shape[0], 3), dtype=np.float64)
    n_outliers = 0
    for i, bin_id in enumerate(unique_bins):
        bin_points = points[bin_indices == bin_id]
        median = np.median(bin_points, axis=0)
        if method == "median":
            axis_points[i] = median
            continue
        # cleaned mean: drop points whose deviation from the median exceeds outlier_sigma * std on any axis
        std = bin_points.std(axis=0)
        deviations = np.abs(bin_points - median)
        outlier_mask = ((std > 0) & (deviations > outlier_sigma * std)).any(axis=1)
        inliers = bin_points[~outlier_mask]
        n_outliers += int(outlier_mask.sum())
        axis_points[i] = inliers.mean(axis=0) if inliers.size else median

    bin_centers = unique_bins.astype(np.float64) * bin_width
    order = np.argsort(bin_centers)
    return axis_points[order], bin_centers[order], n_outliers


def clip_endpoints(points, arclength, factor=4.0):
    """Clip axis points from either end whose steps exceed factor x the median step: keep the longest contiguous run of
    good steps (handles 'comet trail' endpoints clustering off the curve); repeated with the updated median.
    Returns (points, arclength, number clipped at the start, number clipped at the end)."""
    if factor <= 0:
        raise ValueError("clip factor must be > 0 (got {})".format(factor))
    n_start_total = n_end_total = 0
    while points.shape[0] >= 3:
        step_mags = np.linalg.norm(np.diff(points, axis=0), axis=1)
        median = float(np.median(step_mags))
        if median <= 0:
            break
        good = step_mags <= factor * median
        if good.all():
            break
        n = good.size
        best_start = best_len = 0
        i = 0
        while i < n:
            if not good[i]:
                i += 1
                continue
            j = i
            while j < n and good[j]:
                j += 1
            if (j - i) > best_len:
                best_len, best_start = j - i, i
            i = j
        if best_len == 0:
            break
        lo, hi = best_start, best_start + best_len + 1
        if lo == 0 and hi == points.shape[0]:
            break
        n_start_total += lo
        n_end_total += points.shape[0] - hi
        points, arclength = points[lo:hi], arclength[lo:hi]
    return points, arclength, n_start_total, n_end_total


def build_axis_polydata(axis_points, arclength):
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk
    n = axis_points.shape[0]
    vtk_points = vtk.vtkPoints()
    vtk_points.SetData(numpy_to_vtk(axis_points.astype(np.float32), deep=True))
    lines = vtk.vtkCellArray()
    lines.InsertNextCell(n)
    for i in range(n):
        lines.InsertCellPoint(i)
    arclength_array = numpy_to_vtk(arclength.astype(np.float32), deep=True)
    arclength_array.SetName(ARRAY_NAME)
    polydata = vtk.vtkPolyData()
    polydata.SetPoints(vtk_points)
    polydata.SetLines(lines)
    polydata.GetPointData().AddArray(arclength_array)
    polydata.GetPointData().SetActiveScalars(ARRAY_NAME)
    return polydata


def write_polydata(polydata, path, binary=False):
    """Legacy VTK 4.2 (readable by the NIRAL C++ tools and older VTK)."""
    import vtk
    writer = vtk.vtkPolyDataWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(polydata)
    if binary:
        writer.SetFileTypeToBinary()
    else:
        writer.SetFileTypeToASCII()
    if hasattr(writer, "SetFileVersion"):
        writer.SetFileVersion(42)
    if writer.Write() != 1:
        raise IOError("Couldn't write {}".format(path))


def read_axis(path):
    """(points (n x 3, RAS), arc lengths (n,)) of an axis file."""
    axis = fibers.read_fibers(path)
    if ARRAY_NAME not in axis.point_data:
        raise ValueError("{} has no '{}' point data".format(path, ARRAY_NAME))
    return axis.points, np.asarray(axis.point_data[ARRAY_NAME], dtype=np.float64).reshape(-1)


def fiber_axis(fiber_file, output_file, bin_width=1.0, method="mean", outlier_sigma=3.0, clip=True, clip_factor=4.0,
               arc_source="dtiplayground", plane_of_origin="median", binary=False):
    """Compute and write the axis of one fiber file. Returns (axis points, arc lengths)."""
    bundle = fibers.read_fibers(fiber_file)
    arclength = fiber_arc_lengths(bundle, arc_source, plane_of_origin)
    axis_points, axis_arc, n_outliers = compute_axis(bundle.points, arclength, bin_width, method, outlier_sigma)
    n_start = n_end = 0
    if clip:
        axis_points, axis_arc, n_start, n_end = clip_endpoints(axis_points, axis_arc, clip_factor)
    write_polydata(build_axis_polydata(axis_points, axis_arc), output_file, binary=binary)
    details = ", dropped {} outliers (>{}sigma)".format(n_outliers, outlier_sigma) if method == "mean" else ""
    if clip:
        details += ", clipped {} from start and {} from end (>{}x median step)".format(n_start, n_end, clip_factor)
    log.info("Wrote axis with %d points (bin width %g, method %s, arc length %s%s) to %s",
             axis_points.shape[0], bin_width, method, arc_source if arc_source == "stored" else "{} plane".format(plane_of_origin),
             details, output_file)
    return axis_points, axis_arc


### profiles on the axis (visualization)

_HEMISPHERE_MAP = {"l": "left", "r": "right"}
_NOISE_TOKENS = frozenset({"parametrized", "axis"})


def _tokenize_name(name):
    """Comparable token set of a fiber or profile folder name: lowercase, '_' tokens, without noise tokens,
    l/r -> left/right (hemisphere may appear anywhere)."""
    tokens = set()
    for raw in Path(name).stem.lower().split("_"):
        if raw and raw not in _NOISE_TOKENS:
            tokens.add(_HEMISPHERE_MAP.get(raw, raw))
    return frozenset(tokens)


def resolve_profiles_dir(path, fiber_stem):
    """A folder with *.csv is used as is; otherwise the subfolder whose tokenized name matches the fiber."""
    path = Path(path)
    if any(path.glob("*.csv")):
        return path
    target = _tokenize_name(fiber_stem)
    matches = [d for d in sorted(path.iterdir()) if d.is_dir() and _tokenize_name(d.name) == target]
    if len(matches) > 1:
        raise ValueError("Ambiguous profile match for {}: {}".format(fiber_stem, [m.name for m in matches]))
    if not matches:
        raise ValueError("No subfolder of {} matches fiber '{}'".format(path, fiber_stem))
    return matches[0]


def read_profile_csv(path):
    """(arc lengths, subject ids, values (n_arc x n_subjects)) of a profile CSV, sorted by arc length."""
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = [row for row in reader if row]
    if len(header) < 2:
        raise ValueError("Profile CSV needs at least 2 columns: {}".format(path))
    data = np.array([[float(v) if v not in ("", None) else np.nan for v in row] for row in rows], dtype=np.float64)
    order = np.argsort(data[:, 0])
    return data[order, 0], header[1:], data[order, 1:]


def profiles_on_axis(profiles_dir, axis_points, axis_arc, output_file, binary=False):
    """Write one VTK with the axis and a point data array '<property>_<subject>' per profile CSV column in profiles_dir,
    interpolated at the axis arc lengths (axis trimmed to the arc length range of the profiles)."""
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk
    profiles_dir = Path(profiles_dir)
    folder_prefix = profiles_dir.name + "_"
    csv_paths = sorted(p for p in profiles_dir.glob("*.csv") if not p.name.endswith("_agebinstats.csv"))
    if not csv_paths:
        return None, 0, 0
    polydata = sub_arc = None
    n_subjects = 0
    for csv_path in csv_paths:
        csv_arc, subjects, values = read_profile_csv(csv_path)
        stem = csv_path.stem
        property_name = stem[len(folder_prefix):] if stem.startswith(folder_prefix) else stem
        if polydata is None:
            mask = (axis_arc >= csv_arc.min()) & (axis_arc <= csv_arc.max())
            if not mask.any():
                log.warning("No overlap between axis arc lengths [%g, %g] and profile range [%g, %g]; skipping profiles",
                            axis_arc.min(), axis_arc.max(), csv_arc.min(), csv_arc.max())
                return None, 0, 0
            sub_arc = axis_arc[mask]
            polydata = build_axis_polydata(axis_points[mask], sub_arc)
            n_subjects = len(subjects)
        for j, subject in enumerate(subjects):
            arr = numpy_to_vtk(np.interp(sub_arc, csv_arc, values[:, j]).astype(np.float32), deep=True)
            arr.SetName("{}_{}".format(property_name, subject))
            polydata.GetPointData().AddArray(arr)
    write_polydata(polydata, output_file, binary=binary)
    return output_file, len(csv_paths), n_subjects


### command line

def add_parser(subparsers):
    p = subparsers.add_parser("compute-axis", help="Compute the 1D axis of fiber tracts",
                              description="Compute a 1D axis curve of fiber tracts by averaging fiber point coordinates "
                                          "within arc length bins. Writes <tract>_axis.vtk with point data "
                                          "SamplingDistance2Origin (arc length).")
    p.add_argument("inputs", nargs="+", help="Fiber files (.vtk/.vtp) or folders of fiber files")
    p.add_argument("-o", "--output", default=None,
                   help="Output axis file (single input) or folder (several inputs; default: next to each input)")
    p.add_argument("--arc-source", choices=["dtiplayground", "stored"], default="dtiplayground",
                   help="Arc length: 'dtiplayground' computes it like EXTRACT_Profile (default), 'stored' uses the "
                        "SamplingDistance2Origin array of the fiber file")
    p.add_argument("--plane-of-origin", choices=["median", "cog"], default="median",
                   help="Plane of origin for --arc-source dtiplayground (default: median, as EXTRACT_Profile)")
    p.add_argument("-b", "--bin-width", type=float, default=1.0, help="Arc length bin width (default: 1.0)")
    p.add_argument("-m", "--method", choices=("mean", "median"), default="mean",
                   help="Per-bin aggregation: 'mean' (default) drops points deviating more than --outlier-sigma std from "
                        "the bin median on any axis and averages the rest; 'median' uses the median coordinate")
    p.add_argument("--outlier-sigma", type=float, default=3.0, help="Outlier threshold for --method mean (default: 3.0)")
    p.add_argument("--no-clip", dest="clip", action="store_false",
                   help="Disable endpoint clipping (default: clip ends whose step exceeds --clip-factor x median step)")
    p.add_argument("--clip-factor", type=float, default=4.0, help="Endpoint clipping factor (default: 4.0)")
    p.add_argument("--profiles-dir", default=None,
                   help="Profile CSV folder (a tract folder with *.csv, or the base folder with one subfolder per tract): "
                        "also write <tract>_axis_profiles.vtk with the profiles on the axis")
    p.add_argument("--profiles-output-dir", default=None, help="Folder for the profile VTKs (default: next to the axis)")
    p.add_argument("--binary", action="store_true", help="Write binary VTK (default: ASCII); files are legacy VTK 4.2")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


def _fiber_files(inputs):
    files = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            files += sorted(f for f in path.iterdir() if f.suffix in (".vtk", ".vtp") and not f.stem.endswith("_axis"))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError("Input not found: {}".format(item))
    return files


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
    files = _fiber_files(args.inputs)
    if not files:
        raise ValueError("No fiber files found in {}".format(args.inputs))
    single_output = args.output is not None and len(files) == 1 and not Path(args.output).is_dir() and Path(args.output).suffix in (".vtk", ".vtp")
    for fiber_file in files:
        if single_output:
            output_file = Path(args.output)
        elif args.output is not None:
            Path(args.output).mkdir(parents=True, exist_ok=True)
            output_file = Path(args.output).joinpath(fiber_file.stem + "_axis.vtk")
        else:
            output_file = fiber_file.with_name(fiber_file.stem + "_axis.vtk")
        axis_points, axis_arc = fiber_axis(fiber_file, output_file, args.bin_width, args.method, args.outlier_sigma,
                                           args.clip, args.clip_factor, args.arc_source, args.plane_of_origin, args.binary)
        if args.profiles_dir is not None:
            resolved = resolve_profiles_dir(args.profiles_dir, fiber_file.stem)
            out_dir = Path(args.profiles_output_dir) if args.profiles_output_dir else output_file.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            path, n_props, n_subjects = profiles_on_axis(resolved, axis_points, axis_arc,
                                                          out_dir.joinpath(output_file.stem + "_profiles.vtk"), args.binary)
            if path is not None:
                log.info("Wrote %d properties x %d subjects = %d arrays to %s", n_props, n_subjects, n_props * n_subjects, path)
    return 0
