#
#   fiberprofile/analysis/impute_profiles.py
#
#   Impute the missing values of along-tract profile tables (e.g. Profiles_Clean of qc-profiles) from the observed
#   values of the same scan. Every profile location (tract, arc length) has a 3-D position in atlas space, the point
#   of the tract axis (<axis-dir>/<tract>_axis.vtk from compute-axis) at that arc length; the tracts are dense in the
#   brain, so a missing location has observed neighbours in other tracts of the same scan.
#
#   Missing values are blank cells (e.g. the locations sampled outside the brain) and whole profiles: a scan that has
#   tables for other tracts but is absent from the table of a tract (the profiles qc-profiles excluded). Both are
#   treated the same. A scan absent from every table has nothing to impute from.
#
#   Methods (each scan and metric on its own; no information of other scans):
#     arc-linear   linear along the arc length of the same profile, gaps up to --max-gap mm
#     linear       linear in 3-D over the observed locations of all tracts (Delaunay tetrahedra)
#     knn          mean of the --k nearest observed locations in 3-D (inverse distance weights by default)
#     siren        a SIREN (sine network) per scan, all metrics jointly, on the 3-D position (and arc length or the
#                  tract, --siren-inputs); GPU when there is one
#
#   With a normative prior (--prior-stats-dir, the age bin statistics of qc-profiles, and the ages of the scans), a
#   method imputes the deviations of the scan from the norm of its age bin instead of its values (--relative-to-prior):
#   z = (value - mean) / SD at each location, imputed, then back to values with the norm of the missing location.
#   prior-mean imputes the norm itself (the mean of the scan's age bin), also for a metric the scan lacks entirely.
#
#   population is a probabilistic PCA of the deviations of a normative cohort, over all tracts and metrics jointly: a
#   scan's observed deviations give the mean and SD of each missing cell, also of a metric it lacks entirely. With
#   --norm population (the default with a prior), the methods above impute the deviations from that prediction (the
#   residuals) within --max-distance, and population fills the rest.
#
#   --validate hides observed values (gaps within profiles and whole profiles) of a sample of scans, imputes them with
#   the methods and settings to compare, and reports the errors.
#

import argparse
import json
import logging
import math
import os
import re
import time
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd

log = logging.getLogger("impute")

METHODS = ("arc-linear", "linear", "knn", "siren", "prior-mean", "population")
SPATIAL = ("linear", "knn", "siren")  # methods that need the 3-D positions (--axis-dir)
BY_NORM = ("prior-mean", "population")  # methods on the norm, also for a metric a scan lacks entirely
DEFAULT_BINS = "0-3,4-9,10-60"  # as qc-profiles --bins
SIREN_INPUTS = ("xyz", "xyz+arc", "xyz+tract")
METRIC_ORDER = ["fa", "md", "rd", "ad", "NDI", "ODI", "FWF", "FW_FA", "FW_MD", "FW_RD", "FW_AD"]
GAP, END, WHOLE, REGION, MEASURE = "gap", "end gap", "whole profile", "region", "whole measure"
PATTERNS = (GAP, END, WHOLE, REGION, MEASURE)
SHORT = {GAP: "gap", END: "end", WHOLE: "whole", REGION: "region", MEASURE: "measure"}
NOISE = ("isotropic", "metric", "diagonal")  # population: noise model of the probabilistic PCA
NORMS = ("population", "age-bin")  # what the deviations of --relative-to-prior are from
POPULATION_DEFAULTS = {"components": 80, "noise": "isotropic"}
# validation: families of metrics a scan lacks together (no free water or NODDI fit), hidden as a whole measure
FAMILIES = {"dti": ("FA", "MD", "RD", "AD"), "fw": ("FWFA", "FWMD", "FWRD", "FWAD"), "fwf": ("FWF",),
            "noddi": ("NDI", "ODI")}
ARC_ENDS = ("none", "constant", "linear")
REFERENCE = "reference"  # validation: the cohort mean at each location (other scans), as a scale for the errors
# validation: distance (mm) from a hidden value to the nearest observed position of the same metric, bin edges
DISTANCE_BINS = [0.0, 2.0, 4.0, 6.0, 10.0, 15.0, 20.0, 25.0, np.inf]
# validation: a region may hide at most this share of a scan's observed tracts (else another center is drawn)
REGION_MAX_SHARE = 0.5
SD_FLOOR = 0.25  # validation: the between-scan SD of a location is at least this share of the metric's median SD


### profile tables

BLANK = {"", "nan", "na", "none", "null"}


def is_blank(text):
    return str(text).strip().lower() in BLANK


class Table:
    """One profile table: its file, tract, metric and orientation, the cells as written (strings, so the observed
    values are copied verbatim) and as numbers (arc lengths x scans)."""

    def __init__(self, path, profiles_dir):
        from dtiplayground.dmri.fiberprofile.analysis.profile_qc import CASE_COLUMN, read_profile_table, tract_and_metric
        self.path = path
        self.rel = os.path.relpath(path, profiles_dir)
        self.tract, self.metric = tract_and_metric(path)
        self.raw = pd.read_csv(path, index_col=0, dtype=str, keep_default_na=False)
        self.rowwise = str(self.raw.index.name).strip() == CASE_COLUMN  # one row per scan
        values = read_profile_table(path).apply(pd.to_numeric, errors="coerce")
        self.arcs = values.index.to_numpy(dtype=float)
        self.values = values
        self.scans = [str(c) for c in values.columns]


def read_tables(profiles_dir):
    """The profile tables under *profiles_dir*, in every layout qc-profiles reads."""
    from dtiplayground.dmri.fiberprofile.analysis.profile_qc import select_inputs
    if not os.path.isdir(profiles_dir):
        raise FileNotFoundError("profiles folder not found: {}".format(profiles_dir))
    tables = [Table(f, profiles_dir) for f in select_inputs(profiles_dir)]
    if not tables:
        raise ValueError("no profile tables (<tract>/<tract>_<metric>.csv or <metric>/<tract>_<metric>.csv) in {}".format(profiles_dir))
    return tables


### tract axes

def axis_positions(arcs, axis_points, axis_arcs):
    """3-D positions (n x 3) of the arc lengths *arcs* on a tract axis: linear between the axis points, and along the
    first or last axis segment beyond its ends (compute-axis clips the sparse ends of the tracts)."""
    order = np.argsort(axis_arcs)
    d = np.asarray(axis_arcs, dtype=float)[order]
    p = np.asarray(axis_points, dtype=float)[order]
    if len(d) == 1:
        return np.repeat(p, len(arcs), axis=0)
    out = np.column_stack([np.interp(arcs, d, p[:, i]) for i in range(3)])
    for end, (a, b) in (("lo", (0, 1)), ("hi", (-2, -1))):
        step = d[b] - d[a]
        if step <= 0:
            continue
        sel = arcs < d[0] if end == "lo" else arcs > d[-1]
        if np.any(sel):
            anchor = p[0] if end == "lo" else p[-1]
            ref = d[0] if end == "lo" else d[-1]
            out[sel] = anchor + np.outer(arcs[sel] - ref, (p[b] - p[a]) / step)
    return out


def read_axes(axis_dir, tracts):
    """{tract: (points, arc lengths)} of the axes of *tracts* in *axis_dir*; tracts without an axis are left out."""
    from dtiplayground.dmri.fiberprofile.analysis.fiber_axis import read_axis
    if not os.path.isdir(axis_dir):
        raise FileNotFoundError("axis folder not found: {}".format(axis_dir))
    axes = {}
    for tract in tracts:
        path = os.path.join(axis_dir, "{}_axis.vtk".format(tract))
        if os.path.isfile(path):
            axes[tract] = read_axis(path)
    return axes


### the cohort as one array

class Cohort:
    """The profiles of all scans on one set of locations: positions (tract, arc length, 3-D point) x metrics.

    values[s, p, m] is the value of scan s at position p for metric m (NaN: missing), valid[p, m] whether a table of
    that tract and metric has the position (only those cells are imputed)."""

    def __init__(self, tables, axes=None):
        self.tables = tables
        metrics = {t.metric for t in tables}
        self.metrics = [m for m in METRIC_ORDER if m in metrics] + sorted(metrics - set(METRIC_ORDER))
        self.tracts = sorted({t.tract for t in tables})
        self.scans = sorted({s for t in tables for s in t.scans})
        mi = {m: i for i, m in enumerate(self.metrics)}
        si = {s: i for i, s in enumerate(self.scans)}

        # positions: the union of the arc lengths of the tables of each tract
        grids = defaultdict(set)
        for t in tables:
            grids[t.tract].update(np.round(t.arcs, 6).tolist())
        tract_of, arcs, self.slices = [], [], {}
        for ti, tract in enumerate(self.tracts):
            g = sorted(grids[tract])
            self.slices[tract] = slice(len(arcs), len(arcs) + len(g))
            arcs += g
            tract_of += [ti] * len(g)
        self.arcs = np.asarray(arcs, dtype=float)
        self.tract_of = np.asarray(tract_of, dtype=np.int64)
        self.n_positions = len(self.arcs)

        self.values = np.full((len(self.scans), self.n_positions, len(self.metrics)), np.nan, dtype=np.float32)
        self.valid = np.zeros((self.n_positions, len(self.metrics)), dtype=bool)
        self.rows = {}  # table -> positions of its rows
        for t in tables:
            sl = self.slices[t.tract]
            lookup = {a: sl.start + i for i, a in enumerate(np.round(self.arcs[sl], 6).tolist())}
            rows = np.asarray([lookup[a] for a in np.round(t.arcs, 6).tolist()], dtype=np.int64)
            self.rows[id(t)] = rows
            m = mi[t.metric]
            self.valid[rows, m] = True
            cols = [si[s] for s in t.scans]
            self.values[np.ix_(cols, rows, [m])] = t.values.to_numpy(dtype=np.float32).T[:, :, None]

        self.points = None
        if axes is not None:
            self.points = np.full((self.n_positions, 3), np.nan)
            for tract in self.tracts:
                if tract in axes:
                    sl = self.slices[tract]
                    self.points[sl] = axis_positions(self.arcs[sl], *axes[tract])
            self.has_point = ~np.isnan(self.points).any(axis=1)
        else:
            self.has_point = np.zeros(self.n_positions, dtype=bool)

    def scan(self, s):
        """(positions x metrics) values of scan index *s*, float64."""
        return self.values[s].astype(np.float64)


### methods (one scan: Y positions x metrics, NaN missing)

def nearest_observed(points, Y, valid):
    """(positions x metrics) distance from each position to the nearest observed position of the same metric."""
    from scipy.spatial import cKDTree
    dist = np.full(Y.shape, np.inf)
    usable = ~np.isnan(points).any(axis=1)
    for m in range(Y.shape[1]):
        obs = ~np.isnan(Y[:, m]) & usable
        if not obs.any():
            continue
        q = valid[:, m] & usable
        dist[q, m] = cKDTree(points[obs]).query(points[q], k=1)[0]
    return dist


def impute_arc_linear(Y, cohort, max_gap=None, ends="none"):
    """Linear along the arc length within each profile: interior gaps whose observed ends are at most *max_gap* mm
    apart (no limit: None). The missing start and end of a profile, up to *max_gap* mm beyond its first or last
    observed value: left (*ends* 'none'), that value repeated ('constant'), or the line through the 3 observed values
    nearest to the end extended ('linear'). Whole missing profiles are left."""
    out = np.full(Y.shape, np.nan)
    for tract, sl in cohort.slices.items():
        arcs = cohort.arcs[sl]
        for m in range(Y.shape[1]):
            v = Y[sl, m]
            obs = np.flatnonzero(~np.isnan(v) & cohort.valid[sl, m])
            if len(obs) < 2:
                continue
            for a, b in zip(obs[:-1], obs[1:]):
                if b - a < 2 or (max_gap is not None and arcs[b] - arcs[a] > max_gap):
                    continue
                inner = np.arange(a + 1, b)
                inner = inner[cohort.valid[sl, m][inner]]
                out[sl.start + inner, m] = np.interp(arcs[inner], [arcs[a], arcs[b]], [v[a], v[b]])
            if ends == "none":
                continue
            valid = cohort.valid[sl, m]
            for edge, near in ((np.arange(0, obs[0]), obs[:3]), (np.arange(obs[-1] + 1, len(v)), obs[-3:])):
                edge = edge[valid[edge]]
                if len(edge) == 0:
                    continue
                ref = arcs[obs[0]] if edge[0] < obs[0] else arcs[obs[-1]]
                if max_gap is not None:
                    edge = edge[np.abs(arcs[edge] - ref) <= max_gap]
                if ends == "constant" or len(near) < 2:
                    out[sl.start + edge, m] = v[near[0]] if edge[0] < obs[0] else v[near[-1]]
                else:
                    slope, intercept = np.polyfit(arcs[near], v[near], 1)
                    out[sl.start + edge, m] = intercept + slope * arcs[edge]
    return out


def impute_knn(Y, cohort, k=5, weights="distance", max_distance=None):
    """Mean of the *k* nearest observed positions (3-D) of the same metric, weighted by 1/distance (*weights*
    'distance') or not ('uniform'); only neighbours within *max_distance* mm count."""
    from scipy.spatial import cKDTree
    out = np.full(Y.shape, np.nan)
    pts = cohort.points
    for m in range(Y.shape[1]):
        obs = np.flatnonzero(~np.isnan(Y[:, m]) & cohort.has_point)
        miss = np.flatnonzero(np.isnan(Y[:, m]) & cohort.valid[:, m] & cohort.has_point)
        if len(obs) == 0 or len(miss) == 0:
            continue
        kk = min(k, len(obs))
        d, i = cKDTree(pts[obs]).query(pts[miss], k=kk, distance_upper_bound=np.inf if max_distance is None else max_distance)
        d, i = d.reshape(len(miss), kk), i.reshape(len(miss), kk)
        ok = np.isfinite(d)
        vals = np.where(ok, Y[obs[np.minimum(i, len(obs) - 1)], m], 0.0)
        w = ok / np.maximum(d, 1e-6) if weights == "distance" else ok.astype(float)
        wsum = w.sum(axis=1)
        filled = wsum > 0
        out[miss[filled], m] = (w * vals).sum(axis=1)[filled] / wsum[filled]
    return out


def impute_linear(Y, cohort, max_distance=None, _cache=None):
    """Linear in 3-D: barycentric interpolation in the Delaunay tetrahedra of the observed positions of the same
    metric. Positions outside their convex hull are left (see --fallback)."""
    from scipy.interpolate import LinearNDInterpolator
    from scipy.spatial import Delaunay
    out = np.full(Y.shape, np.nan)
    pts = cohort.points
    cache = {} if _cache is None else _cache
    for m in range(Y.shape[1]):
        obs = ~np.isnan(Y[:, m]) & cohort.has_point
        miss = np.flatnonzero(np.isnan(Y[:, m]) & cohort.valid[:, m] & cohort.has_point)
        if obs.sum() < 4 or len(miss) == 0:
            continue
        key = obs.tobytes()
        if key not in cache:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cache[key] = Delaunay(pts[obs], qhull_options="QJ")  # joggle: positions on lines, shared positions
        out[miss, m] = LinearNDInterpolator(cache[key], Y[obs, m])(pts[miss])
    return out


### SIREN

def build_siren(in_features, hidden, hidden_layers, out_features, omega_0):
    import torch
    from torch import nn

    class SineLayer(nn.Module):
        def __init__(self, in_f, out_f, is_first=False):
            super().__init__()
            self.omega_0 = omega_0
            self.linear = nn.Linear(in_f, out_f)
            with torch.no_grad():
                if is_first:
                    self.linear.weight.uniform_(-1.0 / in_f, 1.0 / in_f)
                else:
                    b = np.sqrt(6.0 / in_f) / omega_0
                    self.linear.weight.uniform_(-b, b)

        def forward(self, x):
            return torch.sin(self.omega_0 * self.linear(x))

    layers = [SineLayer(in_features, hidden, is_first=True)]
    for _ in range(hidden_layers):
        layers.append(SineLayer(hidden, hidden))
    final = nn.Linear(hidden, out_features)
    with torch.no_grad():
        b = np.sqrt(6.0 / hidden) / omega_0
        final.weight.uniform_(-b, b)
    layers.append(final)
    return nn.Sequential(*layers)


