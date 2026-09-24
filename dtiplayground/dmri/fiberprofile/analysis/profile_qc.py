#
#   fiberprofile/analysis/profile_qc.py  (from FiberProfileAnalysis/profile_stat_QC.py)
#   dmrifiberprofile qc-profiles
#
#!/usr/bin/env python3
"""
Compute age-binned statistics (mean, std, percentiles) for along-tract metric
tables and render per-tract QC plots.

The profiles root may hold either layout, and both are read as they are:

  * gathered (``dmrifiberprofile gather``)  ``<tract>/<tract>_<metric>.csv``
  * the output of a run (EXTRACT_Profile)   ``00_EXTRACT_Profile/<metric>/<tract>_<metric>.csv``

so ``gather`` is not needed to QC the profiles of a run. In the second the
folder is the metric and the file name carries the tract, the other way round
from the first; the metrics are named as ``gather`` writes them (fa, md, ad, rd
in lower case), so the same ``--prior-stats-dir`` fits both. A root holding both
(gathered tables written inside the run folder) uses the gathered ones. Tables
of EXTRACT_Profile with ``resultCaseColumnwise`` false (one row per case) are
transposed on reading.

For every table, the columns
(``<subject>_<session>_<prefix>`` identifiers, where the session encodes age as
``ses-<months>m``) are grouped into age bins.  For each bin, the per-arc-length
mean, standard deviation, subject count and percentiles across subjects are
computed (ignoring missing values) and written to a companion CSV:

    <tract>/<tract>_<metric>_agebinstats.csv

with ``Arc_Length`` as rows and ``<bin>_mean`` / ``<bin>_std`` / ``<bin>_N`` /
``<bin>_p<q>`` as columns.

Two QC figures per tract are written under ``StatPlots/``:
  * ``<tract>_meanstd.png``     -- mean +/- std bands per age bin
  * ``<tract>_percentiles.png`` -- 25/50/75 percentile bands per age bin
each with one subplot per metric.

Default age bins (inclusive, months): 0-3, 4-9, 10-60.  The **oldest** bin is
open-ended, so subjects older than its upper bound (e.g. > 60 months) are folded
into it.

Locations sampled outside the brain: a metric that cannot be 0 in tissue (FA,
MD, RD, AD, NDI, ODI, ...) is 0 where the fibers of that case left the brain
mask and the maps were read as background. That is a property of the location,
so it is read as missing on EVERY metric of that tract and case, including the
ones in which 0 is a valid measurement (``--zero-valid-metrics``, by default
FWF, the free water fraction). ``--keep-outside-brain`` keeps the zeros. With
``--clean-dir`` those cells are written empty, so the cleaned tables hold what
the QC used rather than the zeros it ignored.

A profile with less than ``--min-valid-frac`` of its positions left (missing, or
outside the brain) is flagged as an outlier: too little of it is there to judge.
Without it a profile that is missing everywhere would pass, since every
comparison with it is undefined. The check counts the values that are there, not
the comparisons that succeeded: where the prior has no envelope (an age bin with
a single subject has no std) nothing is comparable, which says nothing about the
profile.

With ``--registration-qc`` (a registration-QC folder or ``registration_qc.csv``),
every subject-session flagged there as a registration failure is removed from
ALL tracts/metrics up front -- before any stats, profile QC, or cleaning.
Likewise ``--prep-qc`` (the reformatted DWI preprocessing-QC CSV) removes
individual scans whose excluded gradients exceed ``--prep-excluded-frac`` of the
original, or whose ``rms_larger_than_2`` exceeds ``--prep-rms2-frac`` of the
remaining gradients.

Optionally, with ``--prior-stats-dir`` pointing at a folder of previously
computed stats (e.g. ``ProfileQCStats``, in either layout: they sit next to the
tables they were computed from), profiles are QC'd against the
age-appropriate prior reference to flag likely failed processing.  Because all
of a tract's metrics come from the same tract data, the decision is made once
per **(subject-session, tract)** and applied to every metric of that tract:

  (1) **value / magnitude outlier** -- the in-envelope / valid position counts
      are pooled across the contributing metrics into one joint fraction
      (envelope = ``mean ± k·std`` or a ``p_lo..p_hi`` percentile band); flagged
      when the joint fraction drops below ``--value-min-inside``.
      ``--outlier-exclude-metrics`` (default ``FWF``) drops metrics from this
      computation -- e.g. FWF is a CSF-contamination metric rarely analysed --
      while the resulting decision is still applied to them.  ``--envelope-batch-
      correct`` first removes a technical location offset between the testing and
      normative populations (robust median shift per (metric, age-bin); additive
      for FA-like metrics, multiplicative for diffusivities) so a batch effect
      does not masquerade as value outliers.  It does not touch the shape QC.
  (2) **shape / anatomy outlier** -- based on the ``--shape-metric`` (FA) profile
      only, since flat metrics carry little shape information: the Pearson
      correlation with the prior bin **mean** (or ``--corr-reference median``)
      below ``--corr-min`` (or a robust per-(tract,bin) ``Q1-k·IQR`` fence).

Outputs: ``profile_qc_<reference>.csv`` (per-metric detail + group flags),
``outliers_<reference>.csv`` (per (subject-session, tract) decision), and one
box+violin figure per (metric, age-bin).  With ``--clean-dir``, the flagged
profiles are removed from ALL metric tables of their tract and cleaned profiles
are written there.

Usage
-----
    dmrifiberprofile qc-profiles --profiles-dir Profiles --plots-dir StatPlots
    dmrifiberprofile qc-profiles --profiles-dir Profiles --prior-stats-dir ProfileQCStats
    dmrifiberprofile qc-profiles --profiles-dir <run output>/00_EXTRACT_Profile --plots-dir StatPlots
"""

from __future__ import annotations

import argparse
import glob
import logging
import math
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd

from dtiplayground.dmri.fiberprofile.analysis.gather import normalize_metric

log = logging.getLogger("profile_qc")

AGE_RE = re.compile(r"ses-(\d+)m")
OUTPUT_SUFFIX = "_agebinstats.csv"
PERCENTILES = [1, 5, 25, 50, 75, 95, 99]
CASE_COLUMN = "case_id" # EXTRACT_Profile with resultCaseColumnwise false: one row per case, arc lengths as columns
# Metrics in which 0 is a valid measurement, so a 0 there does not mean the position was sampled outside the brain.
ZERO_VALID_METRICS = {"FWF"}
# Locations sampled outside the brain, per tract (see find_outside_brain / set_outside_brain).
_OUTSIDE_BRAIN = {}
# {prior stats folder: {(tract, metric): path}}, see prior_stats_index
_PRIOR_INDEX = {}
# Preferred metric ordering for the plot subplot grid; others appended.
METRIC_ORDER = ["fa", "md", "rd", "ad", "NDI", "ODI", "FWF"]
# The four DTI metrics shown in the excluded-profiles review figures.
DIFFUSION_METRICS = ["fa", "md", "rd", "ad"]
# Colour-blind-friendly colours, one per age bin (extended if more bins).
BIN_COLORS = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860"]


def tract_and_metric(path):
    """(tract, metric) of a profile table, in either layout:

      gathered (``dmrifiberprofile gather``)   ``<tract>/<tract>_<metric>.csv``
      run output (EXTRACT_Profile)             ``00_EXTRACT_Profile/<metric>/<tract>_<metric>.csv``

    The folder is the tract in the first and the metric in the second, so the file name decides which one it is.
    Tract names contain underscores (AC_olfactory, Arc_FT_L), which is why the folder is taken off the name as a
    prefix or a suffix instead of splitting it. The metric is normalized the way ``gather`` writes it (fa, md, ad, rd
    in lower case), so the prior stats of a gathered normative set are found for either layout.
    """
    folder = os.path.basename(os.path.dirname(path))
    name = os.path.basename(path)[: -len(".csv")]
    if folder and name.startswith(folder + "_"):
        return folder, normalize_metric(name[len(folder) + 1:])
    if folder and name.endswith("_" + folder):
        return name[: -len(folder) - 1], normalize_metric(folder)
    return folder, normalize_metric(name.rsplit("_", 1)[-1])


