#
#   fiberprofile/analysis/gather.py  (from FiberProfileAnalysis/gather_profiles.py)
#
#   Gather along-tract profiles across subjects/sessions into one CSV per (tract, metric):
#
#       <out>/<tract>/<tract>_<metric>.csv     rows: Arc_Length samples, columns: one per dataset identifier
#
#   Inputs (any mix, searched recursively under the given folders):
#     - FVP trees:  <subject>/<session>/Profiles/<subject>_<session>_<prefix>_<tract>_<metric>.fvp
#                   identifier <subject>_<session>_<prefix>; value from the Parameter_Value column
#     - dtiplayground EXTRACT_Profile outputs:  .../00_EXTRACT_Profile/<PROP>/<tract>_<PROP>.csv
#                   (cases as columns or as rows); identifier = case id of the datasheet
#
#   All profiles of a tract must share one arc-length grid: the first profile read for a tract is the template;
#   later profiles with a different sample count, or an arc length deviating more than --arc-tolerance percent of
#   the template's tract length, are reported and excluded. Grids within tolerance are snapped onto the template.
#   The column set is shared by all metric tables of a tract (blank where a dataset lacks that metric).
#   The standard DTI metric names are written in lower case (fa, md, rd, ad), other metric names are kept.
#

import glob
import logging
import os
from collections import defaultdict

import pandas as pd

log = logging.getLogger("gather")

FVP_HEADER_PREFIX = "Arc_Length,"
EXTRACT_PROFILE_DIR = "00_EXTRACT_Profile"
LOWERCASE_METRICS = {"fa", "md", "rd", "ad"}


def normalize_metric(metric):
    return metric.lower() if metric.lower() in LOWERCASE_METRICS else metric


def load_tract_vocabulary(fibers_dir):
    """Tract names from the fiber VTK files, longest first for suffix matching."""
    if not fibers_dir or not os.path.isdir(fibers_dir):
        if fibers_dir:
            log.warning("fibers dir '%s' not found; falling back to '_dwi_' name splitting", fibers_dir)
        return []
    tracts = [os.path.splitext(f)[0] for f in os.listdir(fibers_dir) if f.lower().endswith((".vtk", ".vtp"))]
    return sorted(set(tracts), key=len, reverse=True)


def parse_fvp_name(path, tracts):
    """(subject, session, prefix, tract, metric) from an FVP filename, or None.
    subject/session are the first two tokens and the metric the last; the tract is the longest known tract name that is
    a suffix of the middle span, the prefix whatever precedes it. Without a tract vocabulary the name is split at the
    last '_dwi_'."""
    base = os.path.basename(path)
    if base.endswith(".fvp"):
        base = base[:-4]
    toks = base.split("_")
    if len(toks) < 4:
        return None
    subject, session, metric = toks[0], toks[1], toks[-1]
    middle = "_".join(toks[2:-1])
    tract = None
    for t in tracts:  # longest first -> unambiguous (Fornix_L vs Fornix_narrow_L)
        if middle == t or middle.endswith("_" + t):
            tract = t
            break
    if tract is not None:
        prefix = middle[: -len(tract)].rstrip("_") if middle != tract else ""
    elif "_dwi_" in base:
        prefix, tail = base.split("_dwi_", 1)
        prefix = "_".join(prefix.split("_")[2:] + ["dwi"])
        tract = tail.rsplit("_", 1)[0]
    else:
        return None
    return subject, session, prefix, tract, metric


def arc_key(arc, arc_precision):
    return "%.*f" % (arc_precision, round(float(arc), arc_precision) + 0.0)  # +0.0 normalises -0.0


def read_fvp_profile(path, value_col="Parameter_Value", arc_precision=4):
    """{arc_length_str: value} of one FVP file, or None if unparseable (arc lengths as rounded strings so columns align
    exactly across files)."""
    try:
        with open(path) as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        log.warning("could not read %s (%s)", path, exc)
        return None
    hidx = next((i for i, l in enumerate(lines) if l.startswith(FVP_HEADER_PREFIX)), None)
    if hidx is None:
        log.warning("no '%s' header in %s; skipping", FVP_HEADER_PREFIX, path)
        return None
    header = lines[hidx].split(",")
    try:
        ai = header.index("Arc_Length")
        vi = header.index(value_col)
    except ValueError:
        log.warning("column '%s' not found in %s (has %s); skipping", value_col, path, header)
        return None
    profile = {}
    for row in lines[hidx + 1:]:
        if not row.strip():
            continue
        parts = row.split(",")
        if len(parts) <= max(ai, vi):
            continue
        try:
            profile[arc_key(parts[ai], arc_precision)] = float(parts[vi])
        except ValueError:
            continue
    return profile or None