def pick_device(choice="auto"):
    import torch
    if choice != "auto":
        return choice
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def siren_features(cohort, inputs):
    """Network inputs of every position: the 3-D point scaled to [-1, 1] per axis over all tracts, with the arc length
    (scaled the same way) for 'xyz+arc', or a one-hot code of the tract for 'xyz+tract'."""
    if inputs not in SIREN_INPUTS:
        raise ValueError("unknown SIREN inputs {} ({})".format(inputs, ", ".join(SIREN_INPUTS)))
    pts = np.where(np.isnan(cohort.points), 0.0, cohort.points)
    cols = [pts]
    if inputs == "xyz+arc":
        cols.append(cohort.arcs[:, None])
    X = np.column_stack(cols)
    use = cohort.has_point
    lo, hi = X[use].min(axis=0), X[use].max(axis=0)
    X = (X - lo) / np.where(hi - lo > 0, hi - lo, 1.0) * 2.0 - 1.0
    if inputs == "xyz+tract":
        X = np.column_stack([X, np.eye(len(cohort.tracts))[cohort.tract_of]])
    return X.astype(np.float32)


def fit_siren(X, Y, cfg, device, seed=0, checkpoints=None):
    """Fit a SIREN to the observed values of one scan (all metrics jointly, each standardized on the scan's own
    values) and predict every position. Returns {epochs: prediction (positions x metrics)} at each of *checkpoints*
    (default: the last epoch); metrics without an observed value stay NaN."""
    import torch
    torch.manual_seed(seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        mu, sd = np.nanmean(Y, axis=0), np.nanstd(Y, axis=0)
    has_obs = (~np.isnan(Y)).any(axis=0)
    sd = np.where((sd < 1e-12) | ~np.isfinite(sd), 1.0, sd)
    mu = np.where(np.isfinite(mu), mu, 0.0)
    Yn = (Y - mu) / sd
    mask = ~np.isnan(Yn)
    train = mask.any(axis=1)
    Xt = torch.from_numpy(X).to(device)
    Yt = torch.from_numpy(np.nan_to_num(Yn[train]).astype(np.float32)).to(device)
    Mt = torch.from_numpy(mask[train].astype(np.float32)).to(device)
    Xtr = Xt[torch.from_numpy(np.flatnonzero(train)).to(device)]
    denom = Mt.sum().clamp_min(1.0)
    model = build_siren(X.shape[1], cfg["hidden"], cfg["hidden_layers"], Y.shape[1], cfg["omega0"]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=cfg["lr"])
    checkpoints = sorted(set(checkpoints or [cfg["epochs"]]))
    preds = {}
    for epoch in range(1, checkpoints[-1] + 1):
        opt.zero_grad()
        loss = (((model(Xtr) - Yt) ** 2) * Mt).sum() / denom
        loss.backward()
        opt.step()
        if epoch in checkpoints:
            with torch.no_grad():
                p = model(Xt).cpu().numpy().astype(np.float64) * sd + mu
            p[:, ~has_obs] = np.nan
            preds[epoch] = p
    return preds


### normative prior (age bins)

def bins_from_spec(spec):
    """[(lo, hi, label)] of a bin list "0-3,4-9,10-60" (months, inclusive), the oldest open-ended, as qc-profiles."""
    from dtiplayground.dmri.fiberprofile.analysis.profile_qc import parse_bins
    return parse_bins(spec)


def bins_from_labels(labels):
    """The bins of the column labels of age bin statistics ('0-3m', '4-9m', ...), the oldest open-ended."""
    spec = []
    for label in labels:
        m = re.fullmatch(r"(\d+)-(\d+)m", label)
        if m:
            spec.append("{}-{}".format(m.group(1), m.group(2)))
    return bins_from_spec(",".join(spec))


def scan_ages(cohort, age_csv=None, age_units="months", age_regex=None, age_column=None):
    """Age in months (or None) of every scan: its row in *age_csv*, else the pattern on its name (as qc-profiles)."""
    from dtiplayground.dmri.fiberprofile.analysis.profile_qc import age_of, set_age_source
    table = None
    if age_csv:
        from dtiplayground.dmri.common.age_table import load_age_table
        table = load_age_table(age_csv, age_units, age_column)
    set_age_source(table, age_regex)
    return [age_of(scan, record=False) for scan in cohort.scans]


def subject_of(scan):
    """The subject of a profile column (``<subject>_<session>_<prefix>``)."""
    return scan.split("_")[0]


def scan_bins(ages, bins):
    """Index of the age bin of every age (-1: no age or in no bin)."""
    from dtiplayground.dmri.common.age_table import in_age_bin
    out = []
    for age in ages:
        out.append(next((i for i, (lo, hi, _) in enumerate(bins) if in_age_bin(age, lo, hi)), -1))
    return np.asarray(out, dtype=np.int64)


class Prior:
    """The norm of every position and metric per age bin: mean and SD (bins x positions x metrics), and the bin of
    every scan. From the age bin statistics of qc-profiles (from_files), or from the cohort itself, leaving out the
    scan the norm is asked for (from_cohort, for the validation: the cohort is the normative set)."""

    def __init__(self, bins, scan_bin, mean=None, sd=None, sums=None):
        self.bins, self.scan_bin = bins, scan_bin
        self.mean, self.sd, self.sums = mean, sd, sums
        self.floor = None

    @classmethod
    def from_files(cls, cohort, prior_dir, ages):
        from dtiplayground.dmri.fiberprofile.analysis.profile_qc import find_prior_stats, prior_on_grid
        if not os.path.isdir(prior_dir):
            raise FileNotFoundError("prior stats folder not found: {}".format(prior_dir))
        bins, mean, sd = None, None, None
        mi = {m: i for i, m in enumerate(cohort.metrics)}
        missing = []
        for t in cohort.tables:
            path = find_prior_stats(prior_dir, t.tract, t.metric)
            if path is None:
                missing.append("{} {}".format(t.tract, t.metric))
                continue
            stats = pd.read_csv(path, index_col=0)
            if bins is None:
                bins = bins_from_labels([c[:-5] for c in stats.columns if c.endswith("_mean")])
                mean = np.full((len(bins), cohort.n_positions, len(cohort.metrics)), np.nan)
                sd = np.full_like(mean, np.nan)
            on_grid = prior_on_grid(stats, t.values.index)[0]
            rows = cohort.rows[id(t)]
            for b, (_, _, label) in enumerate(bins):
                if "{}_mean".format(label) in on_grid.columns:
                    mean[b, rows, mi[t.metric]] = on_grid["{}_mean".format(label)].to_numpy(dtype=float)
                    sd[b, rows, mi[t.metric]] = on_grid["{}_std".format(label)].to_numpy(dtype=float)
        if bins is None:
            raise ValueError("no age bin statistics (*_agebinstats.csv) for the profile tables in {}".format(prior_dir))
        if missing:
            log.warning("%d table(s) have no age bin statistics in %s, no norm there: %s", len(missing), prior_dir,
                        ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""))
        prior = cls(bins, scan_bins(ages, bins), mean=mean, sd=sd)
        prior.set_floor()
        return prior

    @classmethod
    def from_cohort(cls, cohort, bins, ages):
        sb = scan_bins(ages, bins)
        shape = (len(bins), cohort.n_positions, len(cohort.metrics))
        s1, s2, n = np.zeros(shape), np.zeros(shape), np.zeros(shape)
        for s in range(len(cohort.scans)):
            if sb[s] < 0:
                continue
            y = cohort.values[s].astype(np.float64)
            ok = ~np.isnan(y)
            s1[sb[s]] += np.where(ok, y, 0.0)
            s2[sb[s]] += np.where(ok, y, 0.0) ** 2
            n[sb[s]] += ok
        prior = cls(bins, sb, sums=(s1, s2, n))
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = s1 / n
            sd = np.sqrt(np.maximum(s2 - n * mean ** 2, 0.0) / (n - 1))
        prior.mean, prior.sd = np.where(n > 0, mean, np.nan), np.where(n > 1, sd, np.nan)
        prior.set_floor()
        return prior

    def set_floor(self):
        """SD floor per metric: SD_FLOOR of its median SD over the bins and positions (a location where a metric hardly
        varies would make every deviation large)."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            self.floor = SD_FLOOR * np.nanmedian(np.where(self.sd > 0, self.sd, np.nan).reshape(-1, self.sd.shape[2]),
                                                 axis=0)

    def norm(self, s, Y=None, others=()):
        """(mean, SD) (positions x metrics) of the age bin of scan *s*, or None without a bin. From the cohort, the
        scan's own values *Y* are left out, and those of the scans *others* (the subject's other scans: (values,
        bin) of each)."""
        b = self.scan_bin[s]
        if b < 0:
            return None
        if self.sums is None:
            mean, sd = self.mean[b], self.sd[b]
        else:
            s1, s2, n = (a[b] for a in self.sums)
            y = Y if Y is not None else np.full(s1.shape, np.nan)
            ok = ~np.isnan(y)
            s1, s2, n = s1 - np.where(ok, y, 0.0), s2 - np.where(ok, y, 0.0) ** 2, n - ok
            for yo, bo in others:
                if bo == b:
                    ok = ~np.isnan(yo)
                    s1, s2, n = s1 - np.where(ok, yo, 0.0), s2 - np.where(ok, yo, 0.0) ** 2, n - ok
            with np.errstate(invalid="ignore", divide="ignore"):
                mean = np.where(n > 0, s1 / n, np.nan)
                sd = np.where(n > 1, np.sqrt(np.maximum(s2 - n * mean ** 2, 0.0) / (n - 1)), np.nan)
        return mean, np.where(np.isfinite(sd), np.fmax(sd, self.floor[None, :]), np.nan)

    def bin_norm(self, b):
        """(mean, SD) of age bin *b* over every scan of the prior (the SD with its floor)."""
        return self.mean[b], np.where(np.isfinite(self.sd[b]), np.fmax(self.sd[b], self.floor[None, :]), np.nan)


### population model: probabilistic PCA of the deviations from the norm

def fit_ppca(Z, q, noise="isotropic", groups=None, max_iter=300, tol=1e-6, device="auto", ridge=1.0):
    """Probabilistic PCA with missing values (EM with the exact posterior of every row, Tipping & Bishop 1999; Ilin &
    Raiko 2010): z = mu + W x + e, x ~ N(0, I_q), e ~ N(0, diag(psi)), on the observed cells of *Z* (rows x cells,
    NaN missing). *noise*: one psi for all cells ('isotropic'), one per group of cells (*groups*, e.g. the metric:
    'metric') or one per cell ('diagonal'). *ridge*: a prior on the rows of W (as that many pseudo-observations of
    x = 0), for the cells observed in few rows. Returns (mu, W, psi, info)."""
    import torch
    dev = pick_device(device)
    if dev == "mps":  # no float64 on mps
        dev = "cpu"
    O = torch.as_tensor(~np.isnan(Z), dtype=torch.float32, device=dev)
    Y = torch.as_tensor(np.nan_to_num(Z), dtype=torch.float32, device=dev)
    N, D = Y.shape
    if q > min(N - 1, D):
        log.warning("population: %d components, fewer than the %d asked: at most the number of scans fitted - 1",
                    max(1, min(N - 1, D)), q)
        q = max(1, min(N - 1, D))
    nj = O.sum(0).clamp_min(1.0)
    n_obs = float(O.sum())
    if groups is not None:
        g = torch.as_tensor(np.asarray(groups), dtype=torch.long, device=dev)
        n_groups = int(g.max()) + 1
    q1 = q + 1
    chunk = max(1, int(4e7 // (q1 * q1 + N)))  # cells per block of the per-cell q x q sums

    def pool(ss):  # psi from the summed expected squared residuals of every cell
        if noise == "isotropic":
            p = torch.full((D,), float(ss.sum()) / n_obs, device=dev)
        elif noise == "metric":
            num = torch.zeros(n_groups, device=dev).index_add_(0, g, ss)
            den = torch.zeros(n_groups, device=dev).index_add_(0, g, O.sum(0))
            p = (num / den.clamp_min(1.0))[g]
        else:
            p = ss / nj
        return p.clamp_min(1e-4)

    # start: PCA of the centered data, missing cells at the mean
    mu = Y.sum(0) / nj
    Yc = (Y - mu) * O
    U, S, Vh = torch.linalg.svd(Yc, full_matrices=False)
    W = (Vh[:q].T * (S[:q] / math.sqrt(N))).contiguous()
    psi = pool((((Yc - (U[:, :q] * S[:q]) @ Vh[:q]) * O) ** 2).sum(0))
    eye = torch.eye(q, dtype=torch.float64, device=dev)
    prev, ll, it = -np.inf, -np.inf, 0
    for it in range(1, max_iter + 1):
        # E-step: posterior of x of every row, x | z_o ~ N(Sigma B, Sigma), Sigma = (I + W_o' Psi_o^-1 W_o)^-1
        Wp = W / psi[:, None]
        G = torch.zeros(N, q * q, device=dev)
        for a in range(0, D, chunk):
            c = slice(a, a + chunk)
            G += O[:, c] @ (W[c, :, None] * Wp[c, None, :]).reshape(-1, q * q)
        M = eye + G.double().reshape(N, q, q)
        L = torch.linalg.cholesky(M)
        Sigma = torch.cholesky_inverse(L)
        Yc = (Y - mu) * O
        B = (Yc @ Wp).double()
        x = (Sigma @ B[:, :, None])[:, :, 0]
        # observed-data log-likelihood (Woodbury), of the parameters before this M-step
        logdet = 2.0 * torch.log(torch.diagonal(L, dim1=1, dim2=2)).sum(1)
        quad = (Yc ** 2 @ (1.0 / psi)).double() - (B * x).sum(1)
        ll = float(-0.5 * ((O @ torch.log(psi)).double() + logdet + quad).sum() - 0.5 * n_obs * math.log(2 * math.pi))
        if it > 1 and abs(ll - prev) <= tol * abs(prev):
            break
        prev = ll
        # M-step: mu and W of every cell jointly (x augmented with a 1), then psi
        xt = torch.cat([x, torch.ones(N, 1, dtype=torch.float64, device=dev)], 1)
        C = (xt[:, :, None] * xt[:, None, :])
        C[:, :q, :q] += Sigma
        C = C.reshape(N, q1 * q1).float()
        Sf = Sigma.reshape(N, q * q).float()
        reg = torch.zeros(q1, q1, dtype=torch.float64, device=dev)
        reg[:q, :q] = ridge * eye
        xtf = xt.float()
        W_new, mu_new, ss = torch.empty_like(W), torch.empty_like(mu), torch.empty_like(mu)
        for a in range(0, D, chunk):
            c = slice(a, a + chunk)
            A = (O[:, c].T @ C).double().reshape(-1, q1, q1) + reg
            b = (Y[:, c].T @ xtf).double()
            sol = torch.linalg.solve(A, b[:, :, None])[:, :, 0].float()
            W_new[c], mu_new[c] = sol[:, :q], sol[:, q]
            R = (Y[:, c] - xtf @ sol.T) * O[:, c]
            t2 = ((sol[:, :q, None] * sol[:, None, :q]).reshape(-1, q * q) * (O[:, c].T @ Sf)).sum(1)
            ss[c] = (R ** 2).sum(0) + t2
        W, mu, psi = W_new, mu_new, pool(ss)
    Wn = W.double().cpu().numpy()
    signal = float(np.sum(Wn ** 2))
    info = {"components": q, "noise": noise, "rows": N, "cells": D, "iterations": it, "loglik": ll,
            "explained": signal / (signal + float(psi.sum()))}
    return mu.double().cpu().numpy(), Wn, psi.double().cpu().numpy(), info


def ppca_posterior(mu, W, psi, z):
    """Posterior mean and SD (with the noise) of every cell from the observed cells of *z* (NaN missing)."""
    o = ~np.isnan(z)
    Wo = W[o] / psi[o, None]
    Sigma = np.linalg.inv(np.eye(W.shape[1]) + Wo.T @ W[o])
    x = Sigma @ (Wo.T @ (z[o] - mu[o]))
    return mu + W @ x, np.sqrt(psi + ((W @ Sigma) * W).sum(axis=1))


def ppca_sd_scale(Z, groups, rows_subject, q, noise, max_iter, tol, device, folds=5, share=0.2, seed=0):
    """Scale of the SDs per group of cells (metric) that makes them right on held-out scans: the model is fitted again
    in *folds* folds by the subject of each row (*rows_subject*), and each held-out row has the whole profiles of a
    share *share* of its tracts hidden and predicted. *Z*: .values (rows x cells, NaN missing) and .tracts (tract of
    every cell). Returns the RMS of error / SD per group (1: right)."""
    rng = np.random.default_rng(seed)
    subjects = np.unique(rows_subject)
    rng.shuffle(subjects)
    fold = {subj: i % folds for i, subj in enumerate(subjects)}
    of = np.asarray([fold[x] for x in rows_subject])
    n_groups = int(groups.max()) + 1
    ss, n = np.zeros(n_groups), np.zeros(n_groups)
    tract = Z.tracts
    for f in range(folds):
        train, held = np.flatnonzero(of != f), np.flatnonzero(of == f)
        if len(train) < 2 or not len(held):
            continue
        mu, W, psi, _ = fit_ppca(Z.values[train], q, noise, groups, max_iter, tol, device)
        for i in held:
            z = Z.values[i]
            have = np.unique(tract[~np.isnan(z)])
            if len(have) < 2:
                continue
            hide = np.isin(tract, rng.choice(have, size=max(1, int(round(share * len(have)))), replace=False))
            hidden = hide & ~np.isnan(z)
            mean, sd = ppca_posterior(mu, W, psi, np.where(hide, np.nan, z))
            e = ((mean - z) / sd)[hidden]
            ss += np.bincount(groups[hidden], weights=e ** 2, minlength=n_groups)
            n += np.bincount(groups[hidden], minlength=n_groups)
    return np.where(n > 0, np.sqrt(ss / np.maximum(n, 1)), 1.0)


class Population:
    """A probabilistic PCA (fit_ppca) of the deviations z of a normative cohort from the norm of their age bins, over
    every cell (tract, arc length, metric): all tracts and metrics jointly, so a scan's observed deviations give the
    mean and SD of every missing cell, also of a metric the scan lacks entirely. The model keeps the norm it was
    fitted with, so it applies to another cohort on the same tracts (--fit-model, --model)."""

    def __init__(self, tract, arc, metric, mu, W, psi, bins, norm_mean, norm_sd, info, sd_scale=None):
        self.tract, self.arc, self.metric = np.asarray(tract), np.asarray(arc, dtype=float), np.asarray(metric)
        self.mu, self.W, self.psi = mu, W, psi
        self.sd_scale = np.ones(len(mu)) if sd_scale is None else np.asarray(sd_scale, dtype=float)  # per cell
        self.bins, self.norm_mean, self.norm_sd = bins, norm_mean, norm_sd  # bins x cells (the SD with its floor)
        self.info = info
        self.p = self.m = None  # position and metric of each cell in the cohort it is bound to (-1: none)

    @classmethod
    def fit(cls, cohort, prior, scans, q, noise="isotropic", max_iter=300, tol=1e-6, device="auto", min_scans=10,
            sd_folds=5):
        """Fit on the deviations of the scans *scans* (indices) from the norm of their age bin (*prior*); the cells
        observed in at least *min_scans* of them. *sd_folds*: folds (by subject) of the calibration of the SDs per
        metric (ppca_sd_scale; 0: none)."""
        Z = np.full((len(scans), cohort.n_positions, len(cohort.metrics)), np.nan)
        for i, s in enumerate(scans):
            nrm = prior.norm(s)
            if nrm is not None:
                Z[i] = (cohort.scan(s) - nrm[0]) / nrm[1]
        if not len(scans):
            raise ValueError("no scan to fit the population model on (scans with an age bin)")
        Z = Z.reshape(len(scans), -1)
        keep = cohort.valid.reshape(-1) & ((~np.isnan(Z)).sum(axis=0) >= min_scans)
        cells = np.flatnonzero(keep)
        p, m = np.unravel_index(cells, cohort.valid.shape)
        Zk = Z[:, cells]
        rows = np.flatnonzero((~np.isnan(Zk)).any(axis=1))
        Zk = Zk[rows]
        mu, W, psi, info = fit_ppca(Zk, q, noise, m, max_iter, tol, device)
        scale = np.ones(len(cells))
        if sd_folds and sd_folds > 1:
            data = argparse.Namespace(values=Zk, tracts=cohort.tract_of[p])
            subj = np.asarray([subject_of(cohort.scans[scans[r]]) for r in rows])
            by_metric = ppca_sd_scale(data, m, subj, info["components"], noise, max_iter, tol, device, sd_folds)
            scale = by_metric[m]
            info["sd_scale"] = {cohort.metrics[i]: round(float(by_metric[i]), 4) for i in np.unique(m)}
        bn = [prior.bin_norm(b) for b in range(len(prior.bins))]
        model = cls(np.asarray(cohort.tracts)[cohort.tract_of[p]], cohort.arcs[p], np.asarray(cohort.metrics)[m], mu, W,
                    psi, prior.bins, np.stack([a[p, m] for a, _ in bn]), np.stack([b[p, m] for _, b in bn]), info, scale)
        model.p, model.m = p, m
        return model

    def bind(self, cohort):
        """Match the cells to the positions and metrics of *cohort*; returns the share of the model cells it has."""
        lookup = {(cohort.tracts[cohort.tract_of[i]], a): i for i, a in enumerate(np.round(cohort.arcs, 6).tolist())}
        mi = {m: i for i, m in enumerate(cohort.metrics)}
        self.p = np.asarray([lookup.get((t, a), -1) for t, a in zip(self.tract, np.round(self.arc, 6).tolist())],
                            dtype=np.int64)
        self.m = np.asarray([mi.get(m, -1) for m in self.metric], dtype=np.int64)
        self.m[self.p < 0] = -1
        self.p[self.m < 0] = -1
        return float(np.mean(self.p >= 0))

    def prior(self, cohort, ages):
        """The norm kept with the model, as a Prior of *cohort* (bound first)."""
        on = self.p >= 0
        shape = (len(self.bins), cohort.n_positions, len(cohort.metrics))
        mean, sd = np.full(shape, np.nan), np.full(shape, np.nan)
        mean[:, self.p[on], self.m[on]] = self.norm_mean[:, on]
        sd[:, self.p[on], self.m[on]] = self.norm_sd[:, on]
        prior = Prior(self.bins, scan_bins(ages, self.bins), mean=mean, sd=sd)
        prior.floor = np.zeros(len(cohort.metrics))  # the kept SDs have their floor already
        return prior

    def predict(self, z):
        """Posterior mean and SD (positions x metrics, NaN outside the model) of every cell of a scan from its observed
        deviations *z* (positions x metrics, NaN missing). The SD is that of the value (with the noise)."""
        on = self.p >= 0
        zc = np.full(len(self.mu), np.nan)
        zc[on] = z[self.p[on], self.m[on]]
        mean, sd = ppca_posterior(self.mu, self.W, self.psi, zc)
        sd = sd * self.sd_scale
        out_mean, out_sd = np.full(z.shape, np.nan), np.full(z.shape, np.nan)
        out_mean[self.p[on], self.m[on]] = mean[on]
        out_sd[self.p[on], self.m[on]] = sd[on]
        return out_mean, out_sd

    def impute(self, Y, norm):
        """(values, SDs) of every cell of a scan with values *Y* and the norm (mean, SD) of its age bin."""
        zm, zsd = self.predict((Y - norm[0]) / norm[1])
        return norm[0] + zm * norm[1], zsd * norm[1]

    def save(self, path):
        lo = np.array([b[0] for b in self.bins], dtype=float)
        hi = np.array([b[1] for b in self.bins], dtype=float)
        np.savez_compressed(path, tract=self.tract, arc=self.arc, metric=self.metric, mu=self.mu, W=self.W,
                            psi=self.psi, bin_lo=lo, bin_hi=hi, bin_label=np.asarray([b[2] for b in self.bins]),
                            norm_mean=self.norm_mean, norm_sd=self.norm_sd, sd_scale=self.sd_scale,
                            info=json.dumps(self.info))

    @classmethod
    def load(cls, path):
        d = np.load(path, allow_pickle=False)
        bins = [(float(lo), float(hi), str(label))
                for lo, hi, label in zip(d["bin_lo"], d["bin_hi"], d["bin_label"])]
        return cls(d["tract"], d["arc"], d["metric"], d["mu"], d["W"], d["psi"], bins, d["norm_mean"], d["norm_sd"],
                   json.loads(str(d["info"])), d["sd_scale"] if "sd_scale" in d.files else None)


### imputation of one scan

def impute_scan(Y, cohort, method, opts, cache=None, features=None, device=None, norm=None, relative=False):
    """Imputed values (positions x metrics, NaN where not imputed) of one scan with *method*. *norm*: (mean, SD) of
    the scan's age bin; with *relative*, the method imputes the deviations from it (z) and they are turned back into
    values with the norm of each imputed location."""
    if method == "prior-mean":
        return np.full(Y.shape, np.nan) if norm is None else norm[0].copy()
    if relative:
        if norm is None:
            return np.full(Y.shape, np.nan)
        mean, sd = norm
        z = impute_scan((Y - mean) / sd, cohort, method, opts, cache, features, device)
        return mean + z * sd
    if method == "arc-linear":
        return impute_arc_linear(Y, cohort, opts.get("max_gap"), opts.get("ends", "none"))
    if method == "knn":
        return impute_knn(Y, cohort, opts.get("k", 5), opts.get("weights", "distance"), opts.get("max_distance"))
    if method == "linear":
        return impute_linear(Y, cohort, opts.get("max_distance"), cache)
    if method == "siren":
        Yp = np.where(cohort.has_point[:, None], Y, np.nan)
        return fit_siren(features, Yp, opts["siren"], device, opts.get("seed", 0))[opts["siren"]["epochs"]]
    raise ValueError("unknown method {}".format(method))


def limit(pred, Y, cohort, dist, max_distance, spatial=True):
    """Keep the imputed values of the cells that are missing and have a table; for the 3-D methods (*spatial*), of
    those with a 3-D point within *max_distance* mm of an observed position of the same metric (no limit: None)."""
    keep = np.isnan(Y) & cohort.valid & ~np.isnan(pred)
    if spatial:
        keep &= cohort.has_point[:, None]
        if max_distance is not None:
            keep &= dist <= max_distance
    return np.where(keep, pred, np.nan)


def scan_shares(cohort, Y):
    """Share of the cells with a table that are observed, per metric."""
    n = cohort.valid.sum(axis=0)
    return np.where(n > 0, (~np.isnan(Y) & cohort.valid).sum(axis=0) / np.maximum(n, 1), 0.0)


def missing_tracts(cohort, Y):
    """(number of tracts with a table and no observed value of any metric, number of tracts with a table) of a scan."""
    observed = (~np.isnan(Y) & cohort.valid).any(axis=1)
    n = missing = 0
    for sl in cohort.slices.values():
        if cohort.valid[sl].any():
            n += 1
            missing += not observed[sl].any()
    return missing, n


def too_many_missing(cohort, Y, max_share):
    """Whether a scan misses more than a share *max_share* of its tracts (--max-missing-tracts)."""
    n_missing, n_tracts = missing_tracts(cohort, Y)
    return bool(n_tracts) and n_missing / n_tracts > max_share


### imputation of a cohort

def impute_cohort(cohort, method="knn", fallback=None, opts=None, min_observed=0.5, device="auto", log_every=25,
                  prior=None, max_missing_tracts=None, model=None):
    """Impute every scan; a scan missing more than a share *max_missing_tracts* of its tracts is left as it is.
    *model*: the Population of the method population (bound to *cohort*). Returns (imputed values scans x positions
    x metrics (NaN: not imputed), method index per cell (-1: none), distances to the nearest observed position,
    reasons {(scan, metric): text} for skipped ones, SDs of the values population imputed (NaN elsewhere))."""
    opts = dict(opts or {})
    methods = [method] + ([fallback] if fallback and fallback != method else [])
    needs_points = any(m in SPATIAL for m in methods)
    if needs_points and cohort.points is None:
        raise ValueError("--axis-dir is needed for the methods {}".format(", ".join(m for m in methods if m in SPATIAL)))
    relative = bool(opts.get("relative"))
    if (relative or "prior-mean" in methods or "population" in methods) and prior is None:
        raise ValueError("--relative-to-prior, prior-mean and population need a normative prior (--prior-stats-dir)")
    by_population = relative and opts.get("norm") == "population" and not set(methods) <= set(BY_NORM)
    if ("population" in methods or by_population) and model is None:
        raise ValueError("population and --norm population need a population model")
    features = dev = None
    if "siren" in methods:
        dev = pick_device(device)
        features = siren_features(cohort, opts.get("siren_inputs", "xyz+tract"))
        log.info("SIREN on %s (%s): %d epochs, omega_0=%g, %d hidden layers x %d, Adam lr=%g", dev,
                 opts.get("siren_inputs", "xyz+tract"), opts["siren"]["epochs"], opts["siren"]["omega0"],
                 opts["siren"]["hidden_layers"], opts["siren"]["hidden"], opts["siren"]["lr"])
    shape = cohort.values.shape
    imputed = np.full(shape, np.nan, dtype=np.float64)
    used = np.full(shape, -1, dtype=np.int8)
    dists = np.full(shape, np.inf, dtype=np.float32)
    sds = np.full(shape, np.nan, dtype=np.float32)
    skipped = {}
    t0 = time.time()
    for s, scan in enumerate(cohort.scans):
        Y = cohort.scan(s)
        missing = np.isnan(Y) & cohort.valid
        if not missing.any():
            continue
        if max_missing_tracts is not None and too_many_missing(cohort, Y, max_missing_tracts):
            n_missing, n_tracts = missing_tracts(cohort, Y)
            for m, metric in enumerate(cohort.metrics):
                if missing[:, m].any():
                    skipped[(scan, metric)] = "{} of {} tracts missing, above --max-missing-tracts {:g}".format(
                        n_missing, n_tracts, max_missing_tracts)
            continue
        share = scan_shares(cohort, Y)
        norm = prior.norm(s) if prior is not None else None
        for m, metric in enumerate(cohort.metrics):
            if missing[:, m].any() and share[m] < min_observed and not set(methods) & set(BY_NORM):
                skipped[(scan, metric)] = ("no observed value" if share[m] == 0 else
                                           "{:.0%} observed, below --min-observed {:g}".format(share[m], min_observed))
            if missing[:, m].any() and prior is not None and norm is None:
                skipped[(scan, metric)] = "no age, or an age in no bin of the prior"
        dist = nearest_observed(cohort.points, Y, cohort.valid) if needs_points else np.full(Y.shape, np.inf)
        dists[s] = np.minimum(dist, np.finfo(np.float32).max)
        cache = {}
        pop = None if model is None or norm is None else model.impute(Y, norm)
        # --norm population: the deviations are those from the population prediction of the scan, with its SD
        rnorm = pop if by_population else norm
        for mth in methods:  # a fallback imputes from the observed values too, not from those of the first method
            sd = None
            if mth == "population":
                pred, sd = (np.full(Y.shape, np.nan),) * 2 if pop is None else pop
            else:
                rel = relative and mth not in BY_NORM
                pred = impute_scan(Y, cohort, mth, opts, cache, features, dev, rnorm if rel else norm, rel)
                if rel and by_population and pop is not None:
                    sd = pop[1]  # an upper bound: the method adds the scan's neighbours to the model
            pred = limit(pred, Y, cohort, dist, opts.get("max_distance"), spatial=mth in SPATIAL)
            if mth not in BY_NORM:  # the norm and the population model need no observed value of the metric
                pred[:, share < min_observed] = np.nan
            new = ~np.isnan(pred) & np.isnan(imputed[s])
            imputed[s][new] = pred[new]
            used[s][new] = METHODS.index(mth)
            if sd is not None:
                sds[s][new] = sd[new]
        if log_every and (s + 1) % log_every == 0:
            log.info("  ... %d/%d scans (%.0f s)", s + 1, len(cohort.scans), time.time() - t0)
    return imputed, used, dists, skipped, sds


### outputs

def write_tables(cohort, imputed, out_dir, mask_dir, value_format="%.6g"):
    """Write every table to *out_dir* (same layout and orientation): observed cells verbatim, imputed cells filled; a
    scan absent from a table gets a column (row) when any of its values there was imputed. *mask_dir*: the same
    tables with 1 for imputed, 0 for observed and blank for still missing cells. Returns the number of cells
    filled."""
    si = {s: i for i, s in enumerate(cohort.scans)}
    mi = {m: i for i, m in enumerate(cohort.metrics)}
    n_filled = 0
    for t in cohort.tables:
        rows = cohort.rows[id(t)]
        m = mi[t.metric]
        raw = t.raw if t.rowwise else t.raw.T  # scans x arc lengths, as strings
        raw = raw.copy()
        raw.index = raw.index.astype(str)
        blank = np.vectorize(is_blank, otypes=[bool])(raw.to_numpy()) if raw.size else np.zeros(raw.shape, bool)
        mask = pd.DataFrame(np.where(blank, "", "0"), index=raw.index, columns=raw.columns)
        for scan in cohort.scans:
            vals = imputed[si[scan], rows, m]
            if np.isnan(vals).all():
                continue
            if scan not in raw.index:
                raw.loc[scan] = ""
                mask.loc[scan] = ""
            cells = np.flatnonzero(~np.isnan(vals))
            row_raw = raw.loc[scan].to_numpy(dtype=object)
            row_mask = mask.loc[scan].to_numpy(dtype=object)
            for c in cells:
                if is_blank(row_raw[c]):
                    row_raw[c] = value_format % vals[c]
                    row_mask[c] = "1"
                    n_filled += 1
            raw.loc[scan] = row_raw
            mask.loc[scan] = row_mask
        for frame, root in ((raw, out_dir), (mask, mask_dir)):
            out = frame if t.rowwise else frame.T
            out.index.name = t.raw.index.name
            if not t.rowwise:
                out.columns.name = None
            path = os.path.join(root, t.rel)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            out.to_csv(path)
    return n_filled


def write_values(cohort, values, root, value_format="%.6g"):
    """Tables of *values* (scans x positions x metrics) in the layout of the input, blank where NaN; the scans with
    any value in a table (e.g. the SDs of the imputed values)."""
    mi = {m: i for i, m in enumerate(cohort.metrics)}
    for t in cohort.tables:
        v = values[:, cohort.rows[id(t)], mi[t.metric]]
        keep = ~np.isnan(v).all(axis=1)
        if not keep.any():
            continue
        cells = np.where(np.isnan(v[keep]), "", np.char.mod(value_format, np.nan_to_num(v[keep])))
        frame = pd.DataFrame(cells, index=np.asarray(cohort.scans)[keep], columns=t.raw.columns if t.rowwise
                             else t.raw.index)
        out = frame if t.rowwise else frame.T
        out.index.name = t.raw.index.name
        path = os.path.join(root, t.rel)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        out.to_csv(path)


def missing_shape(miss):
    """'whole profile', or the kinds of runs of missing values of a profile: 'end gap' (at its start or end), 'gap'
    (inside), or both."""
    if miss.all():
        return WHOLE
    obs = np.flatnonzero(~miss)
    kinds = []
    if miss[:obs[0]].any() or miss[obs[-1] + 1:].any():
        kinds.append(END)
    if miss[obs[0]:obs[-1] + 1].any():
        kinds.append(GAP)
    return ", ".join(kinds)


def summary_rows(cohort, imputed, used, dists, skipped, sds=None):
    """One row per scan, tract and metric with missing values: what was missing, what was imputed and how (with the
    mean SD of the values population imputed, *sds*)."""
    rows = []
    for s, scan in enumerate(cohort.scans):
        Y = cohort.values[s]
        for tract, sl in cohort.slices.items():
            for m, metric in enumerate(cohort.metrics):
                valid = cohort.valid[sl, m]
                if not valid.any():
                    continue
                miss = np.isnan(Y[sl, m]) & valid
                if not miss.any():
                    continue
                filled = ~np.isnan(imputed[s, sl, m]) & miss
                n_obs = int(valid.sum() - miss.sum())
                meth = sorted({METHODS[i] for i in used[s, sl, m][filled]})
                d = dists[s, sl, m][filled]
                sd = np.array([]) if sds is None else sds[s, sl, m][filled & ~np.isnan(sds[s, sl, m])]
                left = int(miss.sum() - filled.sum())
                reason = ""
                if left:
                    reason = skipped.get((scan, metric), "")
                    if not reason:
                        reason = "not filled (--max-distance, --max-gap, outside the observed positions or no axis)"
                rows.append({"scan": scan, "tract": tract, "metric": metric, "n_positions": int(valid.sum()),
                             "n_observed": n_obs, "n_missing": int(miss.sum()),
                             "shape": missing_shape(miss[valid]), "n_imputed": int(filled.sum()),
                             "n_left": left, "methods": "+".join(meth),
                             "max_distance_mm": round(float(d.max()), 3) if d.size and np.isfinite(d).all() else "",
                             "mean_sd": float("{:.6g}".format(sd.mean())) if sd.size else "", "left_reason": reason})
    return pd.DataFrame(rows, columns=["scan", "tract", "metric", "n_positions", "n_observed", "n_missing", "shape",
                                       "n_imputed", "n_left", "methods", "max_distance_mm", "mean_sd", "left_reason"])


### validation

def axis_proximity(cohort):
    """Per tract: distance from its positions to the nearest position of another tract (atlas space)."""
    from scipy.spatial import cKDTree
    rows = []
    for ti, tract in enumerate(cohort.tracts):
        sl = cohort.slices[tract]
        mine = cohort.has_point[sl]
        others = np.flatnonzero((cohort.tract_of != ti) & cohort.has_point)
        if not mine.any() or len(others) == 0:
            rows.append({"tract": tract})
            continue
        d, i = cKDTree(cohort.points[others]).query(cohort.points[sl][mine], k=1)
        near = cohort.tract_of[others[i]]
        rows.append({"tract": tract, "n_positions": int(mine.sum()), "min_mm": round(float(d.min()), 3),
                     "median_mm": round(float(np.median(d)), 3), "max_mm": round(float(d.max()), 3),
                     "share_within_2mm": round(float((d <= 2).mean()), 3),
                     "share_within_5mm": round(float((d <= 5).mean()), 3),
                     "nearest_tract": cohort.tracts[np.bincount(near).argmax()]})
    return pd.DataFrame(rows)


def hide(cohort, Y, rng, gap_fraction, gap_mm, whole_fraction, end_fraction=0.0, end_mm=(1.0, 8.0)):
    """Positions of one scan to hide: whole profiles (all metrics of a tract) of a share *whole_fraction* of its
    observed tracts; of the other tracts, in a share *gap_fraction* one run of positions *gap_mm* (lo, hi) long inside
    the observed part, and in a share *end_fraction* the first or last *end_mm* of the observed part (at least 3
    observed positions are kept). Returns {position: pattern}."""
    observed = (~np.isnan(Y) & cohort.valid).any(axis=1)
    tracts = [t for t, sl in cohort.slices.items() if observed[sl].sum() >= 3]
    rng.shuffle(tracts)
    n_whole = int(round(whole_fraction * len(tracts)))
    hidden = {}
    for t in tracts[:n_whole]:
        sl = cohort.slices[t]
        for p in np.flatnonzero(observed[sl]):
            hidden[sl.start + p] = WHOLE
    rest = tracts[n_whole:]
    n_gap = int(round(gap_fraction * len(rest)))
    n_end = int(round(end_fraction * len(rest)))
    for t in rest[n_gap:n_gap + n_end]:
        sl = cohort.slices[t]
        obs = np.flatnonzero(observed[sl])
        arcs = cohort.arcs[sl]
        length = rng.uniform(*end_mm)
        if rng.random() < 0.5:
            run = [q for q in obs if arcs[q] - arcs[obs[0]] < length]
        else:
            run = [q for q in obs if arcs[obs[-1]] - arcs[q] < length]
        if len(obs) - len(run) < 3:
            continue
        for q in run:
            hidden[sl.start + q] = END
    for t in rest[:n_gap]:
        sl = cohort.slices[t]
        obs = np.flatnonzero(observed[sl])
        arcs = cohort.arcs[sl]
        length = rng.uniform(*gap_mm)
        inner = obs[1:-1]  # keep observed ends, so the gap is inside the profile
        if len(inner) == 0:
            continue
        start = rng.choice(inner)
        run = [p for p in inner if arcs[start] <= arcs[p] <= arcs[start] + length]
        for p in run:
            hidden[sl.start + p] = GAP
    return hidden


def hide_region(cohort, Y, rng, radius_mm, count=1):
    """Positions of one scan to hide as a region: *count* spheres around random observed positions, radius drawn from
    *radius_mm* (lo, hi); every tract with an observed position inside a sphere loses its whole profile (all
    metrics), as a regional artifact would have qc-profiles reject all of them. A sphere reaching more than
    REGION_MAX_SHARE of the scan's tracts is drawn again (10 tries, then left out). Returns {position: 'region'}."""
    observed = (~np.isnan(Y) & cohort.valid).any(axis=1) & cohort.has_point
    obs = np.flatnonzero(observed)
    hidden = {}
    if len(obs) == 0:
        return hidden
    n_tracts = len(np.unique(cohort.tract_of[obs]))
    for _ in range(count):
        for _attempt in range(10):  # a region that takes most of the scan is not a regional artifact: redraw
            center = cohort.points[rng.choice(obs)]
            radius = rng.uniform(*radius_mm)
            inside = observed & (np.linalg.norm(cohort.points - center, axis=1) <= radius)
            tracts = np.unique(cohort.tract_of[inside])
            if len(tracts) <= REGION_MAX_SHARE * n_tracts:
                break
        else:
            continue
        for t in tracts:
            sl = cohort.slices[cohort.tracts[t]]
            for q in np.flatnonzero(observed[sl]):
                hidden[sl.start + q] = REGION
    return hidden