def is_run_output_table(path):
    """The table is a per property one of EXTRACT_Profile (``<metric>/<tract>_<metric>.csv``), not a gathered one."""
    folder = os.path.basename(os.path.dirname(path))
    name = os.path.basename(path)[: -len(".csv")]
    return bool(folder) and not name.startswith(folder + "_") and name.endswith("_" + folder)


def select_inputs(profiles_dir):
    """The profile tables under *profiles_dir*, in either layout (see tract_and_metric). A folder holding both the
    EXTRACT_Profile output of a run and gathered tables (e.g. the gathered ones written into the run folder) offers
    the same profiles twice: the gathered table is used and the other one left out."""
    files = sorted(f for f in glob.glob(os.path.join(profiles_dir, "**", "*.csv"), recursive=True)
                   if not f.endswith(OUTPUT_SUFFIX))
    gathered = {tract_and_metric(f): f for f in files if not is_run_output_table(f)}
    inputs = list(gathered.values())
    duplicates = 0
    for f in files:
        if not is_run_output_table(f):
            continue
        if tract_and_metric(f) in gathered:
            duplicates += 1
        else:
            inputs.append(f)
    if duplicates:
        log.info("%d table(s) of the EXTRACT_Profile output are also there as gathered tables; the gathered ones "
                 "are used", duplicates)
    return sorted(inputs)


def parse_bins(spec: str):
    """Parse "lo-hi,lo-hi,..." into sorted [(lo, hi, label), ...].

    The highest bin is made open-ended (hi -> +inf) so older subjects fall
    into it, while its label keeps the user-specified upper bound.
    """
    bins = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        lo, hi = (int(x) for x in token.split("-"))
        bins.append([lo, hi, f"{lo}-{hi}m"])
    bins.sort(key=lambda b: b[0])
    if bins:
        bins[-1][1] = math.inf  # oldest bin catches everything above its lower edge
    return [tuple(b) for b in bins]


def age_of(column: str):
    m = AGE_RE.search(column)
    return int(m.group(1)) if m else None


def bin_columns(columns, bins):
    """Map bin label -> list of columns whose age falls in that bin."""
    grouped = {label: [] for _, _, label in bins}
    for col in columns:
        age = age_of(col)
        if age is None:
            log.debug("no age in column '%s'; skipping", col)
            continue
        for lo, hi, label in bins:
            if lo <= age <= hi:
                grouped[label].append(col)
                break
    return grouped


def process_table(df: pd.DataFrame, bins, ddof: int) -> pd.DataFrame:
    """Binned mean/std/N/percentiles for one metric table (arc x subjects)."""
    grouped = bin_columns(df.columns, bins)
    out = pd.DataFrame(index=df.index)
    for _, _, label in bins:
        cols = grouped[label]
        sub = df[cols]  # arc-length x subjects (possibly empty)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            out[f"{label}_mean"] = sub.mean(axis=1, skipna=True) if cols else np.nan
            out[f"{label}_std"] = sub.std(axis=1, skipna=True, ddof=ddof) if cols else np.nan
            out[f"{label}_N"] = sub.notna().sum(axis=1).astype(int) if cols else 0
            for q in PERCENTILES:
                if cols:
                    out[f"{label}_p{q}"] = np.nanpercentile(sub.to_numpy(dtype=float), q, axis=1)
                else:
                    out[f"{label}_p{q}"] = np.nan
        log.debug("  %s: %d subjects", label, len(cols))
    out.index.name = "Arc_Length"
    return out


def ordered_metrics(metrics):
    known = [m for m in METRIC_ORDER if m in metrics]
    extra = sorted(m for m in metrics if m not in METRIC_ORDER)
    return known + extra


def _plot_grid(tract, stats, bins, kind, out_path, dpi):
    """Render one figure (kind='meanstd' or 'percentiles') with a subplot per metric."""
    import matplotlib.pyplot as plt

    metrics = ordered_metrics(stats.keys())
    n = len(metrics)
    ncols = min(4, n)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.8, nrows * 3.0), squeeze=False)
    axes = axes.ravel()

    for ax, metric in zip(axes, metrics):
        df = stats[metric]
        x = df.index.to_numpy(dtype=float)
        for bi, (_, _, label) in enumerate(bins):
            color = BIN_COLORS[bi % len(BIN_COLORS)]
            nmax = int(df[f"{label}_N"].max()) if f"{label}_N" in df else 0
            leg = f"{label} (n≤{nmax})"
            if kind == "meanstd":
                mean = df[f"{label}_mean"].to_numpy(dtype=float)
                std = df[f"{label}_std"].to_numpy(dtype=float)
                ax.plot(x, mean, color=color, lw=1.6, label=leg)
                ax.fill_between(x, mean - std, mean + std, color=color, alpha=0.18, linewidth=0)
            else:  # percentiles 25/50/75
                p25 = df[f"{label}_p25"].to_numpy(dtype=float)
                p50 = df[f"{label}_p50"].to_numpy(dtype=float)
                p75 = df[f"{label}_p75"].to_numpy(dtype=float)
                ax.plot(x, p50, color=color, lw=1.6, label=leg)
                ax.fill_between(x, p25, p75, color=color, alpha=0.18, linewidth=0)
                ax.plot(x, p25, color=color, lw=0.7, ls="--")
                ax.plot(x, p75, color=color, lw=0.7, ls="--")
        ax.set_title(metric, fontsize=10)
        ax.set_xlabel("Arc length", fontsize=8)
        ax.set_ylabel(metric, fontsize=8)
        ax.tick_params(labelsize=7)
        ax.margins(x=0)

    for ax in axes[n:]:  # hide unused cells
        ax.set_visible(False)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(bins), fontsize=9, frameon=False)
    title = "mean ± std" if kind == "meanstd" else "25/50/75 percentiles"
    fig.suptitle(f"{tract} — {title} by age bin", fontsize=12)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def subject_session_of(column):
    """The <subject>_<session> key of a profile column (drops the prefix)."""
    toks = column.split("_")
    return f"{toks[0]}_{toks[1]}" if len(toks) >= 2 else column


def load_registration_failures(path):
    """Load the set of <subject>_<session> ids flagged by registration QC.

    *path* may be the registration-QC folder (containing ``registration_qc.csv``)
    or the CSV itself.
    """
    csv = os.path.join(path, "registration_qc.csv") if os.path.isdir(path) else path
    if not os.path.isfile(csv):
        raise FileNotFoundError(f"registration QC table not found: {csv}")
    df = pd.read_csv(csv)
    if "is_outlier" not in df.columns:
        raise ValueError(f"{csv} has no 'is_outlier' column")
    id_col = "id" if "id" in df.columns else df.columns[0]
    return set(df.loc[df["is_outlier"].astype(bool), id_col].astype(str))


def load_prep_failures(path, excluded_frac, rms2_frac):
    """Full identifiers failing preprocessing QC (reformatted DWIQC report).

    A scan fails if excluded gradients exceed *excluded_frac* of the original
    gradients, OR rms_larger_than_2 exceeds *rms2_frac* of the remaining
    gradients.  The report may list ``original_number_of_gradients`` and/or
    ``remaining_number_of_gradients``; a missing one is derived (original =
    remaining + excluded).  QC_Report before 0.7.12 wrote the remaining count as
    ``original_number_of_gradients``.  Returns a set of
    ``sub-<sub>_ses-<ses>_<prefix>`` identifiers.
    """
    csv = path
    if os.path.isdir(path):
        cand = [os.path.join(path, n) for n in ("DWIQC_report_reformatted.csv", "DWIQC_report.csv")]
        csv = next((c for c in cand if os.path.isfile(c)), cand[0])
    if not os.path.isfile(csv):
        raise FileNotFoundError(f"preprocessing QC table not found: {csv}")
    df = pd.read_csv(csv, dtype={"sub": str, "ses": str, "prefix": str})

    # The report lists either the original or the remaining gradient count;
    # the missing one is derived as original = remaining + excluded.
    has_orig = "original_number_of_gradients" in df.columns
    has_rem = "remaining_number_of_gradients" in df.columns
    if not (has_orig or has_rem):
        raise ValueError(f"{csv} needs 'original_number_of_gradients' or 'remaining_number_of_gradients'")
    need = {"sub", "ses", "prefix", "number_of_excluded_gradients", "rms_larger_than_2"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"{csv} missing columns {sorted(missing)} (run prep_qc_reformat.py first?)")

    failed = set()
    for _, r in df.iterrows():
        exc = float(r["number_of_excluded_gradients"])
        rms2 = float(r["rms_larger_than_2"])
        if has_rem:  # remaining reported (with the original since 0.7.12)
            remaining = float(r["remaining_number_of_gradients"])
            orig = float(r["original_number_of_gradients"]) if has_orig else remaining + exc
        else:
            orig = float(r["original_number_of_gradients"])
            remaining = orig - exc
        fail_exc = orig > 0 and exc > excluded_frac * orig
        fail_rms = remaining > 0 and rms2 > rms2_frac * remaining
        if fail_exc or fail_rms:
            failed.add(f"sub-{r['sub']}_ses-{r['ses']}_{r['prefix']}")
    return failed