def read_extract_profile_csv(path, arc_precision=4):
    """{identifier: {arc_length_str: value}} of an EXTRACT_Profile table (cases as columns: first column 'Arc Length';
    cases as rows: first column 'case_id', arc lengths as column names)."""
    df = pd.read_csv(path)
    first = str(df.columns[0])
    profiles = {}
    if first.strip().lower().replace("_", " ") == "arc length":
        keys = [arc_key(a, arc_precision) for a in df.iloc[:, 0]]
        for ident in df.columns[1:]:
            profiles[str(ident)] = dict(zip(keys, df[ident].astype(float)))
    elif first == "case_id":
        keys = [arc_key(a, arc_precision) for a in df.columns[1:]]
        for _, row in df.iterrows():
            profiles[str(row.iloc[0])] = dict(zip(keys, row.iloc[1:].astype(float)))
    else:
        log.warning("unrecognized profile table layout in %s; skipping", path)
    return profiles


def compare_arc_grid(arcs, template, tol):
    """None when the grid matches the template (same sample count, arc lengths within tol), else a reason string."""
    if len(arcs) != len(template):
        return "{} samples vs {} in the template".format(len(arcs), len(template))
    worst = max(range(len(arcs)), key=lambda i: abs(arcs[i] - template[i]), default=None)
    if worst is None or abs(arcs[worst] - template[worst]) <= tol:
        return None
    return ("arc length differs by {:.4g} at sample {} ({:.4g} vs {:.4g}), tolerance {:.4g}"
            .format(abs(arcs[worst] - template[worst]), worst, arcs[worst], template[worst], tol))


def rename_excluded(path, suffix="_exclude"):
    """Rename an excluded FVP to <name>.fvp_exclude (no longer matches *.fvp on later runs)."""
    target = path + suffix
    try:
        if os.path.exists(target):
            log.warning("overwriting existing %s", target)
        os.replace(path, target)
    except OSError as exc:
        log.warning("could not rename %s (%s)", path, exc)
        return False
    log.info("renamed %s -> %s", path, os.path.basename(target))
    return True


def find_inputs(profiles_dirs):
    """(fvp files outside EXTRACT_Profile outputs, EXTRACT_Profile tables [(path, tract, metric)])."""
    fvps, tables = [], []
    for root in profiles_dirs:
        for f in sorted(glob.glob(os.path.join(root, "**", "*.fvp"), recursive=True)):
            if EXTRACT_PROFILE_DIR not in f.split(os.sep):  # per-subject intermediates of EXTRACT_Profile
                fvps.append(f)
        for f in sorted(glob.glob(os.path.join(root, "**", EXTRACT_PROFILE_DIR, "*", "*.csv"), recursive=True)):
            prop = os.path.basename(os.path.dirname(f))
            name = os.path.basename(f)[:-4]
            if name.endswith("_" + prop) and not name.endswith("_agebinstats"):
                tables.append((f, name[: -len(prop) - 1], prop))
    return sorted(set(fvps)), tables