def family_of(metric):
    """The family (FAMILIES) of a metric name, or None."""
    key = re.sub(r"[^A-Z]", "", metric.upper())
    return next((f for f, names in FAMILIES.items() if key in names), None)


def hide_measure(cohort, Y, rng, families):
    """A family of metrics (one of *families* the scan has observed values of) to hide entirely, as for a scan without
    that model fit. Returns ({position: 'whole measure'}, metric indices), or ({}, [])."""
    have = sorted({family_of(m) for i, m in enumerate(cohort.metrics)
                   if family_of(m) in families and (~np.isnan(Y[:, i]) & cohort.valid[:, i]).any()})
    if not have:
        return {}, []
    fam = have[rng.integers(len(have))]
    metrics = [i for i, m in enumerate(cohort.metrics) if family_of(m) == fam]
    observed = (~np.isnan(Y[:, metrics]) & cohort.valid[:, metrics]).any(axis=1)
    return {p: MEASURE for p in np.flatnonzero(observed)}, metrics


def population_configs(args):
    """(setting, components, noise) of the population settings to compare."""
    if "population" not in [m.strip() for m in args.validate_methods.split(",")]:
        return []
    noises = [x.strip() for x in args.validate_noise.split(",") if x.strip()]
    for x in noises:
        if x not in NOISE:
            raise ValueError("unknown --validate-noise {} ({})".format(x, ", ".join(NOISE)))
    return [("population q={} {}".format(q, x), q, x) for q in parse_list(args.validate_components, int) for x in noises]


