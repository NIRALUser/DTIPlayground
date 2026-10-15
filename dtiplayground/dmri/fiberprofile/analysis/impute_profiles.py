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
#   --validate hides observed values (gaps within profiles and whole profiles) of a sample of scans, imputes them with
#   the methods and settings to compare, and reports the errors.
#

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

METHODS = ("arc-linear", "linear", "knn", "siren")
SIREN_INPUTS = ("xyz", "xyz+arc", "xyz+tract")
METRIC_ORDER = ["fa", "md", "rd", "ad", "NDI", "ODI", "FWF", "FW_FA", "FW_MD", "FW_RD", "FW_AD"]
GAP, END, WHOLE, REGION = "gap", "end gap", "whole profile", "region"
PATTERNS = (GAP, END, WHOLE, REGION)
SHORT = {GAP: "gap", END: "end", WHOLE: "whole", REGION: "region"}
ARC_ENDS = ("none", "constant", "linear")
REFERENCE = "reference"  # validation: the cohort mean at each location (other scans), as a scale for the errors
# validation: distance (mm) from a hidden value to the nearest observed position of the same metric, bin edges
DISTANCE_BINS = [0.0, 2.0, 4.0, 6.0, 10.0, 15.0, 25.0, np.inf]
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


### imputation of one scan

def impute_scan(Y, cohort, method, opts, cache=None, features=None, device=None):
    """Imputed values (positions x metrics, NaN where not imputed) of one scan with *method*."""
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


### imputation of a cohort

def impute_cohort(cohort, method="knn", fallback=None, opts=None, min_observed=0.5, device="auto", log_every=25):
    """Impute every scan. Returns (imputed values scans x positions x metrics (NaN: not imputed), method index per
    cell (-1: none), distances to the nearest observed position, reasons {(scan, metric): text} for skipped ones)."""
    opts = dict(opts or {})
    methods = [method] + ([fallback] if fallback and fallback != method else [])
    needs_points = any(m != "arc-linear" for m in methods)
    if needs_points and cohort.points is None:
        raise ValueError("--axis-dir is needed for the methods {}".format(", ".join(m for m in methods if m != "arc-linear")))
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
    skipped = {}
    t0 = time.time()
    for s, scan in enumerate(cohort.scans):
        Y = cohort.scan(s)
        missing = np.isnan(Y) & cohort.valid
        if not missing.any():
            continue
        share = scan_shares(cohort, Y)
        for m, metric in enumerate(cohort.metrics):
            if missing[:, m].any() and share[m] < min_observed:
                skipped[(scan, metric)] = ("no observed value" if share[m] == 0 else
                                           "{:.0%} observed, below --min-observed {:g}".format(share[m], min_observed))
        dist = nearest_observed(cohort.points, Y, cohort.valid) if needs_points else np.full(Y.shape, np.inf)
        dists[s] = np.minimum(dist, np.finfo(np.float32).max)
        cache = {}
        for mth in methods:  # a fallback imputes from the observed values too, not from those of the first method
            pred = impute_scan(Y, cohort, mth, opts, cache, features, dev)
            pred = limit(pred, Y, cohort, dist, opts.get("max_distance"), spatial=mth != "arc-linear")
            pred[:, share < min_observed] = np.nan
            new = ~np.isnan(pred) & np.isnan(imputed[s])
            imputed[s][new] = pred[new]
            used[s][new] = METHODS.index(mth)
        if log_every and (s + 1) % log_every == 0:
            log.info("  ... %d/%d scans (%.0f s)", s + 1, len(cohort.scans), time.time() - t0)
    return imputed, used, dists, skipped


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


def summary_rows(cohort, imputed, used, dists, skipped):
    """One row per scan, tract and metric with missing values: what was missing, what was imputed and how."""
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
                             "left_reason": reason})
    return pd.DataFrame(rows, columns=["scan", "tract", "metric", "n_positions", "n_observed", "n_missing", "shape",
                                       "n_imputed", "n_left", "methods", "max_distance_mm", "left_reason"])


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
    siren = []
    if "siren" in methods:
        for inputs in [x.strip() for x in args.validate_siren_inputs.split(",") if x.strip()]:
            if inputs not in SIREN_INPUTS:
                raise ValueError("unknown SIREN inputs {} ({})".format(inputs, ", ".join(SIREN_INPUTS)))
            for omega0 in parse_list(args.validate_omega0, float):
                for seed in range(args.validate_seeds):
                    siren.append((inputs, omega0, seed))
    return configs, siren


def parse_list(text, kind):
    return [kind(x) for x in str(text).split(",") if x.strip()]