def read_profile_table(path):
    """A profile CSV as arc lengths x cases. A table of EXTRACT_Profile with ``resultCaseColumnwise`` false holds them
    the other way round (first column ``case_id``, arc lengths as column names) and is transposed."""
    df = pd.read_csv(path, index_col=0)
    if str(df.index.name).strip() == CASE_COLUMN:
        df = df.transpose()
        df.index = pd.to_numeric(df.index, errors="coerce")
        df.index.name = "Arc_Length"
    return df


def find_outside_brain(inputs, zero_valid_metrics=ZERO_VALID_METRICS):
    """{tract: (arc lengths x cases) boolean table} of the profile locations that were sampled outside the brain.

    A metric that cannot be zero in tissue (FA, MD, RD, AD, NDI, ODI, ...) is zero at a position when the fibers
    there fell outside the brain mask and the maps were read as background. That is a property of the location, not
    of the metric, so the position is dropped from every metric of that tract and case, including the ones where
    zero is a valid measurement (*zero_valid_metrics*, by default the free water fraction). Values that are not
    positive count, so a negative diffusivity is dropped as well.
    """
    outside = {}
    for path in inputs:
        tract, metric = tract_and_metric(path)
        if metric in zero_valid_metrics:
            continue
        try:
            df = read_profile_table(path)
        except Exception as e:
            log.warning("could not read %s: %s", path, e)
            continue
        with np.errstate(invalid="ignore"):
            bad = df.le(0)
        if not bad.to_numpy().any():
            continue
        if tract in outside:
            outside[tract] = outside[tract].reindex(
                index=outside[tract].index.union(bad.index),
                columns=outside[tract].columns.union(bad.columns), fill_value=False)
            aligned = bad.reindex(index=outside[tract].index, columns=outside[tract].columns, fill_value=False)
            outside[tract] = outside[tract] | aligned
        else:
            outside[tract] = bad
    return outside


def set_outside_brain(outside):
    """Register the locations sampled outside the brain; every table read afterwards has them as missing."""
    global _OUTSIDE_BRAIN
    _OUTSIDE_BRAIN = dict(outside or {})
    return sum(int(m.to_numpy().sum()) for m in _OUTSIDE_BRAIN.values())


def load_profile_table(path, exclude_ids=None, exclude_full=None):
    """Read a profile CSV, dropping excluded columns.

    *exclude_ids* drops by ``<subject>_<session>`` (any prefix; registration QC);
    *exclude_full* drops by exact ``<subject>_<session>_<prefix>`` identifier
    (a specific scan; preprocessing QC).

    The locations registered by ``set_outside_brain`` (sampled outside the brain, found on the other metrics of the
    same tract) are read as missing, so they take part in nothing that follows.
    """
    df = read_profile_table(path)
    tract = tract_and_metric(path)[0]
    mask = _OUTSIDE_BRAIN.get(tract)
    if mask is not None:
        aligned = mask.reindex(index=df.index, columns=df.columns, fill_value=False).fillna(False)
        df = df.mask(aligned.to_numpy(dtype=bool))
    if exclude_ids or exclude_full:
        drop = [c for c in df.columns
                if (exclude_ids and subject_session_of(c) in exclude_ids)
                or (exclude_full and c in exclude_full)]
        if drop:
            df = df.drop(columns=drop)
    return df


def write_metric_summaries(inputs, exclude_ids, out_dir, exclude_full=None):
    """Per-(tract, dataset) whole-tract summary of every metric.

    Writes ``summary_mean.csv`` and ``summary_median.csv`` under *out_dir*: each
    row is a (tract, dataset) pair, each metric column holds the mean (resp.
    median) of that profile along the tract's arc-length.
    """
    from collections import defaultdict

    means, medians, metrics_seen = defaultdict(dict), defaultdict(dict), set()
    for f in inputs:
        tract, metric = tract_and_metric(f)
        df = load_profile_table(f, exclude_ids, exclude_full)
        metrics_seen.add(metric)
        col_mean = df.mean(axis=0, skipna=True)
        col_median = df.median(axis=0, skipna=True)
        for dataset in df.columns:
            means[(tract, dataset)][metric] = col_mean[dataset]
            medians[(tract, dataset)][metric] = col_median[dataset]

    metric_cols = [m for m in METRIC_ORDER if m in metrics_seen] + sorted(metrics_seen - set(METRIC_ORDER))

    def to_frame(store):
        rows = []
        for (tract, dataset), vals in sorted(store.items()):
            toks = dataset.split("_")
            sub = toks[0] if len(toks) > 0 else ""
            ses = toks[1] if len(toks) > 1 else ""
            row = {"tract": tract, "dataset": dataset,
                   "sub": sub[len("sub-"):] if sub.startswith("sub-") else sub,
                   "ses": ses[len("ses-"):] if ses.startswith("ses-") else ses,
                   "prefix": "_".join(toks[2:])}
            row.update(vals)
            rows.append(row)
        return pd.DataFrame(rows).reindex(columns=["tract", "dataset", "sub", "ses", "prefix"] + metric_cols)

    os.makedirs(out_dir, exist_ok=True)
    to_frame(means).to_csv(os.path.join(out_dir, "summary_mean.csv"), index=False)
    to_frame(medians).to_csv(os.path.join(out_dir, "summary_median.csv"), index=False)
    return len(means)


def write_excluded_cases(reg_failed, prep_failed, groups, out_dir, filename="excluded_cases.csv"):
    """List every excluded case, one row each (registration, preprocessing and
    profile on separate rows), with sub/ses (prefixes stripped), prefix, tract,
    reason."""
    def strip(tok, pre):
        return tok[len(pre):] if tok.startswith(pre) else tok

    rows = []
    for ident in sorted(reg_failed):
        t = ident.split("_")
        rows.append({"sub": strip(t[0], "sub-"), "ses": strip(t[1], "ses-") if len(t) > 1 else "",
                     "prefix": "_".join(t[2:]), "tract": "", "reason": "registration"})
    for ident in sorted(prep_failed):
        t = ident.split("_")
        rows.append({"sub": strip(t[0], "sub-"), "ses": strip(t[1], "ses-") if len(t) > 1 else "",
                     "prefix": "_".join(t[2:]), "tract": "", "reason": "preprocessing"})
    if groups is not None:
        for _, g in groups[groups["is_outlier"]].sort_values(["tract", "subject_session"]).iterrows():
            t = str(g["subject_session"]).split("_")
            rows.append({"sub": strip(t[0], "sub-"), "ses": strip(t[1], "ses-") if len(t) > 1 else "",
                         "prefix": "_".join(t[2:]), "tract": g["tract"], "reason": "profile"})

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    pd.DataFrame(rows, columns=["sub", "ses", "prefix", "tract", "reason"]).to_csv(path, index=False)
    return path, len(rows)