def population_folds(cohort, args, sample, prior, bins, scan_bin, pops, dev):
    """Population models of the validation: the sampled scans split by subject into --validate-folds folds; for each
    fold and setting a model fitted on the other subjects (their norm from them too, with --validate-prior cohort).
    Returns {scan: [(setting, model, the scan's norm of the model)]}."""
    rng = np.random.default_rng(args.validate_seed + 1)  # own stream: the hidden values stay those of other runs
    subjects = sorted({subject_of(cohort.scans[s]) for s in sample})
    rng.shuffle(subjects)
    n_folds = max(1, min(args.validate_folds, len(subjects)))
    fold_of = {subj: i % n_folds for i, subj in enumerate(subjects)}
    ages = scan_ages(cohort, args.age_csv, args.age_units, args.age_regex, args.age_column)
    usable = [s for s in range(len(cohort.scans)) if scan_bin[s] >= 0
              and not too_many_missing(cohort, cohort.scan(s), args.max_missing_tracts)]
    out = defaultdict(list)
    t0 = time.time()
    for f in range(n_folds):
        held = {subj for subj, i in fold_of.items() if i == f}
        train = [s for s in usable if subject_of(cohort.scans[s]) not in held]
        fprior = prior if args.validate_prior == "files" else Prior.from_cohort(
            cohort, bins, [a if subject_of(sc) not in held else None for a, sc in zip(ages, cohort.scans)])
        for name, q, noise in pops:
            model = Population.fit(cohort, fprior, train, q, noise, args.max_iter, device=dev, min_scans=args.min_scans,
                                   sd_folds=args.sd_calibration_folds)
            for s in sample:
                if fold_of[subject_of(cohort.scans[s])] != f:
                    continue
                if args.validate_prior == "files":
                    nrm = prior.norm(s)
                else:
                    nrm = fprior.bin_norm(scan_bin[s]) if scan_bin[s] >= 0 else None
                out[s].append((name, model, nrm))
        log.info("  population models of fold %d/%d: %d settings on %d scans (%.0f s)", f + 1, n_folds, len(pops),
                 len(train), time.time() - t0)
    return out


def population_local(args):
    """(name, method, opts) of the methods imputing the residuals from the population prediction
    (--validate-population-local): knn with each k of --validate-k, siren with each input and omega_0 of the grid at
    its most epochs."""
    out = []
    for m in [x.strip() for x in args.validate_population_local.split(",") if x.strip() and x.strip() != "none"]:
        if m == "knn":
            out += [("knn k={}".format(k), "knn", {"k": k, "weights": "distance"}) for k in parse_list(args.validate_k, int)]
        elif m == "siren":
            cfg = {"hidden": args.hidden_width, "hidden_layers": args.hidden_layers, "lr": args.lr,
                   "epochs": max(parse_list(args.validate_epochs, int))}
            out += [("siren {} omega0={:g}".format(i, o), "siren",
                     {"siren_inputs": i, "seed": args.seed, "siren": dict(cfg, omega0=o)})
                    for i in [x.strip() for x in args.validate_siren_inputs.split(",") if x.strip()]
                    for o in parse_list(args.validate_omega0, float)]
        else:
            raise ValueError("unknown --validate-population-local {} (knn, siren, none)".format(m))
    return out