def validate_pass(cohort, Y, hidden, configs, siren, epochs, features, cfg, dev, args, loc_sd, acc, by_loc, by_dist,
                  totals=None):
    """Hide the positions *hidden* ({position: pattern}) of one scan, impute them with every setting and add the
    errors to the accumulators."""
    hp = np.zeros(cohort.n_positions, dtype=bool)
    hp[list(hidden)] = True
    pattern = np.array([hidden.get(p, "") for p in range(cohort.n_positions)])
    Ym = Y.copy()
    Ym[hp] = np.nan
    truth = np.where(hp[:, None] & ~np.isnan(Y) & cohort.valid, Y, np.nan)
    dist = nearest_observed(cohort.points, Ym, cohort.valid)
    dbin = np.clip(np.digitize(dist, DISTANCE_BINS) - 1, 0, len(DISTANCE_BINS) - 2)
    preds = {}
    cache = {}
    for name, method, opts in configs:
        p = impute_scan(Ym, cohort, method, opts, cache)
        preds[(method, name, "", np.nan, np.nan, np.nan)] = limit(p, Ym, cohort, dist, args.max_distance,
                                                                   spatial=method != "arc-linear")
    for inputs, omega0, seed in siren:
        Yp = np.where(cohort.has_point[:, None], Ym, np.nan)
        ck = fit_siren(features[inputs], Yp, dict(cfg, omega0=omega0, epochs=max(epochs)), dev,
                       seed=args.seed + seed, checkpoints=epochs)
        for e, p in ck.items():
            preds[("siren", "siren {} omega0={:g}".format(inputs, omega0), inputs, omega0, e, seed)] = \
                limit(p, Ym, cohort, dist, args.max_distance)
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
    for key, p in preds.items():
        err = p - truth
        nerr = err / loc_sd
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
                    acc[key + (pat, metric, tract)] += [h.sum(), ok.sum(), np.sum(e[ok] ** 2), np.sum(ne[okn] ** 2),
                                                        okn.sum(), np.sum(ne[c] ** 2), c.sum(), np.sum(ne[r] ** 2),
                                                        np.sum(nr[r] ** 2)]


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
                         "vs_reference": math.sqrt(d[b, 4] / d[b, 5]) if d[b, 5] > 0 else np.nan})
    t = pd.DataFrame(rows)
    if t.empty:
        return t
    keys = ["method", "setting", "siren_inputs", "omega0", "epochs", "pattern", "distance_mm", "distance_lo"]
    mean = t.groupby(keys, as_index=False, dropna=False).agg(n_hidden=("n_hidden", "sum"), n_filled=("n_filled", "sum"),
                                                             nrmse=("nrmse", "mean"), vs_reference=("vs_reference", "mean"))
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
    eligible = np.flatnonzero(has.any(axis=1) & ((shares >= args.min_observed) | ~has).all(axis=1))
    sample = sorted(rng.choice(eligible, size=min(args.validate_scans, len(eligible)), replace=False).tolist())
    log.info("Validation on %d of %d scans (%d eligible: each metric they have at least %g observed), %d round(s) of "
             "hidden values per scan", len(sample), len(cohort.scans), len(eligible), args.min_observed,
             args.validate_rounds)
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
    dev = pick_device(args.device) if siren else None
    features = {inputs: siren_features(cohort, inputs) for inputs in {s[0] for s in siren}}
    cfg = {"hidden": args.hidden_width, "hidden_layers": args.hidden_layers, "lr": args.lr}
    if siren:
        log.info("SIREN grid on %s: inputs %s, omega_0 %s, epochs %s, %d seed(s)", dev, args.validate_siren_inputs,
                 args.validate_omega0, args.validate_epochs, args.validate_seeds)
    # (method, setting, siren inputs, omega0, epochs, seed, pattern, metric, tract) -> n hidden, n filled, squared
    # error, squared normalized error, n normalized, squared normalized error on the common cells, n common
    acc = defaultdict(lambda: np.zeros(9))
    # (method, setting, siren inputs, omega0, epochs) -> (pattern, position, metric, [n hidden, n filled, squared
    # error, squared normalized error, n normalized]), summed over scans, rounds and SIREN seeds
    shape = (len(PATTERNS), cohort.n_positions, len(cohort.metrics), 5)
    by_loc = defaultdict(lambda: np.zeros(shape, dtype=np.float32))
    # (method, setting, siren inputs, omega0, epochs, pattern, metric) -> (distance bins, [n hidden, n filled,
    # squared normalized error, n normalized])
    by_dist = defaultdict(lambda: np.zeros((len(DISTANCE_BINS) - 1, 6)))
    region_mm = tuple(parse_list(args.validate_region_mm, float))
    end_mm = tuple(parse_list(args.validate_end_gap_mm, float))
    totals = None
    if args.validate_reference:
        vals = cohort.values.astype(np.float64)
        totals = (np.nansum(vals, axis=0), (~np.isnan(vals)).sum(axis=0).astype(np.float64))
        del vals
    t0 = time.time()
    rounds = [(s, r) for s in sample for r in range(args.validate_rounds)]
    for n, (s, r) in enumerate(rounds, 1):
        Y = cohort.scan(s)
        # pass 1: random whole profiles and gaps; pass 2: a region (its own pass, so it doesn't take the neighbours of
        # the profiles of pass 1)
        passes = [hide(cohort, Y, rng, args.validate_gap_fraction, gap_mm, args.validate_whole_fraction,
                       args.validate_end_gap_fraction, end_mm)]
        if args.validate_region_count > 0:
            passes.append(hide_region(cohort, Y, rng, region_mm, args.validate_region_count))
        for hidden in passes:
            if hidden:
                validate_pass(cohort, Y, hidden, configs, siren, epochs, features, cfg, dev, args, loc_sd, acc,
                              by_loc, by_dist, totals)
        log.info("  ... %d/%d scans%s validated (%.0f s)", n, len(rounds),
                 "" if args.validate_rounds == 1 else " x rounds", time.time() - t0)

    rows = []
    for k, a in acc.items():
        method, name, inputs, omega0, epochs_, seed, pat, metric, tract = k
        cn = a[6]
        rows.append({"method": method, "setting": name, "siren_inputs": inputs, "omega0": omega0, "epochs": epochs_,
                     "seed": seed, "pattern": pat, "metric": metric, "tract": tract, "n_hidden": int(a[0]),
                     "n_filled": int(a[1]), "sse": a[2], "nsse": a[3], "n_norm": int(a[4]), "nsse_common": a[5],
                     "n_common": int(cn), "nsse_paired": a[7], "nsse_reference": a[8]})
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
    # every metric counts the same: the mean of the errors of the metrics (pooled squared errors would be dominated by
    # the metric with the largest normalized errors)
    summary = per_seed.groupby(["method", "setting", "siren_inputs", "omega0", "epochs", "seed", "pattern"],
                               as_index=False, dropna=False).agg(
        n_hidden=("n_hidden", "sum"), n_filled=("n_filled", "sum"), nrmse=("nrmse", "mean"),
        nrmse_common=("nrmse_common", "mean"), vs_reference=("vs_reference", "mean"))
    summary["coverage"] = summary["n_filled"] / summary["n_hidden"].where(summary["n_hidden"] > 0)
    summary = summary.groupby(["method", "setting", "siren_inputs", "omega0", "epochs", "pattern"], as_index=False,
                              dropna=False).agg(
        n_seeds=("seed", "size"), n_hidden=("n_hidden", "mean"), coverage=("coverage", "mean"),
        nrmse=("nrmse", "mean"), nrmse_sd=("nrmse", "std"), nrmse_common=("nrmse_common", "mean"),
        vs_reference=("vs_reference", "mean"))
    summary = summary.sort_values(["pattern", "nrmse_common", "nrmse"])
    summary.to_csv(os.path.join(out, "validation_summary.csv"), index=False)
    with open(os.path.join(out, "validation_settings.json"), "w") as fh:
        json.dump({"scans": [cohort.scans[s] for s in sample], "rounds": args.validate_rounds,
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
        nsse_paired=("nsse_paired", "sum"), nsse_reference=("nsse_reference", "sum"))
    g["coverage"] = g["n_filled"] / g["n_hidden"].where(g["n_hidden"] > 0)
    g["rmse"] = np.sqrt(g["sse"] / g["n_filled"].where(g["n_filled"] > 0))
    g["nrmse"] = np.sqrt(g["nsse"] / g["n_norm"].where(g["n_norm"] > 0))
    g["nrmse_common"] = np.sqrt(g["nsse_common"] / g["n_common"].where(g["n_common"] > 0))
    # the error relative to that of the reference on the same cells: below 1, better than the cohort mean
    g["vs_reference"] = np.sqrt(g["nsse_paired"] / g["nsse_reference"].where(g["nsse_reference"] > 0))
    return g.drop(columns=["sse", "nsse", "nsse_common", "nsse_paired", "nsse_reference"])


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
        sir = d[d["method"] == "siren"]
        for j, omega0 in enumerate(sorted(sir["omega0"].unique())):
            for inputs in SIREN_INPUTS:
                c = sir[(sir["siren_inputs"] == inputs) & (sir["omega0"] == omega0)].sort_values("epochs")
                if len(c):
                    ax.errorbar(c["epochs"], c["nrmse"], yerr=c["nrmse_sd"].fillna(0), color=colors[inputs],
                                ls=styles[j % len(styles)], marker="o", ms=3, capsize=2,
                                label="{} ω0={:g}".format(inputs, omega0))
        others = d[(d["method"] != "siren") & np.isfinite(d["nrmse"])]
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
    p.add_argument("--method", default="arc-linear", choices=METHODS,
                   help="Imputation method (default: arc-linear; with --fallback none, only the gaps inside profiles are "
                        "filled: from the same scan, whole profiles are imputed worse than by the cohort mean, see the "
                        "documentation)")
    p.add_argument("--fallback", default="none", choices=("none",) + METHODS,
                   help="Method for the cells the first one leaves, e.g. knn after linear for positions outside the "
                        "observed ones (default: none)")
    p.add_argument("--k", type=int, default=1, help="knn: number of neighbours (default: 1)")
    p.add_argument("--knn-weights", default="distance", choices=("distance", "uniform"),
                   help="knn: weight the neighbours by 1/distance or equally (default: distance)")
    p.add_argument("--max-distance", type=float, default=10.0,
                   help="linear, knn, siren: cells farther than this (mm) from an observed position of the same metric "
                        "stay missing; 0: no limit (default: 10)")
    p.add_argument("--arc-ends", default="none", choices=ARC_ENDS,
                   help="arc-linear: the missing start and end of a profile: left, the nearest observed value repeated, "
                        "or the line through the 3 nearest observed values extended (up to --max-gap mm) (default: none)")
    p.add_argument("--max-gap", type=float, default=15.0,
                   help="arc-linear: longest gap (mm, between its observed ends) filled, the range of the validation; "
                        "0: no limit (default: 15)")
    p.add_argument("--min-observed", type=float, default=0.5,
                   help="A metric of a scan with a smaller share of observed values is not imputed (default: 0.5)")
    p.add_argument("--siren-inputs", default="xyz+tract", choices=SIREN_INPUTS,
                   help="siren: network inputs, the 3-D position alone, with the arc length, or with the tract (one-hot) "
                        "(default: xyz+tract, best for gaps; for whole profiles xyz with --epochs 100 --omega0 10)")
    p.add_argument("--epochs", type=int, default=1000, help="siren: training epochs (default: 1000)")
    p.add_argument("--omega0", type=float, default=30.0, help="siren: omega_0 (default: 30)")
    p.add_argument("--hidden-layers", type=int, default=3, help="siren: hidden sine layers (default: 3)")
    p.add_argument("--hidden-width", type=int, default=256, help="siren: layer width (default: 256)")
    p.add_argument("--lr", type=float, default=1e-4, help="siren: Adam learning rate (default: 1e-4)")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"], help="siren: torch device (default: auto)")
    p.add_argument("--seed", type=int, default=0, help="siren: random seed (default: 0)")
    p.add_argument("--value-format", default="%.6g", help="printf format of the imputed values (default: %%.6g, as EXTRACT_Profile)")
    v = p.add_argument_group("validation (--validate)")
    v.add_argument("--validate", action="store_true",
                   help="Compare methods and settings on hidden observed values of a sample of scans instead of imputing")
    v.add_argument("--validate-scans", type=int, default=30, help="Number of scans (default: 30)")
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
    v.add_argument("--validate-methods", default="arc-linear,linear,knn,siren", help="Methods to compare (default: all)")
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


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
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
    if args.method != "arc-linear" or args.fallback not in ("none", "arc-linear"):
        if axes is None:
            log.error("--axis-dir is needed for %s", args.method if args.method != "arc-linear" else args.fallback)
            return 1
    missing = int((np.isnan(cohort.values) & cohort.valid[None]).sum())
    log.info("%d missing cells (blank, or whole profiles of scans absent from a table)", missing)
    opts = {"k": args.k, "weights": args.knn_weights, "max_distance": args.max_distance, "max_gap": args.max_gap,
            "ends": args.arc_ends,
            "seed": args.seed, "siren_inputs": args.siren_inputs,
            "siren": {"epochs": args.epochs, "omega0": args.omega0, "hidden": args.hidden_width,
                      "hidden_layers": args.hidden_layers, "lr": args.lr}}
    fallback = None if args.fallback == "none" else args.fallback
    imputed, used, dists, skipped = impute_cohort(cohort, args.method, fallback, opts, args.min_observed, args.device)
    n = write_tables(cohort, imputed, args.out_dir, os.path.join(args.report_dir, "masks"), args.value_format)
    summary = summary_rows(cohort, imputed, used, dists, skipped)
    os.makedirs(args.report_dir, exist_ok=True)
    summary.to_csv(os.path.join(args.report_dir, "imputation_summary.csv"), index=False)
    with open(os.path.join(args.report_dir, "imputation_settings.json"), "w") as fh:
        json.dump({k: v for k, v in vars(args).items() if k != "func"}, fh, indent=1, default=str)
    left = missing - n
    log.info("Imputed %d of %d missing cells (%s%s) into %s/; %d left (imputation_summary.csv: left_reason)", n,
             missing, args.method, "" if fallback is None else ", then " + fallback, args.out_dir, left)
    log.info("Masks of the imputed cells and imputation_summary.csv in %s/", args.report_dir)
    return 0