def gather_profiles(profiles_dirs, out_dir, fibers_dir=None, value_column="Parameter_Value", metrics=None, tracts=None,
                    arc_tolerance=0.1, rename_mismatched=False, arc_precision=4):
    """Gather profiles into <out_dir>/<tract>/<tract>_<metric>.csv. Returns the list of written CSV paths."""
    if isinstance(profiles_dirs, str):
        profiles_dirs = [profiles_dirs]
    for d in profiles_dirs:
        if not os.path.isdir(d):
            raise FileNotFoundError("profiles dir not found: {}".format(d))
    wanted_metrics = {m.lower() for m in metrics} if metrics else None
    wanted_tracts = {t.lower() for t in tracts} if tracts else None
    if wanted_metrics:
        log.info("Restricting to metrics: %s", ", ".join(sorted(wanted_metrics)))
    if wanted_tracts:
        log.info("Restricting to tracts: %s", ", ".join(sorted(wanted_tracts)))

    vocabulary = load_tract_vocabulary(fibers_dir)
    if fibers_dir:
        log.info("Tract vocabulary: %d names from %s", len(vocabulary), fibers_dir)
    if wanted_tracts and vocabulary:
        unknown = sorted(wanted_tracts - {t.lower() for t in vocabulary})
        if unknown:
            log.warning("requested tract(s) not in %s: %s", fibers_dir, ", ".join(unknown))

    fvps, tables = find_inputs(profiles_dirs)
    log.info("Found %d FVP files and %d EXTRACT_Profile tables under %s", len(fvps), len(tables), ", ".join(profiles_dirs))

    groups = defaultdict(dict)         # (tract, metric) -> {identifier -> {arc -> value}}
    tract_idents = defaultdict(set)    # tract -> identifiers seen (any metric)
    tract_arcs = {}                    # tract -> (arc keys, arc positions, source, tolerance); first profile wins
    counts = defaultdict(int)

    def add_profile(tract, metric, ident, profile, source, fvp_path=None):
        keys = tuple(profile)
        arcs = tuple(float(k) for k in keys)
        if tract not in tract_arcs:
            length = abs(arcs[-1] - arcs[0]) if len(arcs) > 1 else 0.0
            tract_arcs[tract] = (keys, arcs, source, length * arc_tolerance / 100.0)
        tmpl_keys, tmpl_arcs, tmpl_source, tol = tract_arcs[tract]
        reason = compare_arc_grid(arcs, tmpl_arcs, tol)
        if reason is not None:
            log.warning("inconsistent profile sampling in %s (%s); template %s - excluding", source, reason, os.path.basename(tmpl_source))
            counts["arc_mismatch"] += 1
            if rename_mismatched and fvp_path is not None:
                rename_excluded(fvp_path)
            return
        if keys != tmpl_keys:  # within tolerance: snap onto the template grid
            profile = dict(zip(tmpl_keys, profile.values()))
        tract_idents[tract].add(ident)
        if ident in groups[(tract, metric)]:
            log.warning("duplicate identifier %s for (%s, %s); overwriting", ident, tract, metric)
        groups[(tract, metric)][ident] = profile
        counts["ok"] += 1

    def wanted(tract, metric):
        if wanted_tracts is not None and tract.lower() not in wanted_tracts:
            return False
        if wanted_metrics is not None and metric.lower() not in wanted_metrics:
            return False
        return True

    for f in fvps:
        parsed = parse_fvp_name(f, vocabulary)
        if parsed is None:
            log.warning("could not parse tract/metric from %s; skipping", os.path.basename(f))
            counts["skip"] += 1
            continue
        subject, session, prefix, tract, metric = parsed
        metric = normalize_metric(metric)
        if not wanted(tract, metric):
            counts["filtered"] += 1
            continue
        profile = read_fvp_profile(f, value_column, arc_precision)
        if profile is None:
            counts["skip"] += 1
            continue
        add_profile(tract, metric, "_".join(x for x in (subject, session, prefix) if x), profile, f, fvp_path=f)

    for f, tract, prop in tables:
        metric = normalize_metric(prop)
        if not wanted(tract, metric):
            counts["filtered"] += 1
            continue
        for ident, profile in read_extract_profile_csv(f, arc_precision).items():
            add_profile(tract, metric, ident, profile, "{} [{}]".format(f, ident))

    all_idents = sorted(set().union(*tract_idents.values())) if tract_idents else []
    log.info("Parsed %d profiles (%d skipped%s%s); %d identifiers, %d (tract,metric) tables",
             counts["ok"], counts["skip"],
             ", {} excluded by the tract/metric selection".format(counts["filtered"]) if counts["filtered"] else "",
             ", {} excluded for inconsistent sampling".format(counts["arc_mismatch"]) if counts["arc_mismatch"] else "",
             len(all_idents), len(groups))

    os.makedirs(out_dir, exist_ok=True)
    written = []
    for (tract, metric), per_ident in sorted(groups.items()):
        columns = sorted(tract_idents[tract])
        arc_rows = sorted({arc for prof in per_ident.values() for arc in prof}, key=float)
        data = {ident: [per_ident.get(ident, {}).get(arc, float("nan")) for arc in arc_rows] for ident in columns}
        df = pd.DataFrame(data, index=arc_rows, columns=columns)
        df.index.name = "Arc_Length"
        tract_dir = os.path.join(out_dir, tract)
        os.makedirs(tract_dir, exist_ok=True)
        out_csv = os.path.join(tract_dir, "{}_{}.csv".format(tract, metric))
        df.to_csv(out_csv)
        written.append(out_csv)
    log.info("Wrote %d CSV files under %s/", len(written), out_dir)
    return written


### command line

def add_parser(subparsers):
    p = subparsers.add_parser("gather", help="Gather subject profiles into one CSV per tract and metric",
                              description="Gather along-tract profiles (FVP trees and/or dtiplayground EXTRACT_Profile "
                                          "outputs) into <out-dir>/<tract>/<tract>_<metric>.csv with arc length rows "
                                          "and one column per dataset.")
    p.add_argument("--profiles-dir", nargs="+", default=["Output_Profiles"], metavar="DIR",
                   help="Folders searched recursively for *.fvp and EXTRACT_Profile outputs")
    p.add_argument("--fibers-dir", default=None,
                   help="Folder of tract VTK files (tract names used to parse FVP file names)")
    p.add_argument("--out-dir", default="Profiles_CSV", help="Output root (one subfolder per tract)")
    p.add_argument("--value-column", default="Parameter_Value", help="FVP column to tabulate (default: Parameter_Value)")
    p.add_argument("--metrics", nargs="+", metavar="METRIC", help="Only these metrics (e.g. fa md NDI); default: all")
    p.add_argument("--tracts", nargs="+", metavar="TRACT", help="Only these tracts (e.g. Fornix_L Fornix_R); default: all")
    p.add_argument("--arc-tolerance", type=float, default=0.1, metavar="PCT",
                   help="Allowed arc-length deviation from the tract template, in %% of its length (default: 0.1); "
                        "the sample count must match exactly")
    p.add_argument("--rename-mismatched", action="store_true",
                   help="Rename FVP files excluded for inconsistent sampling to <name>.fvp_exclude")
    p.add_argument("--arc-precision", type=int, default=4, help="Decimals for arc-length alignment (default: 4)")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
    gather_profiles(args.profiles_dir, args.out_dir, args.fibers_dir, args.value_column, args.metrics, args.tracts,
                    args.arc_tolerance, args.rename_mismatched, args.arc_precision)
    return 0