def validation_configs(args):
    """The method settings to compare: (name, method, opts) and, for siren, the checkpoints (epochs)."""
    methods = [m.strip() for m in args.validate_methods.split(",") if m.strip()]
    for m in methods:
        if m not in METHODS:
            raise ValueError("unknown method {} in --validate-methods ({})".format(m, ", ".join(METHODS)))
    configs = []
    base = {"max_gap": args.max_gap, "max_distance": args.max_distance, "weights": args.knn_weights}
    if "arc-linear" in methods:  # every hidden gap, so it is compared on the same gaps as the others
        for ends in [e.strip() for e in args.validate_arc_ends.split(",") if e.strip()]:
            if ends not in ARC_ENDS:
                raise ValueError("unknown --validate-arc-ends {} ({})".format(ends, ", ".join(ARC_ENDS)))
            configs.append(("arc-linear" if ends == "none" else "arc-linear ends={}".format(ends), "arc-linear",
                            dict(base, max_gap=None, ends=ends)))
    if "linear" in methods:
        configs.append(("linear", "linear", dict(base)))
    if "knn" in methods:
        weights = [w.strip() for w in args.validate_knn_weights.split(",") if w.strip()]
        for w in weights:
            if w not in ("distance", "uniform"):
                raise ValueError("unknown knn weights {} in --validate-knn-weights (distance, uniform)".format(w))
        for k in parse_list(args.validate_k, int):
            for w in weights:
                configs.append(("knn k={} {}".format(k, w), "knn", dict(base, k=k, weights=w)))
    relative = validate_relative(args)
    configs = [(name + (" (z)" if rel else ""), method, dict(opts, relative=rel))
               for rel in relative for name, method, opts in configs]
    if "prior-mean" in methods:
        configs.append(("prior-mean", "prior-mean", dict(base, relative=False)))
    siren = []
    if "siren" in methods:
        for inputs in [x.strip() for x in args.validate_siren_inputs.split(",") if x.strip()]:
            if inputs not in SIREN_INPUTS:
                raise ValueError("unknown SIREN inputs {} ({})".format(inputs, ", ".join(SIREN_INPUTS)))
            for omega0 in parse_list(args.validate_omega0, float):
                for seed in range(args.validate_seeds):
                    for rel in relative:
                        siren.append((inputs, omega0, seed, rel))
    return configs, siren


def validation_prior(cohort, args, configs, siren):
    """The normative prior of the validation (for the settings that need one, and the age bin mean reference): from
    the cohort itself, each scan left out of its own norm (--validate-prior cohort, for a normative cohort), or the
    age bin statistics of --prior-stats-dir (files: from another cohort)."""
    needed = any(o.get("relative") or m == "prior-mean" for _, m, o in configs) or any(x[3] for x in siren) \
        or bool(population_configs(args))
    ages = scan_ages(cohort, args.age_csv, args.age_units, args.age_regex, args.age_column)
    if not needed and (all(a is None for a in ages) or (args.validate_prior == "files" and not args.prior_stats_dir)):
        return None  # only for the age bin reference, which is then left out
    if args.validate_prior == "files":
        if not args.prior_stats_dir:
            raise ValueError("--validate-prior files needs --prior-stats-dir")
        prior = Prior.from_files(cohort, args.prior_stats_dir, ages)
    else:
        prior = Prior.from_cohort(cohort, bins_from_spec(args.bins), ages)
    n = np.bincount(prior.scan_bin[prior.scan_bin >= 0], minlength=len(prior.bins))
    log.info("Prior (%s): age bins %s with %s scans; %d scan(s) without an age bin", args.validate_prior,
             ", ".join(b[2] for b in prior.bins), ", ".join(str(x) for x in n), int((prior.scan_bin < 0).sum()))
    return prior


def report_bins(cohort, args, prior):
    """(age bins, bin of every scan) the validation is reported by: those of the prior, else of --bins with the ages
    of the scans; (None, None) without any age."""
    if prior is not None:
        return prior.bins, prior.scan_bin
    ages = scan_ages(cohort, args.age_csv, args.age_units, args.age_regex, args.age_column)
    if all(a is None for a in ages):
        return None, None
    bins = bins_from_spec(args.bins)
    return bins, scan_bins(ages, bins)


def validate_relative(args):
    """[False] (values), [True] (deviations from the prior) or both, of --validate-relative."""
    out = []
    for x in [v.strip() for v in args.validate_relative.split(",") if v.strip()]:
        if x not in ("no", "yes"):
            raise ValueError("unknown --validate-relative {} (no, yes)".format(x))
        out.append(x == "yes")
    return out


def parse_list(text, kind):
    return [kind(x) for x in str(text).split(",") if x.strip()]


def validate_pass(cohort, Y, hidden, configs, siren, epochs, features, cfg, dev, args, loc_sd, acc, by_loc, by_dist,
                  totals=None, norm=None, age_bin="", metrics=None, models=(), calib=None, local=()):
    """Hide the positions *hidden* ({position: pattern}) of one scan (the metrics *metrics*, default all), impute
    them with every setting and add the errors to the accumulators (per tract and the scan's *age_bin*). *models*:
    (setting, population model, norm of the model) of the population settings; *calib*: accumulator of the errors
    relative to the SDs of population and prior-mean; *local*: (name, method, opts) of the methods imputing the
    residuals from the population prediction."""
    hp = np.zeros(cohort.n_positions, dtype=bool)
    hp[list(hidden)] = True
    hm = np.zeros(len(cohort.metrics), dtype=bool)
    hm[slice(None) if metrics is None else list(metrics)] = True
    pattern = np.array([hidden.get(p, "") for p in range(cohort.n_positions)])
    Ym = Y.copy()
    Ym[np.ix_(hp, hm)] = np.nan
    truth = np.where(hp[:, None] & hm[None, :] & ~np.isnan(Y) & cohort.valid, Y, np.nan)
    # a whole measure hidden: the methods on the scan's own values (or deviations) have nothing to impute it from
    own_only = metrics is not None
    none = np.full(Y.shape, np.nan)
    sds = {}
    dist = nearest_observed(cohort.points, Ym, cohort.valid)
    dbin = np.clip(np.digitize(dist, DISTANCE_BINS) - 1, 0, len(DISTANCE_BINS) - 2)
    preds = {}
    cache = {}
    zcache = {}
    for name, method, opts in configs:
        rel = opts.get("relative", False)
        if (rel or method == "prior-mean") and norm is None:
            continue  # no norm for this scan: these settings are left out
        key = (method + (" (z)" if rel else ""), name, "", np.nan, np.nan, np.nan)
        if own_only and method not in BY_NORM:
            preds[key] = none
            continue
        p = impute_scan(Ym, cohort, method, opts, zcache if rel else cache, norm=norm, relative=rel)
        preds[key] = limit(p, Ym, cohort, dist, args.max_distance, spatial=method in SPATIAL)
        if method == "prior-mean":
            sds[key] = norm[1]
    for name, model, mnorm in models:
        if mnorm is None:
            continue
        p, sd = model.impute(Ym, mnorm)
        key = ("population", name, "", np.nan, np.nan, np.nan)
        pop = limit(p, Ym, cohort, dist, None, spatial=False)
        preds[key] = pop
        sds[key] = sd
        # the residuals from the population prediction imputed by a method on the 3-D neighbours, within
        # --max-distance; the population prediction beyond
        for lname, lmethod, lopts in local:
            lkey = ("population+" + lmethod, "{} + {}".format(name, lname), "", np.nan, np.nan, np.nan)
            if own_only:
                preds[lkey], sds[lkey] = pop, sd
                continue
            if lmethod == "siren":
                pr = impute_scan(Ym, cohort, "siren", lopts, None, features[lopts["siren_inputs"]], dev, (p, sd), True)
            else:
                pr = impute_scan(Ym, cohort, lmethod, lopts, {}, norm=(p, sd), relative=True)
            pr = limit(pr, Ym, cohort, dist, args.max_distance, spatial=True)
            preds[lkey] = np.where(np.isnan(pr), pop, pr)
            sds[lkey] = sd
    for inputs, omega0, seed, rel in siren:
        if rel and norm is None:
            continue
        if own_only:
            for e in epochs:
                preds[("siren (z)" if rel else "siren", "siren {} omega0={:g}{}".format(inputs, omega0, " (z)" if rel
                                                                                          else ""),
                       inputs, omega0, e, seed)] = none
            continue
        Yp = np.where(cohort.has_point[:, None], Ym, np.nan)
        if rel:
            Yp = (Yp - norm[0]) / norm[1]
        ck = fit_siren(features[inputs], Yp, dict(cfg, omega0=omega0, epochs=max(epochs)), dev,
                       seed=args.seed + seed, checkpoints=epochs)
        for e, p in ck.items():
            if rel:
                p = norm[0] + p * norm[1]
            preds[("siren (z)" if rel else "siren", "siren {} omega0={:g}{}".format(inputs, omega0, " (z)" if rel else ""),
                   inputs, omega0, e, seed)] = limit(p, Ym, cohort, dist, args.max_distance)
    hidden_cells = ~np.isnan(truth)
    present = [pat for pat in PATTERNS if (pattern == pat).any()]
    # cells every setting filled, of the settings that fill some of the pattern (arc-linear fills no whole profile)
    common = {}
    for pat in present:
        c = hidden_cells & (pattern == pat)[:, None]
        for key, p in preds.items():
            filled = ~np.isnan(p) & c
            if filled.any():
                c &= ~np.isnan(p)
        common[pat] = c
    nref = np.full(truth.shape, np.nan)  # normalized error of the reference, to compare each setting on its own cells
    if totals is not None:  # reference, not a method: the mean of the other scans at each location
        tsum, tn = totals
        own = ~np.isnan(Y)
        with np.errstate(invalid="ignore", divide="ignore"):
            ref = (tsum - np.where(own, Y, 0.0)) / (tn - own)
        ref = np.where(hidden_cells, ref, np.nan)
        preds[(REFERENCE, "cohort mean (reference)", "", np.nan, np.nan, np.nan)] = ref
        nref = (ref - truth) / loc_sd
    # the second reference: the mean of the scan's age bin (the norm, without the scan's subject); across a range of
    # ages with large changes (infancy) the cohort mean is a poor summary of a scan
    nage = np.full(truth.shape, np.nan) if norm is None else (np.where(hidden_cells, norm[0], np.nan) - truth) / loc_sd
    if calib is not None:  # the errors relative to the predicted SDs: about 1 (RMS) and 95% within 1.96 if right
        for key, sd in sds.items():
            ze = (preds[key] - truth) / sd
            for pat in present:
                for m, metric in enumerate(cohort.metrics):
                    z = ze[(pattern == pat), m]
                    z = z[~np.isnan(z)]
                    if z.size:
                        calib[key[:2] + (pat, metric)] += [z.size, np.sum(z ** 2), np.sum(np.abs(z) <= 1.96)]
    for key, p in preds.items():
        err = p - truth
        nerr = err / loc_sd
        # completed: the cells the setting leaves filled with the age bin mean (a deviation of 0), so every setting is
        # scored on every hidden value
        cerr = err if norm is None else np.where(np.isnan(p), norm[0], p) - truth
        ncerr = cerr / loc_sd
        okr = ~np.isnan(nerr) & ~np.isnan(nref)  # cells with both errors, for the ratio to the reference
        loc = by_loc[key[:5]]
        for pat in present:
            pi = PATTERNS.index(pat)
            h = hidden_cells & (pattern == pat)[:, None]
            ok = h & ~np.isnan(err)
            okn = ok & ~np.isnan(nerr)
            loc[pi, :, :, 0] += h
            loc[pi, :, :, 1] += ok
            loc[pi, :, :, 2] += np.where(ok, err, 0.0) ** 2
            loc[pi, :, :, 3] += np.where(okn, nerr, 0.0) ** 2
            loc[pi, :, :, 4] += okn
            nb = len(DISTANCE_BINS) - 1
            for m, metric in enumerate(cohort.metrics):
                hm = h[:, m]
                if not hm.any():
                    continue
                b = dbin[hm, m]
                d = by_dist[key[:5] + (pat, metric)]
                d[:, 0] += np.bincount(b, minlength=nb)
                d[:, 1] += np.bincount(b, weights=ok[hm, m], minlength=nb)
                d[:, 2] += np.bincount(b, weights=np.where(okn[hm, m], nerr[hm, m], 0.0) ** 2, minlength=nb)
                d[:, 3] += np.bincount(b, weights=okn[hm, m], minlength=nb)
                d[:, 4] += np.bincount(b, weights=np.where(okr[hm, m], nerr[hm, m], 0.0) ** 2, minlength=nb)
                d[:, 5] += np.bincount(b, weights=np.where(okr[hm, m], nref[hm, m], 0.0) ** 2, minlength=nb)
                oka = okn[hm, m] & ~np.isnan(nage[hm, m])  # paired with the age bin mean
                d[:, 6] += np.bincount(b, weights=np.where(oka, nerr[hm, m], 0.0) ** 2, minlength=nb)
                d[:, 7] += np.bincount(b, weights=np.where(oka, nage[hm, m], 0.0) ** 2, minlength=nb)
        for pat in present:
            rowsel = pattern == pat
            for m, metric in enumerate(cohort.metrics):
                hc = hidden_cells[:, m] & rowsel
                if not hc.any():
                    continue
                for tract, sl in cohort.slices.items():
                    h = hc[sl]
                    if not h.any():
                        continue
                    e = err[sl, m][h]
                    ne = nerr[sl, m][h]
                    ok = ~np.isnan(e)
                    okn = ok & ~np.isnan(ne)
                    c = common[pat][sl, m][h] & okn
                    r = okr[sl, m][h]
                    nr = nref[sl, m][h]
                    na = nage[sl, m][h]
                    ra = okn & ~np.isnan(na)
                    ce = cerr[sl, m][h]
                    nce = ncerr[sl, m][h]
                    rc = ~np.isnan(nce) & ~np.isnan(na)
                    acc[key + (pat, metric, tract, age_bin)] += [h.sum(), ok.sum(), np.sum(e[ok] ** 2), np.sum(ne[okn] ** 2),
                                                        okn.sum(), np.sum(ne[c] ** 2), c.sum(), np.sum(ne[r] ** 2),
                                                        np.sum(nr[r] ** 2), np.sum(ne[ra] ** 2),
                                                        np.sum(na[ra] ** 2), np.sum(ce[rc] ** 2), rc.sum(),
                                                        np.sum(nce[rc] ** 2), np.sum(na[rc] ** 2)]


def calibration_table(calib):
    """The errors relative to the predicted SDs (population: the posterior SD; prior-mean: the SD of the age bin), per
    setting, pattern and metric and as their mean ('all'): RMS of error / SD (1 if the SDs are right) and the share of
    the errors within 1.96 SD (0.95)."""
    rows = [{"method": k[0], "setting": k[1], "pattern": k[2], "metric": k[3], "n": int(a[0]),
             "rms_z": math.sqrt(a[1] / a[0]), "within_1.96sd": a[2] / a[0]} for k, a in calib.items() if a[0] > 0]
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    mean = t.groupby(["method", "setting", "pattern"], as_index=False).agg(
        n=("n", "sum"), rms_z=("rms_z", "mean"), **{"within_1.96sd": ("within_1.96sd", "mean")})
    mean["metric"] = "all"
    return pd.concat([t, mean], ignore_index=True).sort_values(["pattern", "method", "setting", "metric"])


def distance_table(by_dist, cohort):
    """Errors by the distance from a hidden value to the nearest observed position of the same metric, per setting
    and pattern, per metric and as their mean ('all')."""
    rows = []
    for (method, name, inputs, omega0, epochs, pat, metric), d in by_dist.items():
        for b in range(len(DISTANCE_BINS) - 1):
            if d[b, 0] == 0:
                continue
            rows.append({"method": method, "setting": name, "siren_inputs": inputs, "omega0": omega0,
                         "epochs": epochs, "pattern": pat, "metric": metric,
                         "distance_mm": "{:g}-{:g}".format(DISTANCE_BINS[b], DISTANCE_BINS[b + 1]),
                         "distance_lo": DISTANCE_BINS[b], "n_hidden": int(d[b, 0]), "n_filled": int(d[b, 1]),
                         "coverage": d[b, 1] / d[b, 0],
                         "nrmse": math.sqrt(d[b, 2] / d[b, 3]) if d[b, 3] > 0 else np.nan,
                         "vs_reference": math.sqrt(d[b, 4] / d[b, 5]) if d[b, 5] > 0 else np.nan,
                         "vs_age_mean": math.sqrt(d[b, 6] / d[b, 7]) if d[b, 7] > 0 else np.nan,
                         # the sums of the squared normalized errors of the setting and of the age bin mean on the
                         # same values, e.g. to score a --max-distance from a run without one
                         "nsse_paired_age": d[b, 6], "nsse_age_mean": d[b, 7]})
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    keys = ["method", "setting", "siren_inputs", "omega0", "epochs", "pattern", "distance_mm", "distance_lo"]
    mean = t.groupby(keys, as_index=False, dropna=False).agg(n_hidden=("n_hidden", "sum"), n_filled=("n_filled", "sum"),
                                                             nrmse=("nrmse", "mean"), vs_reference=("vs_reference", "mean"),
                                                             vs_age_mean=("vs_age_mean", "mean"))
    mean["metric"] = "all"
    mean["coverage"] = mean["n_filled"] / mean["n_hidden"]
    t = pd.concat([t, mean], ignore_index=True)
    return t.sort_values(["pattern", "method", "setting", "epochs", "metric", "distance_lo"]).drop(columns="distance_lo")