def write_agebin_stats(inputs, bins, ddof, plots_dir=None, dpi=130, exclude_ids=None, exclude_full=None):
    """Write ``<...>_agebinstats.csv`` next to each table; optional per-tract plots.

    Returns (n_csv, n_plots).
    """
    by_tract: dict = {}
    for f in inputs:
        by_tract.setdefault(tract_and_metric(f)[0], []).append(f)
    if plots_dir:
        os.makedirs(plots_dir, exist_ok=True)

    n_csv = n_plots = 0
    for tract, files in sorted(by_tract.items()):
        stats = {}
        for csv_path in sorted(files):
            metric = tract_and_metric(csv_path)[1]
            out = process_table(load_profile_table(csv_path, exclude_ids, exclude_full), bins, ddof)
            out.to_csv(csv_path[: -len(".csv")] + OUTPUT_SUFFIX)
            stats[metric] = out
            n_csv += 1
        if plots_dir and stats:
            _plot_grid(tract, stats, bins, "meanstd",
                       os.path.join(plots_dir, f"{tract}_meanstd.png"), dpi)
            _plot_grid(tract, stats, bins, "percentiles",
                       os.path.join(plots_dir, f"{tract}_percentiles.png"), dpi)
            n_plots += 2
    return n_csv, n_plots


def bin_label_for_age(age, bins):
    """Return the bin label an age falls into, or None."""
    for lo, hi, label in bins:
        if lo <= age <= hi:
            return label
    return None


def prior_stats_index(prior_dir):
    """{(tract, metric): path} of the age bin stats under *prior_dir*, whichever layout they are in: they are written
    next to the tables they were computed from, so a normative set gathered first has them per tract and one computed
    straight from a run has them per metric. The names are read with tract_and_metric, which also puts the metric in
    the spelling used here (the run output writes FA, gather fa)."""
    index = _PRIOR_INDEX.get(prior_dir)
    if index is None:
        index = {}
        for path in sorted(glob.glob(os.path.join(prior_dir, "**", "*" + OUTPUT_SUFFIX), recursive=True)):
            index.setdefault(tract_and_metric(path[: -len(OUTPUT_SUFFIX)] + ".csv"), path)
        _PRIOR_INDEX[prior_dir] = index
        log.debug("%d prior stats table(s) under %s", len(index), prior_dir)
    return index


def find_prior_stats(prior_dir, tract, metric):
    """Locate the prior stats CSV for a (tract, metric); support nested/flat."""
    found = prior_stats_index(prior_dir).get((tract, metric))
    if found is not None:
        return found
    candidates = [
        os.path.join(prior_dir, tract, f"{tract}_{metric}{OUTPUT_SUFFIX}"),
        os.path.join(prior_dir, f"{tract}_{metric}{OUTPUT_SUFFIX}"),
        os.path.join(prior_dir, tract, f"{tract}_{metric}.csv"),
    ]
    return next((c for c in candidates if os.path.isfile(c)), None)