def validate(cohort, args):
    """Hide observed values of a sample of scans, impute them with every setting to compare, and write the errors
    to *args.report_dir*/validation. Returns the summary table."""
    if cohort.points is None:
        raise ValueError("--validate needs --axis-dir")
    out = os.path.join(args.report_dir, "validation")
    os.makedirs(out, exist_ok=True)
    configs, siren = validation_configs(args)
    epochs = parse_list(args.validate_epochs, int)
    rng = np.random.default_rng(args.validate_seed)
    shares = np.stack([scan_shares(cohort, cohort.scan(s)) for s in range(len(cohort.scans))])
    has = shares > 0  # metrics a scan doesn't have at all (e.g. no NODDI) don't count against it
    eligible = has.any(axis=1) & ((shares >= args.min_observed) | ~has).all(axis=1)
    for s in np.flatnonzero(eligible):  # scans the imputation leaves (--max-missing-tracts) are not validated either
        eligible[s] = not too_many_missing(cohort, cohort.scan(s), args.max_missing_tracts)
    eligible = np.flatnonzero(eligible)
    prior = validation_prior(cohort, args, configs, siren)
    bins, scan_bin = report_bins(cohort, args, prior)
    pops = population_configs(args)
    if pops and (bins is None or not (scan_bin >= 0).any()):
        log.warning("population is left out of the validation: it needs the ages of the scans (--age-csv or "
                    "--age-regex)")
        pops = []
    families = [x.strip() for x in args.validate_measure_families.split(",") if x.strip() and x.strip() != "none"]
    for x in families:
        if x not in FAMILIES:
            raise ValueError("unknown --validate-measure-families {} ({})".format(x, ", ".join(FAMILIES)))
    if args.validate_scans_per_bin > 0:
        if bins is None:
            raise ValueError("--validate-scans-per-bin needs ages")
        sample = []
        for b in range(len(bins)):
            pool = eligible[scan_bin[eligible] == b]
            sample += rng.choice(pool, size=min(args.validate_scans_per_bin, len(pool)), replace=False).tolist()
        sample = sorted(sample)
    else:
        sample = sorted(rng.choice(eligible, size=min(args.validate_scans, len(eligible)), replace=False).tolist())
    label = (lambda s: "") if bins is None else (lambda s: bins[scan_bin[s]][2] if scan_bin[s] >= 0 else "none")
    log.info("Validation on %d of %d scans (%d eligible: each metric they have at least %g observed, at most %g of the "
             "tracts missing), %d round(s) of hidden values per scan%s", len(sample), len(cohort.scans), len(eligible),
             args.min_observed, args.max_missing_tracts,
             args.validate_rounds, "" if bins is None else "; per age bin: " + ", ".join(
                 "{} {}".format(b[2], sum(scan_bin[s] == i for s in sample)) for i, b in enumerate(bins)))
    # the scans of the same subject (other sessions) are left out of the norm and the reference with the scan itself
    subject_scans = defaultdict(list)
    for i, scan in enumerate(cohort.scans):
        subject_scans[subject_of(scan)].append(i)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        loc_sd = np.nanstd(cohort.values, axis=0)  # between-scan SD per position and metric (normalizes the errors)
    # floor: a quarter of the metric's median between-scan SD, so a location where a metric hardly varies (e.g. the
    # free water fraction in deep white matter) doesn't blow up the normalized error
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        floor = SD_FLOOR * np.nanmedian(np.where(loc_sd > 0, loc_sd, np.nan), axis=0)
    loc_sd = np.where(np.isfinite(loc_sd), np.fmax(loc_sd, floor[None, :]), np.nan)
    loc_sd = np.where(loc_sd > 0, loc_sd, np.nan)
    gap_mm = tuple(parse_list(args.validate_gap_mm, float))
    dev = pick_device(args.device) if siren or pops else None
    features = {inputs: siren_features(cohort, inputs) for inputs in {s[0] for s in siren}}
    cfg = {"hidden": args.hidden_width, "hidden_layers": args.hidden_layers, "lr": args.lr}
    if siren:
        log.info("SIREN grid on %s: inputs %s, omega_0 %s, epochs %s, %d seed(s)", dev, args.validate_siren_inputs,
                 args.validate_omega0, args.validate_epochs, args.validate_seeds)
    # (method, setting, siren inputs, omega0, epochs, seed, pattern, metric, tract) -> n hidden, n filled, squared
    # error, squared normalized error, n normalized, squared normalized error on the common cells, n common
    acc = defaultdict(lambda: np.zeros(15))
    # (method, setting, siren inputs, omega0, epochs) -> (pattern, position, metric, [n hidden, n filled, squared
    # error, squared normalized error, n normalized]), summed over scans, rounds and SIREN seeds
    shape = (len(PATTERNS), cohort.n_positions, len(cohort.metrics), 5)
    by_loc = defaultdict(lambda: np.zeros(shape, dtype=np.float32))
    # (method, setting, siren inputs, omega0, epochs, pattern, metric) -> (distance bins, [n hidden, n filled,
    # squared normalized error, n normalized])
    by_dist = defaultdict(lambda: np.zeros((len(DISTANCE_BINS) - 1, 8)))
    region_mm = tuple(parse_list(args.validate_region_mm, float))
    end_mm = tuple(parse_list(args.validate_end_gap_mm, float))
    totals = None
    if args.validate_reference:
        vals = cohort.values.astype(np.float64)
        totals = (np.nansum(vals, axis=0), (~np.isnan(vals)).sum(axis=0).astype(np.float64))
        del vals
    models, local = {}, population_local(args)
    for inputs in {o["siren_inputs"] for _, m, o in local if m == "siren"} - set(features):
        features[inputs] = siren_features(cohort, inputs)
    if pops:
        log.info("Population models on %s: %s, %d fold(s) by subject", dev, ", ".join(p[0] for p in pops),
                 args.validate_folds)
        models = population_folds(cohort, args, sample, prior, bins, scan_bin, pops, dev)
    calib = defaultdict(lambda: np.zeros(3))  # (method, setting, pattern, metric) -> n, sum z^2, n |z| <= 1.96
    measure_rng = np.random.default_rng(args.validate_seed + 2)  # own stream: the other hidden values stay the same
    t0 = time.time()
    rounds = [(s, r) for s in sample for r in range(args.validate_rounds)]
    for n, (s, r) in enumerate(rounds, 1):
        Y = cohort.scan(s)
        others = [o for o in subject_scans[subject_of(cohort.scans[s])] if o != s] \
            if args.validate_leave_out == "subject" else []
        norm = None if prior is None else prior.norm(s, Y, [(cohort.scan(o), prior.scan_bin[o]) for o in others])
        tot = totals
        if totals is not None and others:
            vals = cohort.values[others].astype(np.float64)
            tot = (totals[0] - np.nansum(vals, axis=0), totals[1] - (~np.isnan(vals)).sum(axis=0))
        # pass 1: random whole profiles and gaps; pass 2: a region (its own pass, so it doesn't take the neighbours of
        # the profiles of pass 1)
        passes = [hide(cohort, Y, rng, args.validate_gap_fraction, gap_mm, args.validate_whole_fraction,
                       args.validate_end_gap_fraction, end_mm)]
        if args.validate_region_count > 0:
            passes.append(hide_region(cohort, Y, rng, region_mm, args.validate_region_count))
        passes = [(hidden, None) for hidden in passes]
        if families:  # pass 3: a whole measure (a family of metrics), the other metrics all observed
            passes.append(hide_measure(cohort, Y, measure_rng, families))
        for hidden, metrics in passes:
            if hidden:
                validate_pass(cohort, Y, hidden, configs, siren, epochs, features, cfg, dev, args, loc_sd, acc,
                              by_loc, by_dist, tot, norm, label(s), metrics, models.get(s, ()), calib, local)
        log.info("  ... %d/%d scans%s validated (%.0f s)", n, len(rounds),
                 "" if args.validate_rounds == 1 else " x rounds", time.time() - t0)

    rows = []
    for k, a in acc.items():
        method, name, inputs, omega0, epochs_, seed, pat, metric, tract, age_bin = k
        cn = a[6]
        rows.append({"method": method, "setting": name, "siren_inputs": inputs, "omega0": omega0, "epochs": epochs_,
                     "seed": seed, "pattern": pat, "metric": metric, "tract": tract, "age_bin": age_bin, "n_hidden": int(a[0]),
                     "n_filled": int(a[1]), "sse": a[2], "nsse": a[3], "n_norm": int(a[4]), "nsse_common": a[5],
                     "n_common": int(cn), "nsse_paired": a[7], "nsse_reference": a[8],
                     "nsse_paired_age": a[9], "nsse_age_mean": a[10], "sse_completed": a[11],
                     "n_completed": int(a[12]), "nsse_completed": a[13], "nsse_age_mean_completed": a[14]})
    cells = pd.DataFrame(rows)
    by_tract = aggregate(cells, ["method", "setting", "siren_inputs", "omega0", "epochs", "seed", "pattern", "metric", "tract"])
    prox = axis_proximity(cohort)
    prox.to_csv(os.path.join(out, "axis_proximity.csv"), index=False)
    by_tract = by_tract.merge(prox[["tract", "median_mm", "share_within_2mm"]].rename(
        columns={"median_mm": "axis_median_mm_to_other_tract", "share_within_2mm": "axis_share_within_2mm"}),
        on="tract", how="left")
    by_tract.to_csv(os.path.join(out, "validation_by_tract.csv"), index=False)
    per_seed = aggregate(cells, ["method", "setting", "siren_inputs", "omega0", "epochs", "seed", "pattern", "metric"])
    per_seed.to_csv(os.path.join(out, "validation_by_metric.csv"), index=False)
    if bins is not None:
        aggregate(cells, ["method", "setting", "siren_inputs", "omega0", "epochs", "seed", "pattern", "metric",
                          "age_bin"]).to_csv(os.path.join(out, "validation_by_age_bin.csv"), index=False)
    # every metric counts the same: the mean of the errors of the metrics (pooled squared errors would be dominated by
    # the metric with the largest normalized errors)
    summary = per_seed.groupby(["method", "setting", "siren_inputs", "omega0", "epochs", "seed", "pattern"],
                               as_index=False, dropna=False).agg(
        n_hidden=("n_hidden", "sum"), n_filled=("n_filled", "sum"), nrmse=("nrmse", "mean"),
        nrmse_common=("nrmse_common", "mean"), vs_reference=("vs_reference", "mean"),
        vs_age_mean=("vs_age_mean", "mean"), vs_age_mean_completed=("vs_age_mean_completed", "mean"))
    summary["coverage"] = summary["n_filled"] / summary["n_hidden"].where(summary["n_hidden"] > 0)
    summary = summary.groupby(["method", "setting", "siren_inputs", "omega0", "epochs", "pattern"], as_index=False,
                              dropna=False).agg(
        n_seeds=("seed", "size"), n_hidden=("n_hidden", "mean"), coverage=("coverage", "mean"),
        nrmse=("nrmse", "mean"), nrmse_sd=("nrmse", "std"), nrmse_common=("nrmse_common", "mean"),
        vs_reference=("vs_reference", "mean"), vs_age_mean=("vs_age_mean", "mean"),
        vs_age_mean_completed=("vs_age_mean_completed", "mean"))
    summary = summary.sort_values(["pattern", "nrmse_common", "nrmse"])
    summary.to_csv(os.path.join(out, "validation_summary.csv"), index=False)
    with open(os.path.join(out, "validation_settings.json"), "w") as fh:
        json.dump({"scans": [cohort.scans[s] for s in sample], "leave_out": args.validate_leave_out,
                   "scans_per_bin": args.validate_scans_per_bin, "rounds": args.validate_rounds,
                   "measure_families": families,
                   "population": {"components": args.validate_components, "noise": args.validate_noise,
                                  "folds": args.validate_folds, "max_iter": args.max_iter,
                                  "min_scans": args.min_scans} if pops else None,
                   "gap_fraction": args.validate_gap_fraction, "knn_weights": args.validate_knn_weights,
                   "gap_mm": gap_mm, "whole_fraction": args.validate_whole_fraction,
                   "region_mm": region_mm, "region_count": args.validate_region_count,
                   "end_gap_fraction": args.validate_end_gap_fraction, "end_gap_mm": end_mm,
                   "arc_ends": args.validate_arc_ends, "reference": bool(args.validate_reference),
                   "max_distance": args.max_distance, "max_gap": args.max_gap, "min_observed": args.min_observed,
                   "siren": dict(cfg, inputs=args.validate_siren_inputs, omega0=args.validate_omega0,
                                 epochs=args.validate_epochs, seeds=args.validate_seeds, device=dev)}, fh, indent=1)
    if siren and not args.no_plots:
        plot_epochs(summary, os.path.join(out, "validation_siren_epochs.png"))
    write_location_errors(cohort, by_loc, summary, out, args.validate_location_settings, args.validate_min_n,
                          args.no_plots)
    distance_table(by_dist, cohort).to_csv(os.path.join(out, "validation_by_distance.csv"), index=False)
    if calib:
        calibration_table(calib).to_csv(os.path.join(out, "validation_calibration.csv"), index=False)
    log.info("Wrote the validation to %s/ (validation_summary.csv: error per setting and pattern, normalized by the "
             "between-scan SD at each position; nrmse_common: on the cells every setting filled)", out)
    return summary


def location_settings(summary, which="best"):
    """The settings whose errors per location are written: 'all', or the best setting of each method for each pattern
    (lowest error on the cells every setting filled, then on its own cells)."""
    keys = ["method", "setting", "siren_inputs", "omega0", "epochs"]
    rows = summary
    if which == "best":
        rows = (summary.sort_values(["nrmse_common", "nrmse"], na_position="last")
                .groupby(["method", "pattern"], as_index=False, dropna=False).head(1))
    chosen = []
    for _, r in rows.iterrows():
        k = tuple("" if (isinstance(r[c], float) and np.isnan(r[c]) and c == "siren_inputs") else r[c] for c in keys)
        if k not in chosen:
            chosen.append(k)
    return chosen


def same_key(a, b):
    return all((x == y) or (isinstance(x, float) and isinstance(y, float) and np.isnan(x) and np.isnan(y))
               for x, y in zip(a, b))


def slug(key):
    method, name, inputs, omega0, epochs = key
    text = name if method != "siren" else "{} epochs={:g}".format(name, epochs)
    return re.sub(r"[^A-Za-z0-9.]+", "_", text).strip("_")


def location_table(cohort, key, loc):
    """Errors per location (and their mean over the metrics, metric 'all') of one setting, positions with hidden values."""
    rows = []
    method, name, inputs, omega0, epochs = key
    pts = np.where(cohort.has_point[:, None], cohort.points, np.nan) if cohort.points is not None else \
        np.full((cohort.n_positions, 3), np.nan)
    for pi, pat in enumerate(PATTERNS):
        a = loc[pi].astype(np.float64)
        pooled = a.sum(axis=1)
        pooled[:, 3] = metric_mean_nrmse(a) ** 2  # 'all': the mean of the errors of the metrics, see location_nrmse
        pooled[:, 4] = np.where(np.isfinite(pooled[:, 3]), 1.0, 0.0)
        for m, metric in list(enumerate(cohort.metrics)) + [(None, "all")]:
            v = pooled if m is None else a[:, m]
            sel = np.flatnonzero(v[:, 0] > 0)
            if len(sel) == 0:
                continue
            with np.errstate(invalid="ignore", divide="ignore"):
                rows.append(pd.DataFrame({
                    "method": method, "setting": name, "siren_inputs": inputs, "omega0": omega0, "epochs": epochs,
                    "pattern": pat, "metric": metric, "tract": np.asarray(cohort.tracts)[cohort.tract_of[sel]],
                    "arc_length": cohort.arcs[sel], "x": pts[sel, 0], "y": pts[sel, 1], "z": pts[sel, 2],
                    "n_hidden": v[sel, 0].astype(int), "n_filled": v[sel, 1].astype(int),
                    "coverage": v[sel, 1] / v[sel, 0],
                    "rmse": np.sqrt(v[sel, 2] / np.where(v[sel, 1] > 0, v[sel, 1], np.nan)) if m is not None else np.nan,
                    "nrmse": np.sqrt(v[sel, 3] / np.where(v[sel, 4] > 0, v[sel, 4], np.nan))}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def metric_mean_nrmse(a):
    """Per location, the mean over the metrics of their normalized RMSE (a: positions x metrics x sums)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        per_metric = np.sqrt(a[:, :, 3] / np.where(a[:, :, 4] > 0, a[:, :, 4], np.nan))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmean(per_metric, axis=1)


def write_error_polydata(cohort, loc, path):
    """The tract axes at the profile locations (one polyline per tract) with the errors of one setting as point data:
    <pattern>_n (hidden values), <pattern>_nrmse (mean over the metrics) and <pattern>_nrmse_<metric>, pattern
    gap or whole; NaN where nothing was hidden or filled."""
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk
    from dtiplayground.dmri.fiberprofile.analysis.fiber_axis import write_polydata
    keep = np.flatnonzero(cohort.has_point)
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(cohort.points[keep].astype(np.float32), deep=True))
    lines = vtk.vtkCellArray()
    index = {p: i for i, p in enumerate(keep)}
    for tract, sl in cohort.slices.items():
        ids = [index[p] for p in range(sl.start, sl.stop) if p in index]
        if len(ids) >= 2:
            lines.InsertNextCell(len(ids))
            for i in ids:
                lines.InsertCellPoint(i)
    poly = vtk.vtkPolyData()
    poly.SetPoints(points)
    poly.SetLines(lines)

    def add(name, values):
        arr = numpy_to_vtk(np.asarray(values, dtype=np.float32), deep=True)
        arr.SetName(name)
        poly.GetPointData().AddArray(arr)

    add("arc_length", cohort.arcs[keep])
    with np.errstate(invalid="ignore", divide="ignore"):
        for pi, short in enumerate(SHORT[pat] for pat in PATTERNS):
            a = loc[pi][keep].astype(np.float64)
            pooled = a.sum(axis=1)
            add("{}_n".format(short), pooled[:, 0])
            add("{}_nrmse".format(short), metric_mean_nrmse(a))
            for m, metric in enumerate(cohort.metrics):
                add("{}_nrmse_{}".format(short, metric), np.sqrt(a[:, m, 3] / np.where(a[:, m, 4] > 0, a[:, m, 4], np.nan)))
    poly.GetPointData().SetActiveScalars("whole_nrmse")
    write_polydata(poly, path, binary=True)


def plot_error_map(cohort, loc, title, path, min_n):
    """The normalized error per location (mean over the metrics) in three projections, per pattern; locations with
    fewer than *min_n* hidden values in gray."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keep = cohort.has_point
    pts = cohort.points
    views = [("axial (x-y)", 0, 1), ("coronal (x-z)", 0, 2), ("sagittal (y-z)", 1, 2)]
    rows = [pi for pi in range(len(PATTERNS)) if loc[pi, :, :, 0].sum() > 0]
    fig, axes = plt.subplots(len(rows), 3, figsize=(15, 4.8 * len(rows)), squeeze=False)
    errs = {}
    for pi in rows:
        a = loc[pi].astype(np.float64)
        errs[pi] = (metric_mean_nrmse(a), a.sum(axis=1)[:, 0])
    good = np.concatenate([e[(n >= min_n) & keep & np.isfinite(e)] for e, n in errs.values()])
    vmax = float(np.percentile(good, 95)) if good.size else 1.0
    for row, pi in enumerate(rows):
        pat = PATTERNS[pi]
        e, n = errs[pi]
        ok = keep & (n >= min_n) & np.isfinite(e)
        few = keep & ~ok
        for j, (label, a, b) in enumerate(views):
            ax = axes[row][j]
            ax.scatter(pts[few, a], pts[few, b], s=2, c="0.85", lw=0)
            order = np.flatnonzero(ok)[np.argsort(e[ok])]  # largest errors drawn last
            sc = ax.scatter(pts[order, a], pts[order, b], s=5, c=e[order], cmap="magma_r", vmin=0, vmax=vmax, lw=0)
            ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            ax.set_title("hidden {}s: {}".format(pat, label), fontsize=10)
        fig.colorbar(sc, ax=axes[row], shrink=0.8, label="normalized RMSE")
    fig.suptitle("{} -- error per location (gray: fewer than {} hidden values)".format(title, min_n), fontsize=12)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def write_location_errors(cohort, by_loc, summary, out, which, min_n, no_plots):
    """Errors per location of the chosen settings: validation_by_location.csv, and per setting a VTK file of the
    tract axes with the errors as point data and a figure (error_maps/)."""
    chosen = location_settings(summary, which)
    keys = [k for c in chosen for k in by_loc if same_key(k, c)]
    if not keys:
        return
    maps = os.path.join(out, "error_maps")
    os.makedirs(maps, exist_ok=True)
    tables = []
    for key in keys:
        tables.append(location_table(cohort, key, by_loc[key]))
        write_error_polydata(cohort, by_loc[key], os.path.join(maps, slug(key) + ".vtk"))
        if not no_plots:
            title = key[1] if key[0] != "siren" else "{}, {:g} epochs".format(key[1], key[4])
            plot_error_map(cohort, by_loc[key], title, os.path.join(maps, slug(key) + ".png"), min_n)
    pd.concat(tables, ignore_index=True).to_csv(os.path.join(out, "validation_by_location.csv"), index=False)
    log.info("Wrote the errors per location of %d setting(s) (%s) to validation_by_location.csv and %s/", len(keys),
             which, maps)


def aggregate(cells, keys):
    g = cells.groupby(keys, as_index=False, dropna=False).agg(
        n_hidden=("n_hidden", "sum"), n_filled=("n_filled", "sum"), sse=("sse", "sum"), nsse=("nsse", "sum"),
        n_norm=("n_norm", "sum"), nsse_common=("nsse_common", "sum"), n_common=("n_common", "sum"),
        nsse_paired=("nsse_paired", "sum"), nsse_reference=("nsse_reference", "sum"),
        nsse_paired_age=("nsse_paired_age", "sum"), nsse_age_mean=("nsse_age_mean", "sum"),
        sse_completed=("sse_completed", "sum"), n_completed=("n_completed", "sum"),
        nsse_completed=("nsse_completed", "sum"), nsse_age_mean_completed=("nsse_age_mean_completed", "sum"))
    g["coverage"] = g["n_filled"] / g["n_hidden"].where(g["n_hidden"] > 0)
    g["rmse"] = np.sqrt(g["sse"] / g["n_filled"].where(g["n_filled"] > 0))
    g["nrmse"] = np.sqrt(g["nsse"] / g["n_norm"].where(g["n_norm"] > 0))
    g["nrmse_common"] = np.sqrt(g["nsse_common"] / g["n_common"].where(g["n_common"] > 0))
    # the error relative to that of the reference on the same cells: below 1, better than the cohort mean
    g["vs_reference"] = np.sqrt(g["nsse_paired"] / g["nsse_reference"].where(g["nsse_reference"] > 0))
    # ... and to that of the mean of the scan's age bin (the norm; with a prior only)
    g["vs_age_mean"] = np.sqrt(g["nsse_paired_age"] / g["nsse_age_mean"].where(g["nsse_age_mean"] > 0))
    # ... and both on every hidden value, the cells the setting leaves filled with the age bin mean
    g["rmse_completed"] = np.sqrt(g["sse_completed"] / g["n_completed"].where(g["n_completed"] > 0))
    g["vs_age_mean_completed"] = np.sqrt(g["nsse_completed"] / g["nsse_age_mean_completed"].where(
        g["nsse_age_mean_completed"] > 0))
    return g.drop(columns=["sse", "nsse", "nsse_common", "nsse_paired", "nsse_reference", "nsse_paired_age",
                           "nsse_age_mean", "sse_completed", "nsse_completed", "nsse_age_mean_completed"])


def plot_epochs(summary, path):
    """Normalized error against the epochs of every SIREN setting, per pattern, with the other methods as lines."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pats = [p for p in PATTERNS if p in set(summary["pattern"])]
    fig, axes = plt.subplots(1, len(pats), figsize=(6.5 * len(pats), 4.8), squeeze=False)
    colors = dict(zip(SIREN_INPUTS, ["#4C72B0", "#DD8452", "#55A868"]))
    styles = ["-", "--", ":", "-."]
    for ax, pat in zip(axes[0], pats):
        d = summary[summary["pattern"] == pat]
        sir = d[d["method"].str.startswith("siren")]
        for meth, marker in (("siren", "o"), ("siren (z)", "^")):
            for j, omega0 in enumerate(sorted(sir["omega0"].unique())):
                for inputs in SIREN_INPUTS:
                    c = sir[(sir["method"] == meth) & (sir["siren_inputs"] == inputs) & (sir["omega0"] == omega0)]
                    c = c.sort_values("epochs")
                    if len(c):
                        ax.errorbar(c["epochs"], c["nrmse"], yerr=c["nrmse_sd"].fillna(0), color=colors[inputs],
                                    ls=styles[j % len(styles)], marker=marker, ms=4, capsize=2,
                                    label="{} ω0={:g}{}".format(inputs, omega0, " (z)" if meth != "siren" else ""))
        others = d[~d["method"].str.startswith("siren") & np.isfinite(d["nrmse"])]
        grays = plt.cm.Greys(np.linspace(0.45, 0.95, max(len(others), 1)))
        for k, (_, r) in enumerate(others.iterrows()):
            ax.axhline(r["nrmse"], color=grays[k], lw=1.2, ls=styles[k % len(styles)], label=r["setting"])
        ax.set_xscale("log")
        ax.set_xlabel("epochs")
        ax.set_ylabel("normalized RMSE (error / between-scan SD)")
        ax.set_title("hidden {}s".format(pat))
        ax.grid(alpha=0.3)
    for ax in axes[0]:
        ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


### command line

def add_parser(subparsers):
    p = subparsers.add_parser(
        "impute-profiles", help="Impute missing profile values from the same scan (3-D neighbours of the tract axes)",
        description="Impute the missing values of profile tables (e.g. Profiles_Clean of qc-profiles): blank cells and "
                    "whole profiles (a scan absent from the table of a tract but present in others; excluded and "
                    "missing profiles are treated the same). Each scan and metric is imputed from its own observed "
                    "values, using the 3-D positions of the tract axes (--axis-dir, compute-axis). The output mirrors "
                    "the input; observed cells are copied verbatim. --validate compares the methods and settings on "
                    "hidden observed values instead.")
    p.add_argument("--profiles-dir", required=True, help="Profile tables, in any layout qc-profiles reads (e.g. Profiles_Clean)")
    p.add_argument("--axis-dir", default=None, help="Tract axes <tract>_axis.vtk (compute-axis); needed by every method but arc-linear")
    p.add_argument("--out-dir", default="Profiles_Imputed", help="Imputed tables, same layout as the input (default: Profiles_Imputed)")
    p.add_argument("--report-dir", default=None,
                   help="Masks of the imputed cells (masks/), imputation_summary.csv and the validation (validation/) "
                        "(default: <out-dir>_report)")
    p.add_argument("--method", default=None, choices=METHODS,
                   help="Imputation method (default: with --prior-stats-dir or --model siren, on the deviations from "
                        "the population prediction (--norm); without, arc-linear, which fills only the gaps inside "
                        "profiles: from the scan's own values, whole profiles are imputed worse than by the age bin "
                        "mean, see the documentation)")
    p.add_argument("--fallback", default=None, choices=("none",) + METHODS,
                   help="Method for the cells the first one leaves, e.g. positions farther than --max-distance from an "
                        "observed one (default: with --prior-stats-dir population, or prior-mean (the age bin mean) "
                        "with --norm age-bin; without, none)")
    p.add_argument("--k", type=int, default=None,
                   help="knn: number of neighbours (default: 20 on the deviations from the norm, 1 on the values)")
    p.add_argument("--knn-weights", default="distance", choices=("distance", "uniform"),
                   help="knn: weight the neighbours by 1/distance or equally (default: distance)")
    p.add_argument("--max-distance", type=float, default=None,
                   help="linear, knn, siren: cells farther than this (mm) from an observed position of the same metric "
                        "are left (to --fallback); 0: no limit (default: 4 on the deviations from the population "
                        "prediction, 20 on those from the age bin norm, 10 on the values)")
    p.add_argument("--arc-ends", default=None, choices=ARC_ENDS,
                   help="arc-linear: the missing start and end of a profile: left, the nearest observed value repeated, "
                        "or the line through the 3 nearest observed values extended (up to --max-gap mm) (default: "
                        "constant on the deviations from the norm, none on the values)")
    p.add_argument("--max-gap", type=float, default=15.0,
                   help="arc-linear: longest gap (mm, between its observed ends) filled, the range of the validation; "
                        "0: no limit (default: 15)")
    p.add_argument("--min-observed", type=float, default=0.5,
                   help="A metric of a scan with a smaller share of observed values is not imputed (default: 0.5)")
    p.add_argument("--max-missing-tracts", type=float, default=0.5,
                   help="A scan missing a larger share of its tracts (no observed value of any metric, e.g. excluded by "
                        "qc-profiles) is not imputed at all: its imputed values would be little more than the norm; "
                        "1: no limit (default: 0.5)")
    p.add_argument("--siren-inputs", default=None, choices=SIREN_INPUTS,
                   help="siren: network inputs, the 3-D position alone, with the arc length, or with the tract (one-hot) "
                        "(default: xyz on the deviations from the norm, xyz+tract on the values)")
    p.add_argument("--epochs", type=int, default=None,
                   help="siren: training epochs (default: 500 on the deviations from the norm, 1000 on the values)")
    p.add_argument("--omega0", type=float, default=None,
                   help="siren: omega_0 (default: 10 on the deviations from the norm, 30 on the values)")
    p.add_argument("--hidden-layers", type=int, default=3, help="siren: hidden sine layers (default: 3)")
    p.add_argument("--hidden-width", type=int, default=256, help="siren: layer width (default: 256)")
    p.add_argument("--lr", type=float, default=1e-4, help="siren: Adam learning rate (default: 1e-4)")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"], help="siren: torch device (default: auto)")
    p.add_argument("--seed", type=int, default=0, help="siren: random seed (default: 0)")
    n = p.add_argument_group("normative prior (deviations from the norm, prior-mean)")
    n.add_argument("--prior-stats-dir", default=None,
                   help="Age bin statistics of a normative cohort (*_agebinstats.csv of qc-profiles, either layout)")
    n.add_argument("--relative-to-prior", action=argparse.BooleanOptionalAction, default=None,
                   help="The method imputes the deviations of the scan from the norm of its age bin, (value - mean) / "
                        "SD at each location, which are turned back into values with the norm of the imputed location "
                        "(default: with --prior-stats-dir; --no-relative-to-prior imputes the values)")
    n.add_argument("--norm", default=None, choices=NORMS,
                   help="With --relative-to-prior, the norm the deviations are from: the scan's own prediction by the "
                        "population model from all its observed values (population, default), or the mean and SD of "
                        "its age bin (age-bin, as before 0.8.21)")
    n.add_argument("--age-csv", default=None,
                   help="Ages of the scans (as qc-profiles --age-csv); else read from the column names (--age-regex)")
    n.add_argument("--age-column", default=None, metavar="NAME", help="--age-csv column of the age (default: auto-detect)")
    n.add_argument("--age-units", default="months", choices=sorted(__import__(
        "dtiplayground.dmri.common.age_table", fromlist=["x"]).AGE_UNIT_TO_MONTHS), help="Units of --age-csv (default: months)")
    n.add_argument("--age-regex", default=None,
                   help="Pattern of the age in months in a column name, group 1 (default: that of qc-profiles, ses-(\\d+)m)")
    n.add_argument("--bins", default=DEFAULT_BINS,
                   help="Validation with --validate-prior cohort, and the errors per age bin: age bins in months, inclusive, the oldest open-ended "
                        "(default: %(default)s, as qc-profiles)")
    g = p.add_argument_group("population model (probabilistic PCA of the deviations from the norm)")
    g.add_argument("--model", default=None, metavar="FILE",
                   help="population: a model fitted on a normative cohort (--fit-model); it carries the norm it was "
                        "fitted with, which then replaces --prior-stats-dir (default: fit on the profiles themselves)")
    g.add_argument("--fit-model", default=None, metavar="FILE",
                   help="Fit the population model on the profiles (a normative cohort, with --prior-stats-dir or the "
                        "norm of their own age bins, --bins) and save it (.npz), e.g. to impute another cohort")
    g.add_argument("--components", type=int, default=None,
                   help="population: number of components (default: %d)" % POPULATION_DEFAULTS["components"])
    g.add_argument("--noise", default=None, choices=NOISE,
                   help="population: noise model, one variance for all cells, one per metric or one per cell (default: "
                        "%s)" % POPULATION_DEFAULTS["noise"])
    g.add_argument("--max-iter", type=int, default=300, help="population: EM iterations at most (default: 300)")
    g.add_argument("--sd-calibration-folds", type=int, default=5,
                   help="population: the SDs are calibrated per metric by fitting the model again in this many folds "
                        "of the scans (by subject), each predicting hidden whole profiles of the others; 0: no "
                        "calibration (default: 5)")
    g.add_argument("--min-scans", type=int, default=10,
                   help="population: cells observed in fewer scans of the fit are left out of the model (default: 10)")
    p.add_argument("--value-format", default="%.6g", help="printf format of the imputed values (default: %%.6g, as EXTRACT_Profile)")
    v = p.add_argument_group("validation (--validate)")
    v.add_argument("--validate", action="store_true",
                   help="Compare methods and settings on hidden observed values of a sample of scans instead of imputing")
    v.add_argument("--validate-scans", type=int, default=30, help="Number of scans (default: 30)")
    v.add_argument("--validate-scans-per-bin", type=int, default=0,
                   help="Instead of --validate-scans: number of scans of each age bin (of the prior or --bins), so "
                        "every age is represented; 0: off (default: 0)")
    v.add_argument("--validate-leave-out", default="subject", choices=("subject", "scan"),
                   help="Left out of the norm (--validate-prior cohort) and of the reference with a validated scan: "
                        "every scan of its subject (subject, default: its other sessions are not independent of it) "
                        "or the scan only")
    v.add_argument("--validate-seed", type=int, default=0, help="Seed of the scan sample and the hidden values (default: 0)")
    v.add_argument("--validate-rounds", type=int, default=1,
                   help="Rounds of hidden values per scan, each with other tracts and gaps; more rounds give more "
                        "hidden values per location (default: 1)")
    v.add_argument("--validate-whole-fraction", type=float, default=0.1,
                   help="Share of the tracts of a scan whose whole profile is hidden (default: 0.1)")
    v.add_argument("--validate-gap-fraction", type=float, default=0.2,
                   help="Share of the other tracts with one hidden gap (default: 0.2)")
    v.add_argument("--validate-gap-mm", default="3,15", help="Range of the gap lengths, mm (default: 3,15)")
    v.add_argument("--validate-region-count", type=int, default=1,
                   help="Regions per scan and round, hidden in a pass of their own: every tract passing through a "
                        "sphere around a random observed position loses its whole profile, as with a regional artifact; "
                        "0: none (default: 1)")
    v.add_argument("--validate-region-mm", default="10,25", help="Range of the region radii, mm (default: 10,25)")
    v.add_argument("--validate-methods", default="arc-linear,linear,knn,siren,prior-mean,population",
                   help="Methods to compare (default: all)")
    v.add_argument("--validate-components", default="5,10,20,40,80",
                   help="population: numbers of components (default: 5,10,20,40,80)")
    v.add_argument("--validate-noise", default=",".join(NOISE), help="population: noise models (default: all)")
    v.add_argument("--validate-folds", type=int, default=5,
                   help="population: the validated scans are split by subject into this many folds; the model of a "
                        "fold is fitted on the cohort without the subjects of the fold (default: 5)")
    v.add_argument("--validate-population-local", default="knn,siren",
                   help="population: methods imputing the residuals from the population prediction on the 3-D "
                        "neighbours (knn: each --validate-k; siren: each input and omega_0 of the grid, at its most "
                        "epochs), or none (default: knn,siren)")
    v.add_argument("--validate-measure-families", default="fw,noddi",
                   help="Families of metrics hidden as a whole measure, one per scan and round in a pass of its own, as "
                        "for a scan without that model fit: %s; none: no such pass (default: fw,noddi)" % ", ".join(
                       "{} ({})".format(k, "/".join(v)) for k, v in FAMILIES.items()))
    v.add_argument("--validate-relative", default="no,yes",
                   help="Compare the methods on the values (no), on the deviations from the prior (yes) or both "
                        "(default: no,yes); the deviations and prior-mean need ages")
    v.add_argument("--validate-prior", default="cohort", choices=("cohort", "files"),
                   help="Prior of the validation: from the profiles themselves, every scan left out of its own norm "
                        "(cohort, default: for a normative cohort, whose statistics include the scans validated), or "
                        "--prior-stats-dir (files: the statistics of another cohort)")
    v.add_argument("--validate-k", default="1,3,5,10,20,50", help="knn: values of k (default: 1,3,5,10,20,50)")
    v.add_argument("--validate-arc-ends", default="none,constant,linear",
                   help="arc-linear: --arc-ends to compare (default: none,constant,linear)")
    v.add_argument("--validate-end-gap-fraction", type=float, default=0.2,
                   help="Share of the tracts (not hidden whole) whose start or end is hidden (default: 0.2)")
    v.add_argument("--validate-end-gap-mm", default="1,8", help="Range of the lengths of the hidden starts and ends, mm (default: 1,8)")
    v.add_argument("--no-validate-reference", dest="validate_reference", action="store_false",
                   help="No reference row (the mean of the other scans at each location)")
    v.add_argument("--validate-knn-weights", default="distance,uniform",
                   help="knn: weightings of the neighbours to compare (default: distance,uniform)")
    v.add_argument("--validate-siren-inputs", default="xyz,xyz+arc,xyz+tract", help="siren: inputs (default: all three)")
    v.add_argument("--validate-omega0", default="5,10,20,30", help="siren: values of omega_0 (default: 5,10,20,30)")
    v.add_argument("--validate-epochs", default="100,200,500,1000",
                   help="siren: epochs, read off one training at each value (default: 100,200,500,1000)")
    v.add_argument("--validate-seeds", type=int, default=3, help="siren: trainings per setting (default: 3)")
    v.add_argument("--validate-location-settings", default="best", choices=("best", "all"),
                   help="Settings whose errors per location are written: the best of each method per pattern, or all "
                        "(default: best)")
    v.add_argument("--validate-min-n", type=int, default=3,
                   help="Error maps: locations with fewer hidden values are drawn gray (default: 3)")
    v.add_argument("--no-plots", action="store_true", help="No plot of the validation")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


# the settings with the smallest error over all four hiding patterns in the validation on a normative cohort (see the
# documentation): on the deviations from the population prediction or from the age bin norm (with a prior), and on the
# scan's own values (without)
DEFAULTS = {"population": {"method": "siren", "fallback": "population", "k": 20, "arc_ends": "constant",
                           "siren_inputs": "xyz", "epochs": 500, "omega0": 10.0, "max_distance": 4.0},
            "age-bin": {"method": "siren", "fallback": "prior-mean", "k": 20, "arc_ends": "constant",
                        "siren_inputs": "xyz", "epochs": 500, "omega0": 10.0, "max_distance": 20.0},
            "values": {"method": "arc-linear", "fallback": "none", "k": 1, "arc_ends": "none",
                       "siren_inputs": "xyz+tract", "epochs": 1000, "omega0": 30.0, "max_distance": 10.0}}


def resolve_defaults(args):
    """Fill the settings left unset: --relative-to-prior when --prior-stats-dir or --model is given, --norm
    population, then the best settings of that mode (DEFAULTS)."""
    if getattr(args, "relative_to_prior", None) is None:
        args.relative_to_prior = bool(args.prior_stats_dir or getattr(args, "model", None))
    if getattr(args, "norm", None) is None:
        args.norm = "population"
    mode = args.norm if args.relative_to_prior else "values"
    for name, value in list(DEFAULTS[mode].items()) + list(POPULATION_DEFAULTS.items()):
        if getattr(args, name, None) is None:
            setattr(args, name, value)
    return args


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
    resolve_defaults(args)
    args.max_distance = args.max_distance or None
    args.max_gap = args.max_gap or None
    args.report_dir = args.report_dir or os.path.normpath(args.out_dir) + "_report"
    tables = read_tables(args.profiles_dir)
    cohort_tracts = sorted({t.tract for t in tables})
    axes = read_axes(args.axis_dir, cohort_tracts) if args.axis_dir else None
    cohort = Cohort(tables, axes)
    log.info("%d tables: %d tracts, %d metrics (%s), %d scans, %d positions", len(tables), len(cohort.tracts),
             len(cohort.metrics), ", ".join(cohort.metrics), len(cohort.scans), cohort.n_positions)
    if axes is not None:
        no_axis = [t for t in cohort.tracts if t not in axes]
        if no_axis:
            log.warning("%d tract(s) have no axis in %s; their positions have no 3-D point and are only imputed by "
                        "arc-linear: %s", len(no_axis), args.axis_dir, ", ".join(no_axis))
    if args.validate:
        validate(cohort, args)
        return 0
    spatial = [m for m in (args.method, args.fallback) if m in SPATIAL]
    if spatial and axes is None:
        log.error("--axis-dir is needed for %s", ", ".join(spatial))
        return 1
    if "siren" in (args.method, args.fallback):
        log.info("siren: one network per scan (inputs %s, omega_0 %g, %d epochs) on %s", args.siren_inputs,
                 args.omega0, args.epochs, pick_device(args.device))
    prior = model = None
    population = "population" in (args.method, args.fallback) or (
        args.relative_to_prior and args.norm == "population" and not {args.method, args.fallback} <= set(BY_NORM + ("none",)))
    if args.relative_to_prior or "prior-mean" in (args.method, args.fallback) or population or args.fit_model:
        ages = scan_ages(cohort, args.age_csv, args.age_units, args.age_regex, args.age_column)
        if args.model:
            model = Population.load(args.model)
            share = model.bind(cohort)
            if share == 0:
                log.error("The model %s has none of the tracts, arc lengths and metrics of the profiles", args.model)
                return 1
            if args.prior_stats_dir:
                log.warning("--prior-stats-dir is not used: the norm is that of the model %s", args.model)
            prior, source = model.prior(cohort, ages), args.model
            log.info("Population model %s: %d components, %s noise, fitted on %d scans; %.0f%% of its cells are in "
                     "the profiles", args.model, model.info["components"], model.info["noise"], model.info["rows"],
                     100 * share)
        elif args.prior_stats_dir:
            prior, source = Prior.from_files(cohort, args.prior_stats_dir, ages), args.prior_stats_dir
        elif population or args.fit_model:  # the norm of the cohort's own age bins
            prior, source = Prior.from_cohort(cohort, bins_from_spec(args.bins), ages), "the profiles' own age bins"
        else:
            log.error("--relative-to-prior and prior-mean need --prior-stats-dir (the age bin statistics of a normative "
                      "cohort, from qc-profiles) or a population --model")
            return 1
        n = np.bincount(prior.scan_bin[prior.scan_bin >= 0], minlength=len(prior.bins))
        log.info("Norm (%s): age bins %s with %s scan(s); %d scan(s) without an age bin are not imputed", source,
                 ", ".join(b[2] for b in prior.bins), ", ".join(str(x) for x in n), int((prior.scan_bin < 0).sum()))
    if model is None and (population or args.fit_model):
        scans = [s for s in range(len(cohort.scans)) if prior.scan_bin[s] >= 0]
        if args.max_missing_tracts is not None:
            scans = [s for s in scans if not too_many_missing(cohort, cohort.scan(s), args.max_missing_tracts)]
        t0 = time.time()
        model = Population.fit(cohort, prior, scans, args.components, args.noise, args.max_iter, device=args.device,
                               min_scans=args.min_scans, sd_folds=args.sd_calibration_folds)
        log.info("Population model: %d components, %s noise, fitted on %d scans and %d cells in %d EM iterations "
                 "(%.0f s with the calibration); the components explain %.0f%% of the variance of the deviations",
                 model.info["components"], args.noise, model.info["rows"], model.info["cells"], model.info["iterations"],
                 time.time() - t0, 100 * model.info["explained"])
        if "sd_scale" in model.info:
            log.info("Population SDs scaled per metric by %s (%d-fold calibration)", ", ".join(
                "{} {:.2f}".format(k, v) for k, v in model.info["sd_scale"].items()), args.sd_calibration_folds)
        if args.fit_model:
            model.save(args.fit_model)
            log.info("Saved the population model to %s", args.fit_model)
    missing = int((np.isnan(cohort.values) & cohort.valid[None]).sum())
    log.info("%d missing cells (blank, or whole profiles of scans absent from a table)", missing)
    opts = {"k": args.k, "weights": args.knn_weights, "max_distance": args.max_distance, "max_gap": args.max_gap,
            "ends": args.arc_ends, "relative": args.relative_to_prior, "norm": args.norm,
            "seed": args.seed, "siren_inputs": args.siren_inputs,
            "siren": {"epochs": args.epochs, "omega0": args.omega0, "hidden": args.hidden_width,
                      "hidden_layers": args.hidden_layers, "lr": args.lr}}
    fallback = None if args.fallback == "none" else args.fallback
    imputed, used, dists, skipped, sds = impute_cohort(cohort, args.method, fallback, opts, args.min_observed,
                                                       args.device, prior=prior,
                                                       max_missing_tracts=args.max_missing_tracts, model=model)
    n = write_tables(cohort, imputed, args.out_dir, os.path.join(args.report_dir, "masks"), args.value_format)
    if population:
        write_values(cohort, sds, os.path.join(args.report_dir, "sd"), args.value_format)
        log.info("SDs of the values imputed by population in %s/", os.path.join(args.report_dir, "sd"))
    summary = summary_rows(cohort, imputed, used, dists, skipped, sds)
    os.makedirs(args.report_dir, exist_ok=True)
    summary.to_csv(os.path.join(args.report_dir, "imputation_summary.csv"), index=False)
    with open(os.path.join(args.report_dir, "imputation_settings.json"), "w") as fh:
        json.dump({k: v for k, v in vars(args).items() if k != "func"}, fh, indent=1, default=str)
    left = missing - n
    log.info("Imputed %d of %d missing cells (%s%s) into %s/; %d left (imputation_summary.csv: left_reason)", n,
             missing, args.method, "" if fallback is None else ", then " + fallback, args.out_dir, left)
    log.info("Masks of the imputed cells and imputation_summary.csv in %s/", args.report_dir)
    return 0