def pearson_columns(M: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Per-column Pearson r of each column of M (n x k) against ref (n,).

    Uses pairwise-complete masking (NaN in either side dropped per column);
    columns with < 3 valid points or zero variance return NaN.
    """
    R = np.broadcast_to(ref[:, None], M.shape)
    mask = np.isfinite(M) & np.isfinite(R)
    n = mask.sum(axis=0).astype(float)
    Mm = np.where(mask, M, 0.0)
    Rm = np.where(mask, R, 0.0)
    sx, sy = Mm.sum(0), Rm.sum(0)
    sxx, syy, sxy = (Mm * Mm).sum(0), (Rm * Rm).sum(0), (Mm * Rm).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sxy - sx * sy / n
        vx = sxx - sx * sx / n
        vy = syy - sy * sy / n
        r = cov / np.sqrt(vx * vy)
    r = np.where((n >= 3) & (vx > 0) & (vy > 0), r, np.nan)
    return r


def envelope_bounds(prior, label, cfg):
    """Per-arc-length (lo, hi) envelope from the prior stats, or None if absent.

    cfg['method'] == 'std'       -> mean +/- nsd * std
    cfg['method'] == 'percentile'-> [p<lo> .. p<hi>]
    """
    if cfg["method"] == "std":
        mk, sk = f"{label}_mean", f"{label}_std"
        if mk not in prior.columns or sk not in prior.columns:
            return None
        mean = prior[mk].to_numpy(dtype=float)
        std = prior[sk].to_numpy(dtype=float)
        return mean - cfg["nsd"] * std, mean + cfg["nsd"] * std
    lk, hk = f"{label}_p{cfg['pct_lo']}", f"{label}_p{cfg['pct_hi']}"
    if lk not in prior.columns or hk not in prior.columns:
        return None
    return prior[lk].to_numpy(dtype=float), prior[hk].to_numpy(dtype=float)


def fraction_inside(M: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    """Per-column (frac_inside, n_valid, n_inside) for positions within [lo, hi]."""
    Lo, Hi = lo[:, None], hi[:, None]
    valid = np.isfinite(M) & np.isfinite(Lo) & np.isfinite(Hi)
    inside = valid & (M >= Lo) & (M <= Hi)
    n_valid = valid.sum(axis=0)
    n_inside = inside.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(n_valid > 0, n_inside / n_valid, np.nan)
    return frac, n_valid.astype(int), n_inside.astype(int)


def estimate_batch_shifts(inputs, prior_dir, bins, mult_metrics, exclude_ids=None, exclude_full=None):
    """Robust batch shift of the testing population vs the normative reference.

    For each (metric, age-bin), pools across tracts the per-profile **median**
    residual to the normative centre (median/p50) and takes the median over
    profiles -- additive (``value - ref``) for FA-like metrics, multiplicative
    (``value / ref``) for diffusivities in *mult_metrics*.  Returns
    ``{(metric, bin): (kind, value, n_profiles)}`` with kind in {"add", "mul"}.
    This corrects a technical location offset between populations for the
    envelope (value) QC only; the shape QC is shift/scale invariant.
    """
    from collections import defaultdict

    per = defaultdict(list)
    for csv_path in inputs:
        tract, metric = tract_and_metric(csv_path)
        prior_path = find_prior_stats(prior_dir, tract, metric)
        if prior_path is None:
            continue
        df = load_profile_table(csv_path, exclude_ids, exclude_full)
        prior = pd.read_csv(prior_path, index_col=0).reindex(df.index)
        col_ages = {c: age_of(c) for c in df.columns}
        mult = metric in mult_metrics
        for lo, hi, label in bins:
            ref_key = f"{label}_p50" if f"{label}_p50" in prior.columns else f"{label}_mean"
            if ref_key not in prior.columns:
                continue
            ref = prior[ref_key].to_numpy(dtype=float)[:, None]
            cols = [c for c, a in col_ages.items() if a is not None and lo <= a <= hi]
            if not cols:
                continue
            M = df[cols].to_numpy(dtype=float)
            with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                if mult:
                    resid = np.where(np.isfinite(M) & np.isfinite(ref) & (ref > 0), M / ref, np.nan)
                else:
                    resid = np.where(np.isfinite(M) & np.isfinite(ref), M - ref, np.nan)
                prof_med = np.nanmedian(resid, axis=0)  # one robust residual per profile column
            per[(metric, label)].extend(prof_med[np.isfinite(prof_med)].tolist())

    shifts = {}
    for (metric, label), vals in per.items():
        arr = np.asarray(vals, dtype=float)
        if arr.size == 0:
            continue
        kind = "mul" if metric in mult_metrics else "add"
        shifts[(metric, label)] = (kind, float(np.median(arr)), int(arr.size))
    return shifts


def _apply_batch_shift(M, metric, label, batch_shifts):
    """Bring testing values into the normative frame for the envelope check."""
    if not batch_shifts or (metric, label) not in batch_shifts:
        return M
    kind, val, _ = batch_shifts[(metric, label)]
    if kind == "mul":
        return M / val if val not in (0.0,) else M
    return M - val


def compute_profile_qc(inputs, prior_dir, bins, corr_reference, envelope_cfg, exclude_ids=None,
                       exclude_full=None, batch_shifts=None):
    """Per-profile QC vs the age-appropriate prior reference.

    Returns a long-form DataFrame: tract, metric, subject_session, age, bin,
    r (Pearson vs prior mean/median -> shape), frac_inside (fraction of
    positions within the value envelope -> absolute values), n_valid.
    """
    ref_col = "mean" if corr_reference == "mean" else "p50"
    rows = []
    n_missing_prior = 0
    for csv_path in inputs:
        tract, metric = tract_and_metric(csv_path)
        prior_path = find_prior_stats(prior_dir, tract, metric)
        if prior_path is None:
            n_missing_prior += 1
            log.debug("no prior stats for (%s, %s); skipping", tract, metric)
            continue
        df = load_profile_table(csv_path, exclude_ids, exclude_full)
        prior = pd.read_csv(prior_path, index_col=0).reindex(df.index)

        col_ages = {c: age_of(c) for c in df.columns}
        for lo, hi, label in bins:
            ref_key = f"{label}_{ref_col}"
            if ref_key not in prior.columns:
                log.debug("prior %s lacks column '%s'; skipping bin", prior_path, ref_key)
                continue
            ref_vec = prior[ref_key].to_numpy(dtype=float)
            env = envelope_bounds(prior, label, envelope_cfg)
            cols = [c for c, a in col_ages.items() if a is not None and lo <= a <= hi]
            if not cols:
                continue
            M = df[cols].to_numpy(dtype=float)
            ## how much of the profile is there at all: independent of the envelope, which is undefined where the
            ## prior has no std (a bin with one subject) and would otherwise look like missing data
            present = np.isfinite(M).sum(axis=0)
            r = pearson_columns(M, ref_vec)  # shape: shift/scale invariant, uses raw M
            if env is not None:
                M_env = _apply_batch_shift(M, metric, label, batch_shifts)
                frac, nval, nin = fraction_inside(M_env, env[0], env[1])
            else:
                frac = np.full(len(cols), np.nan)
                nval = np.zeros(len(cols), dtype=int)
                nin = np.zeros(len(cols), dtype=int)
            n_positions = int(len(df.index)) # the arc length grid: how many positions the profile could have
            for i, c in enumerate(cols):
                rows.append((tract, metric, c, col_ages[c], label, r[i], frac[i], int(nval[i]), int(nin[i]),
                             int(present[i]), n_positions))
    if n_missing_prior:
        log.warning("%d (tract,metric) tables had no matching prior stats", n_missing_prior)
    return pd.DataFrame(
        rows,
        columns=["tract", "metric", "subject_session", "age", "bin", "r", "frac_inside", "n_valid", "n_inside",
                 "n_present", "n_positions"],
    )


def detect_group_outliers(qc, value_min_inside, shape_method, corr_min, corr_iqr_k,
                          shape_metric, exclude_metrics=(), min_valid_frac=0.75):
    """Decide outliers per (tract, subject_session) -- jointly over metrics.

    Because all of a tract's metrics are extracted from the same tract data, the
    decision is made once per (tract, subject_session) and applies to every
    metric of that tract:

    (1) value: pool the in-envelope / valid counts over the CONTRIBUTING metrics
        (all metrics except *exclude_metrics*, e.g. FWF) into one joint
        fraction; flag if it is below *value_min_inside*.
    (2) shape: use only the *shape_metric* (FA) correlation, since flat metrics
        carry little shape information; flag by a fixed threshold or a robust
        per-(tract,bin) Q1 - k*IQR fence.

    Excluded metrics do not influence the decision, but the resulting flags
    still cover them (the caller applies the group decision to every metric).
    Returns a per-group DataFrame with the joint measures and flags.
    """
    exclude = set(exclude_metrics)

    # canonical set of groups (independent of exclusions)
    groups = qc.groupby(["tract", "subject_session"], as_index=False).agg(
        age=("age", "first"), bin=("bin", "first"))

    # (1) joint value fraction pooled over contributing metrics only
    val_src = qc[~qc["metric"].isin(exclude)]
    vagg = val_src.groupby(["tract", "subject_session"], as_index=False).agg(
        n_inside=("n_inside", "sum"), n_valid=("n_valid", "sum"), n_present=("n_present", "sum"),
        n_positions=("n_positions", "sum"))
    groups = groups.merge(vagg, on=["tract", "subject_session"], how="left")
    cols = ["n_inside", "n_valid", "n_present", "n_positions"]
    groups[cols] = groups[cols].fillna(0)
    groups["joint_frac_inside"] = np.where(
        groups["n_valid"] > 0, groups["n_inside"] / groups["n_valid"], np.nan)
    ## how much of the profile is there at all: missing values, and the locations dropped because the fibers were
    ## sampled outside the brain. Too little of it and the profile is an outlier rather than a clean one -- without
    ## this a profile that is missing everywhere passes, since every comparison with it is undefined. It counts the
    ## values, not the comparisons: where the prior has no envelope (a bin with one subject) nothing is comparable,
    ## which says nothing about the profile.
    groups["frac_valid"] = np.where(
        groups["n_positions"] > 0, groups["n_present"] / groups["n_positions"], np.nan)
    too_empty = (groups["frac_valid"] < min_valid_frac).fillna(True) if min_valid_frac > 0 else False
    groups["is_value_outlier"] = (groups["joint_frac_inside"] < value_min_inside).fillna(False) | too_empty

    # (2) shape from the chosen metric (FA) only
    fa = qc[qc["metric"] == shape_metric][["tract", "subject_session", "bin", "r"]].copy()
    fa = fa.rename(columns={"r": "shape_r"})
    if shape_method == "iqr":
        grp = fa.groupby(["tract", "bin"])["shape_r"]
        q1 = grp.transform(lambda s: s.quantile(0.25))
        q3 = grp.transform(lambda s: s.quantile(0.75))
        fa["is_shape_outlier"] = (fa["shape_r"] < (q1 - corr_iqr_k * (q3 - q1))).fillna(False)
    else:
        fa["is_shape_outlier"] = (fa["shape_r"] < corr_min).fillna(False)

    groups = groups.merge(fa[["tract", "subject_session", "shape_r", "is_shape_outlier"]],
                          on=["tract", "subject_session"], how="left")
    groups["is_shape_outlier"] = groups["is_shape_outlier"].fillna(False)
    groups["is_outlier"] = groups["is_value_outlier"] | groups["is_shape_outlier"]
    return groups


def _arc_value(text):
    """The arc length a field holds, or None. The tables are written with one decimal representation per grid, so the
    value parsed here is the one pandas parsed when the locations outside the brain were found."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _outside_lookup(mask):
    """{case: {arc lengths}} of the locations to blank, from a mask of find_outside_brain."""
    lookup = {}
    if mask is None:
        return lookup
    for column in mask.columns:
        marked = mask.index[mask[column].to_numpy(dtype=bool)]
        if len(marked):
            lookup[str(column)] = set(marked.tolist())
    return lookup


def write_without_columns(in_path, out_path, drop_names, drop_subject_sessions=()):
    """Copy a profile CSV dropping the given identifier columns (by exact name or
    by subject_session); retained cells are preserved byte-for-byte.

    A table holding one row per case (first column ``case_id``, EXTRACT_Profile with ``resultCaseColumnwise`` false)
    has those rows dropped instead.

    The cells at the locations sampled outside the brain (``set_outside_brain``) are written empty, so the cleaned
    tables hold what the QC used rather than the zeros it ignored. Returns the number of cells blanked.
    """
    dss = set(drop_subject_sessions)
    lines = open(in_path).read().splitlines()
    header = lines[0].split(",")
    outside = _outside_lookup(_OUTSIDE_BRAIN.get(tract_and_metric(in_path)[0]))
    blanked = 0

    def dropped(name):
        return name in drop_names or subject_session_of(name) in dss

    def is_outside(case, arc):
        return arc is not None and arc in outside.get(case, ())

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if header and header[0].strip() == CASE_COLUMN:
        arcs = [_arc_value(h) for h in header[1:]] # one arc length per column
        with open(out_path, "w") as fh:
            fh.write(lines[0] + "\n")
            for line in lines[1:]:
                parts = line.split(",")
                if dropped(parts[0]):
                    continue
                for i, arc in enumerate(arcs, start=1):
                    if i < len(parts) and is_outside(parts[0], arc):
                        parts[i] = ""
                        blanked += 1
                fh.write(",".join(parts) + "\n")
        return blanked
    keep = [i for i, name in enumerate(header) if i == 0 or not dropped(name)]
    with open(out_path, "w") as fh:
        fh.write(",".join(header[i] for i in keep) + "\n")
        for line in lines[1:]:
            parts = line.split(",")
            arc = _arc_value(parts[0]) # the row is one arc length
            row = []
            for i in keep:
                value = parts[i] if i < len(parts) else ""
                if i and is_outside(header[i], arc):
                    value = ""
                    blanked += 1
                row.append(value)
            fh.write(",".join(row) + "\n")
    return blanked


def plot_excluded_profiles(inputs, prior_dir, bins, envelope_cfg, prof_outliers_by_tract,
                           reg_ss, full_excl, batch_shifts, out_dir, dpi):
    """Per tract: FA/MD/RD/AD subplots of the normative mean+envelope (per age bin)
    with every excluded profile overlaid (colour = bin, solid = profile-QC
    outlier, dashed = registration/preprocessing exclusion)."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    by_tract = {}
    for f in inputs:
        tract, metric = tract_and_metric(f)
        by_tract.setdefault(tract, {})[metric] = f

    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for tract, mpaths in sorted(by_tract.items()):
        avail = [m for m in DIFFUSION_METRICS if m in mpaths]
        if not avail:
            continue
        cols0 = load_profile_table(mpaths[avail[0]]).columns
        prof_set = prof_outliers_by_tract.get(tract, set())
        excl = [c for c in cols0
                if c in prof_set or subject_session_of(c) in reg_ss or c in full_excl]
        if not excl:
            continue

        n_metrics, n_bins = len(DIFFUSION_METRICS), len(bins)
        fig, axes = plt.subplots(n_metrics, n_bins, figsize=(4.0 * n_bins, 2.8 * n_metrics),
                                 squeeze=False, sharex=True, sharey="row")
        for r, metric in enumerate(DIFFUSION_METRICS):
            if metric not in mpaths:
                for c in range(n_bins):
                    axes[r][c].set_visible(False)
                continue
            df = load_profile_table(mpaths[metric])
            x = df.index.to_numpy(dtype=float)
            prior_path = find_prior_stats(prior_dir, tract, metric)
            prior = pd.read_csv(prior_path, index_col=0).reindex(df.index) if prior_path else None
            for c, (_, _, label) in enumerate(bins):
                ax = axes[r][c]
                color = BIN_COLORS[c % len(BIN_COLORS)]
                if prior is not None and f"{label}_mean" in prior.columns:
                    ax.plot(x, prior[f"{label}_mean"].to_numpy(dtype=float), color=color, lw=1.4, zorder=3)
                    env = envelope_bounds(prior, label, envelope_cfg)
                    if env is not None:
                        ax.fill_between(x, env[0], env[1], color=color, alpha=0.13, linewidth=0, zorder=1)
                n_cell = 0
                for col in excl:
                    if col not in df.columns or bin_label_for_age(age_of(col), bins) != label:
                        continue
                    v = df[col].to_numpy(dtype=float)
                    v = _apply_batch_shift(v[:, None], metric, label, batch_shifts)[:, 0]
                    ax.plot(x, v, color=color, lw=0.7, alpha=0.75,
                            ls="-" if col in prof_set else "--", zorder=2)
                    n_cell += 1
                if n_cell:
                    ax.text(0.02, 0.96, f"n={n_cell}", transform=ax.transAxes, va="top", fontsize=7, color="#333")
                if r == 0:
                    ax.set_title(label, fontsize=11)
                if c == 0:
                    ax.set_ylabel(metric, fontsize=10)
                if r == n_metrics - 1:
                    ax.set_xlabel("Arc length", fontsize=8)
                ax.tick_params(labelsize=7)
                ax.margins(x=0)

        handles = [Line2D([0], [0], color="#444444", lw=1, ls="-", label="profile-QC outlier"),
                   Line2D([0], [0], color="#444444", lw=1, ls="--", label="reg/prep excluded")]
        fig.legend(handles=handles, loc="lower center", ncol=2, fontsize=8, frameon=False)
        corr = " (batch-corrected)" if batch_shifts else ""
        fig.suptitle(f"{tract} — {len(excl)} excluded profiles vs normative mean ± envelope "
                     f"(rows: metric, cols: age bin){corr}", fontsize=12)
        fig.tight_layout(rect=(0, 0.04, 1, 0.96))
        fig.savefig(os.path.join(out_dir, f"{tract}_excluded_profiles.png"), dpi=dpi)
        plt.close(fig)
        written += 1
    return written


def _corr_violin_figure(sub_df, title, out_path, reference, dpi):
    """One large box+violin figure of per-tract correlation for a data subset."""
    import matplotlib.pyplot as plt

    tracts = sorted(sub_df["tract"].unique())
    data, labels, excluded = [], [], []
    for t in tracts:
        vals = sub_df.loc[sub_df["tract"] == t, "r"].to_numpy(dtype=float)
        vals = vals[np.isfinite(vals)]
        if vals.size >= 2:
            data.append(vals)
            labels.append(t)
        else:
            excluded.append(t)
    if excluded:
        log.debug("%s: %d tracts excluded (too few values)", title, len(excluded))
    if not data:
        return False

    pos = np.arange(1, len(data) + 1)
    fig, ax = plt.subplots(figsize=(max(14.0, 0.42 * len(data)), 8.0))
    vp = ax.violinplot(data, positions=pos, showextrema=False, widths=0.85)
    for body in vp["bodies"]:
        body.set_facecolor("#4C72B0")
        body.set_alpha(0.35)
        body.set_edgecolor("#33528a")
    ax.boxplot(
        data, positions=pos, widths=0.28, showfliers=False, patch_artist=True,
        medianprops=dict(color="#C44E52", linewidth=1.4),
        boxprops=dict(facecolor="white", alpha=0.9, edgecolor="#333333"),
        whiskerprops=dict(color="#333333"), capprops=dict(color="#333333"),
    )
    ax.set_xticks(pos)
    ax.set_xticklabels(labels, rotation=90, fontsize=7)
    ax.set_ylabel(f"Pearson r  (profile vs prior {reference})", fontsize=11)
    ax.set_xlabel("Tract", fontsize=11)
    ax.set_title(title, fontsize=13)
    ax.axhline(1.0, color="#999999", lw=0.6, ls=":")
    ax.set_ylim(0.0, 1.0)
    ax.grid(axis="y", alpha=0.25)
    ax.margins(x=0.005)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return True


def plot_correlations_by_metric_bin(corr_df, out_dir, reference, dpi, bins):
    """One large per-tract box+violin figure for each (metric, age-bin)."""
    metrics = ordered_metrics(corr_df["metric"].unique())
    written = 0
    for metric in metrics:
        for _, _, label in bins:
            sub = corr_df[(corr_df["metric"] == metric) & (corr_df["bin"] == label)]
            n_valid = int(sub["r"].notna().sum())
            if n_valid == 0:
                continue
            n_tracts = sub.loc[sub["r"].notna(), "tract"].nunique()
            title = (f"{metric} — {label}: per-tract profile↔prior-{reference} correlation "
                     f"({n_valid} profiles, {n_tracts} tracts)")
            out_path = os.path.join(out_dir, f"correlation_qc_{reference}_{metric}_{label}.png")
            if _corr_violin_figure(sub, title, out_path, reference, dpi):
                written += 1
    return written


def configure_parser(p):
    p.add_argument("--profiles-dir", default="Profiles",
                   help="Root with the profile tables: gathered (<tract>/<tract>_<metric>.csv) or the "
                        "EXTRACT_Profile output of a run (<metric>/<tract>_<metric>.csv)")
    p.add_argument("--plots-dir", default="StatPlots", help="Output folder for QC plots")
    p.add_argument("--keep-outside-brain", action="store_true",
                   help="Keep the profile locations that a metric reports as 0 (fibers sampled outside the brain "
                        "mask); by default they are read as missing on every metric of that tract and case")
    p.add_argument("--min-valid-frac", type=float, default=0.75,
                   help="A profile with a smaller fraction of usable positions (missing, or sampled outside the "
                        "brain) is an outlier: too little of it is left to judge (0 disables; default: %(default)s)")
    p.add_argument("--zero-valid-metrics", default=",".join(sorted(ZERO_VALID_METRICS)),
                   help="Metrics in which 0 is a valid measurement, so it does not mark the location as outside "
                        "the brain (default: %(default)s)")
    p.add_argument("--bins", default="0-3,4-9,10-60", help="Age bins in months, inclusive; oldest is open-ended")
    p.add_argument("--ddof", type=int, default=1, help="Delta d.o.f. for std (1=sample, 0=population; default: 1)")
    p.add_argument("--dpi", type=int, default=130, help="Plot resolution (default: 130)")
    p.add_argument("--no-plots", action="store_true", help="Only write CSVs, skip plots")
    p.add_argument("--prior-stats-dir", default=None,
                   help="Folder of prior computed stats (e.g. ProfileQCStats); enables profile-to-prior "
                        "correlation QC")
    p.add_argument("--registration-qc", default=None,
                   help="Registration-QC folder (or registration_qc.csv). Subject-sessions flagged there are "
                        "removed from ALL tracts/metrics before any stats or profile QC")
    p.add_argument("--prep-qc", default=None,
                   help="Reformatted preprocessing-QC CSV (or its folder). Scans failing motion/artifact "
                        "thresholds are removed (by full sub_ses_prefix identifier) before any computation")
    p.add_argument("--prep-excluded-frac", type=float, default=0.20,
                   help="Fail a scan if excluded gradients > this fraction of the original (default: 0.20)")
    p.add_argument("--prep-rms2-frac", type=float, default=0.20,
                   help="Fail a scan if rms_larger_than_2 > this fraction of remaining gradients (default: 0.20)")
    p.add_argument("--corr-reference", default="mean", choices=["mean", "median"],
                   help="Prior reference to correlate each profile against (default: mean)")
    # (1) value / absolute-magnitude outliers
    p.add_argument("--value-envelope", default="std", choices=["std", "percentile"],
                   help="Reference envelope for value outliers: mean+/-k*std, or a percentile band (default: std)")
    p.add_argument("--value-nsd", type=float, default=3.0,
                   help="k for the mean +/- k*std envelope (default: 3)")
    p.add_argument("--value-pct-lo", type=int, default=5,
                   help="Lower percentile for the percentile envelope (default: 5)")
    p.add_argument("--value-pct-hi", type=int, default=95,
                   help="Upper percentile for the percentile envelope (default: 95)")
    p.add_argument("--value-min-inside", type=float, default=0.9,
                   help="A profile is a value outlier if the fraction of positions inside the envelope "
                        "is below this (default: 0.9)")
    p.add_argument("--envelope-batch-correct", action="store_true",
                   help="Correct a batch shift (testing vs normative) before the value/envelope QC: a robust "
                        "median shift per (metric, age-bin), additive for FA-like metrics and multiplicative "
                        "for diffusivities. Does NOT affect the shape/correlation QC")
    p.add_argument("--batch-mult-metrics", default="md,rd,ad",
                   help="Metrics corrected multiplicatively (others additively) under --envelope-batch-correct "
                        "(default: md,rd,ad)")
    # (2) shape / anatomy outliers (correlation to reference profile)
    p.add_argument("--shape-outlier-method", default="threshold", choices=["threshold", "iqr"],
                   help="Flag shape outliers by a fixed correlation threshold, or a robust per-group "
                        "Q1-k*IQR fence (default: threshold)")
    p.add_argument("--corr-min", type=float, default=0.5,
                   help="Shape outlier if correlation r < this (threshold method; default: 0.5)")
    p.add_argument("--corr-iqr-k", type=float, default=1.5,
                   help="Shape outlier if r < Q1 - k*IQR within each (tract,bin) (iqr method; default: 1.5)")
    p.add_argument("--shape-metric", default="fa",
                   help="Metric whose correlation drives the shape QC (default: fa)")
    p.add_argument("--outlier-exclude-metrics", default="FWF",
                   help="Comma-separated metrics excluded from the (value) outlier computation but still "
                        "having the decision applied to them (default: FWF; '' to use all)")
    p.add_argument("--clean-dir", default=None,
                   help="If given, drop outlier (subject-session, tract) profiles from ALL of that tract's "
                        "metric tables and write cleaned profiles to this folder")
    p.add_argument("--clean-plots-dir", default="StatsPlots_Clean",
                   help="Folder for the recomputed cleaned-data plots (default: StatsPlots_Clean)")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return p


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    configure_parser(p)
    args = p.parse_args(argv)
    return run_args(args, p)


def run_args(args, p) -> int:
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)

    if not os.path.isdir(args.profiles_dir):
        p.error(f"profiles dir not found: {args.profiles_dir}")

    if not args.no_plots:
        import matplotlib
        matplotlib.use("Agg")

    bins = parse_bins(args.bins)
    log.info("Age bins (inclusive months, oldest open-ended): %s",
             [lbl for _, _, lbl in bins])

    inputs = select_inputs(args.profiles_dir)
    log.info("Found %d metric tables under %s", len(inputs), args.profiles_dir)
    if inputs and all(is_run_output_table(f) for f in inputs):
        log.info("These are the per property tables of an EXTRACT_Profile run (the tract is the file name, the "
                 "folder the metric)")

    # locations where the fibers left the brain mask: 0 in a metric that cannot be 0 in tissue
    if args.keep_outside_brain:
        set_outside_brain({})
    else:
        zero_valid = {m.strip() for m in args.zero_valid_metrics.split(",") if m.strip()}
        outside = find_outside_brain(inputs, zero_valid)
        n_cells = set_outside_brain(outside)
        if n_cells:
            profiles = sum(int((m.to_numpy().sum(axis=0) > 0).sum()) for m in outside.values())
            emptied = sum(int((m.to_numpy().all(axis=0)).sum()) for m in outside.values())
            log.info("Sampled outside the brain (0 in %s): %d location(s) of %d profile(s) in %d tract(s) are read "
                     "as missing on every metric%s", "/".join(sorted({m for m in (tract_and_metric(f)[1] for f in inputs)
                                                                      if m not in zero_valid})) or "-",
                     n_cells, profiles, len(outside),
                     "; %d profile(s) keep no location at all" % emptied if emptied else "")

    # Scans that failed upstream QC are removed up front.
    reg_failed = set()
    if args.registration_qc:
        reg_failed = load_registration_failures(args.registration_qc)
        log.info("Registration QC: removing %d failed case(s) before all computations: %s",
                 len(reg_failed), ", ".join(sorted(reg_failed)) if reg_failed else "(none)")
    # registration ids may be session-level (sub_ses) or per-scan (sub_ses_prefix)
    reg_ss = {i for i in reg_failed if len(i.split("_")) <= 2}       # drop all prefixes of the session
    reg_full = {i for i in reg_failed if len(i.split("_")) > 2}      # drop the specific scan
    prep_failed = set()
    if args.prep_qc:
        prep_failed = load_prep_failures(args.prep_qc, args.prep_excluded_frac, args.prep_rms2_frac)
        log.info("Preprocessing QC: removing %d failed scan(s) (excluded>%.0f%% of orig OR rms>2>%.0f%% of "
                 "remaining)", len(prep_failed), 100 * args.prep_excluded_frac, 100 * args.prep_rms2_frac)
    full_excl = prep_failed | reg_full  # exclusions matched by exact sub_ses_prefix identifier

    plots_root = args.plots_dir
    plots_sub = None if args.no_plots else os.path.join(plots_root, "Plots")
    n_csv, n_plots = write_agebin_stats(inputs, bins, args.ddof, plots_sub, args.dpi,
                                        exclude_ids=reg_ss, exclude_full=full_excl)
    log.info("Wrote %d age-bin stats CSVs and %d plots%s.",
             n_csv, n_plots, "" if args.no_plots else f" under {plots_sub}/")

    # per-(tract, dataset) whole-tract metric summaries (mean, median)
    n_sum = write_metric_summaries(inputs, reg_ss, plots_root, exclude_full=full_excl)
    log.info("Wrote metric summaries (mean, median) for %d (tract,dataset) rows under %s/", n_sum, plots_root)

    # --- optional: profile QC / outlier detection vs prior reference -------
    groups = None
    if args.prior_stats_dir:
        if not os.path.isdir(args.prior_stats_dir):
            p.error(f"prior stats dir not found: {args.prior_stats_dir}")
        for pct in (args.value_pct_lo, args.value_pct_hi):
            if args.value_envelope == "percentile" and pct not in PERCENTILES:
                p.error(f"--value-pct-* must be one of {PERCENTILES}; got {pct}")

        env_cfg = {"method": args.value_envelope, "nsd": args.value_nsd,
                   "pct_lo": args.value_pct_lo, "pct_hi": args.value_pct_hi}
        env_desc = (f"mean±{args.value_nsd:g}·std" if args.value_envelope == "std"
                    else f"p{args.value_pct_lo}..p{args.value_pct_hi}")
        log.info("Profile QC vs prior '%s': shape=corr-to-%s, value-envelope=%s",
                 args.prior_stats_dir, args.corr_reference, env_desc)

        exclude_metrics = {m.strip() for m in args.outlier_exclude_metrics.split(",") if m.strip()}
        if exclude_metrics:
            log.info("Metrics excluded from outlier computation (decision still applied): %s",
                     sorted(exclude_metrics))

        batch_shifts = None
        if args.envelope_batch_correct:
            mult_metrics = {m.strip() for m in args.batch_mult_metrics.split(",") if m.strip()}
            batch_shifts = estimate_batch_shifts(inputs, args.prior_stats_dir, bins, mult_metrics,
                                                 exclude_ids=reg_ss, exclude_full=full_excl)
            log.info("Envelope batch correction (testing vs normative), robust median shift per (metric, bin):")
            os.makedirs(plots_root, exist_ok=True)
            brows = []
            for (metric, label), (kind, val, n) in sorted(batch_shifts.items()):
                desc = f"{val:+.4g}" if kind == "add" else f"×{val:.4g}"
                log.info("  %-4s [%s]: %s %s (n=%d profiles)", metric, label, kind, desc, n)
                brows.append({"metric": metric, "bin": label, "kind": kind, "shift": val, "n_profiles": n})
            pd.DataFrame(brows).to_csv(os.path.join(plots_root, f"batch_shifts_{args.corr_reference}.csv"),
                                       index=False)

        qc = compute_profile_qc(inputs, args.prior_stats_dir, bins, args.corr_reference, env_cfg,
                                exclude_ids=reg_ss, exclude_full=full_excl, batch_shifts=batch_shifts)
        groups = detect_group_outliers(qc, args.value_min_inside, args.shape_outlier_method,
                                       args.corr_min, args.corr_iqr_k, args.shape_metric, exclude_metrics,
                                       args.min_valid_frac)

        os.makedirs(plots_root, exist_ok=True)
        # per-metric detail (correlations, envelope fractions) + the group flags
        qc_out = qc.merge(
            groups[["tract", "subject_session", "joint_frac_inside", "shape_r",
                    "is_value_outlier", "is_shape_outlier", "is_outlier"]],
            on=["tract", "subject_session"], how="left",
        )
        qc_csv = os.path.join(plots_root, f"profile_qc_{args.corr_reference}.csv")
        qc_out.to_csv(qc_csv, index=False)
        grp_csv = os.path.join(plots_root, f"outliers_{args.corr_reference}.csv")
        groups.to_csv(grp_csv, index=False)

        ng = len(groups)
        nv = int(groups["is_value_outlier"].sum())
        ns = int(groups["is_shape_outlier"].sum())
        na = int(groups["is_outlier"].sum())
        shape_desc = (f"{args.shape_metric} r<{args.corr_min:g}" if args.shape_outlier_method == "threshold"
                      else f"{args.shape_metric} r<Q1-{args.corr_iqr_k:g}·IQR")
        log.info("(subject-session, tract) groups: %d", ng)
        log.info("  value outliers (joint <%.0f%% inside %s): %d (%.1f%%)",
                 100 * args.value_min_inside, env_desc, nv, 100 * nv / max(ng, 1))
        log.info("  shape outliers (%s): %d (%.1f%%)", shape_desc, ns, 100 * ns / max(ng, 1))
        log.info("  any outlier: %d (%.1f%%)", na, 100 * na / max(ng, 1))
        log.info("Wrote %s and %s", qc_csv, grp_csv)

        if plots_sub and int(qc["r"].notna().sum()):
            n_fig = plot_correlations_by_metric_bin(qc, plots_sub, args.corr_reference, args.dpi, bins)
            log.info("Wrote %d correlation QC plots (one per metric x age-bin) under %s/",
                     n_fig, plots_sub)

        # --- per-tract review figures: excluded profiles vs mean+envelope --
        if plots_sub:
            prof_outliers_by_tract = (groups[groups["is_outlier"]]
                                      .groupby("tract")["subject_session"].apply(set).to_dict())
            excl_dir = os.path.join(plots_sub, "excluded")
            n_excl = plot_excluded_profiles(inputs, args.prior_stats_dir, bins, env_cfg,
                                            prof_outliers_by_tract, reg_ss, full_excl, batch_shifts,
                                            excl_dir, args.dpi)
            log.info("Wrote %d excluded-profile review plots under %s/", n_excl, excl_dir)

        # --- apply outliers -> cleaned profiles + recomputed stats ---------
        if args.clean_dir:
            drop_by_tract = (groups[groups["is_outlier"]]
                             .groupby("tract")["subject_session"].apply(set).to_dict())
            n_dropped_cols = 0
            n_blanked = 0
            clean_tables = []
            for f in inputs:
                tract = tract_and_metric(f)[0]
                drop = drop_by_tract.get(tract, set()) | full_excl
                rel = os.path.relpath(f, args.profiles_dir)
                clean_path = os.path.join(args.clean_dir, rel)
                n_blanked += write_without_columns(f, clean_path, drop, drop_subject_sessions=reg_ss)
                clean_tables.append(clean_path)
                n_dropped_cols += len(drop)
            log.info("Wrote cleaned profiles to %s/ (removed profile-QC outliers + %d registration-failed "
                     "subject-sessions + %d preprocessing-failed scans across %d tables%s)",
                     args.clean_dir, len(reg_failed), len(prep_failed), len(inputs),
                     "; %d cell(s) sampled outside the brain written empty" % n_blanked if n_blanked else "")

            # recompute age-bin stats (+ plots) on the cleaned data
            clean_root = args.clean_plots_dir
            clean_sub = None if args.no_plots else os.path.join(clean_root, "Plots")
            c_csv, c_plots = write_agebin_stats(clean_tables, bins, args.ddof, clean_sub, args.dpi)
            log.info("Recomputed %d age-bin stats CSVs on cleaned data under %s/%s", c_csv, args.clean_dir,
                     "" if clean_sub is None else f"; wrote {c_plots} plots under {clean_sub}/")

            # cleaned-data metric summaries (mean, median)
            write_metric_summaries(clean_tables, None, clean_root)
            log.info("Wrote cleaned-data metric summaries (mean, median) under %s/", clean_root)

            # cleaned-data correlation QC: profile_qc CSV always, plots when enabled
            qc_clean = compute_profile_qc(clean_tables, args.prior_stats_dir, bins, args.corr_reference, env_cfg,
                                          batch_shifts=batch_shifts)
            os.makedirs(clean_root, exist_ok=True)
            clean_qc_csv = os.path.join(clean_root, f"profile_qc_{args.corr_reference}.csv")
            qc_clean.to_csv(clean_qc_csv, index=False)
            log.info("Wrote cleaned-data %s", clean_qc_csv)
            if clean_sub and int(qc_clean["r"].notna().sum()):
                n_cfig = plot_correlations_by_metric_bin(qc_clean, clean_sub, args.corr_reference, args.dpi, bins)
                log.info("Wrote %d cleaned-data correlation QC plots under %s/", n_cfig, clean_sub)

    # --- log of excluded cases (registration + preprocessing + profile) ----
    n_prof_out = int(groups["is_outlier"].sum()) if groups is not None else 0
    if reg_failed or prep_failed or n_prof_out:
        exc_path, n_exc = write_excluded_cases(reg_failed, prep_failed, groups, plots_root)
        log.info("Wrote %d excluded-case rows (%d registration, %d preprocessing, %d profile) to %s",
                 n_exc, len(reg_failed), len(prep_failed), n_prof_out, exc_path)

    return 0


### dmrifiberprofile command

def add_parser(subparsers):
    p = subparsers.add_parser("qc-profiles", help="Age-binned profile statistics, QC plots and profile outlier QC", description=__doc__,
                              formatter_class=argparse.RawDescriptionHelpFormatter)
    configure_parser(p)
    p.set_defaults(func=lambda args: run_args(args, p))


if __name__ == "__main__":
    sys.exit(main())
