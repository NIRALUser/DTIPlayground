"""Shared paths, setting names and scoring for the paper's tables and figures.

Every number in the paper is computed here from the validation result files of dmrifiberprofile impute-profiles
(testProfiles/ImputeValidation/v10 ... v15). The scoring follows the analysis scripts kept with those runs
(v13/analyse_c.py, v15/analyse.py, v15/blend.py):

* score of a setting: for every (pattern, metric, age bin) the RMSE of the setting on all hidden values (cells it
  leaves count with the age-bin mean, ``rmse_completed``) divided by the RMSE of the age-bin mean on the same values;
  the mean over metrics and age bins (and over the four patterns for "overall");
* per-scan score: for every (scan, pattern, metric) sqrt(MSE setting / MSE age-bin mean), averaged over the patterns
  and metrics of the scan; two settings are compared by the log ratio of their per-scan scores over the scan x seed
  pairs (geometric mean ratio, 95% CI, Wilcoxon signed-rank test).
"""
import os
import re

import numpy as np
import pandas as pd
from scipy import stats

ROOT = "/NIRAL/devel/linux/DTI/testProfiles/ImputeValidation"
REPO = "/NIRAL/devel/linux/DTI/DTIPlayground"
PAPER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = os.path.join(PAPER, "tables")
FIGURES = os.path.join(PAPER, "figures")
CACHE = os.path.join(PAPER, "scripts", "cache")
BCP_DIR = os.path.join(ROOT, "v12/data/BCP/Profiles_Clean")
HBCD_DIR = os.path.join(ROOT, "v15/data/HBCD/Profiles_Clean")
HBCD_AGES = os.path.join(ROOT, "v15/hbcd_ages.csv")
AXIS_DIR = "/NIRAL/tools/atlas/DTI/DTI_IBISEP_Feb26/FiberAxis"
for d in (TABLES, FIGURES, CACHE):
    os.makedirs(d, exist_ok=True)

SEEDS = (0, 1, 2)
PATS = ["gap", "end gap", "whole profile", "region"]
PAT_LABEL = {"gap": "Interior gap", "end gap": "End gap", "whole profile": "Whole profile", "region": "Region",
             "whole dti": "Tensor family", "whole noddi": "NODDI family"}
BINS = ["0-3m", "4-9m", "10-60m"]
BIN_LABEL = {"0-3m": "0--3 mo", "4-9m": "4--9 mo", "10-60m": "10--60 mo"}
METRICS = ["fa", "md", "rd", "ad", "NDI", "ODI", "FWF"]
MLABEL = {"fa": "FA", "md": "MD", "rd": "RD", "ad": "AD", "NDI": "NDI", "ODI": "ODI", "FWF": "FWF"}
FAM = {"dti": ["fa", "md", "rd", "ad"], "noddi": ["NDI", "ODI", "FWF"]}

# Okabe-Ito colourblind-safe palette
OI = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73", "pink": "#CC79A7", "sky": "#56B4E9",
      "red": "#D55E00", "yellow": "#F0E442", "black": "#000000", "grey": "#7F7F7F"}
PAT_COLOR = {"gap": OI["blue"], "end gap": OI["sky"], "whole profile": OI["orange"], "region": OI["red"],
             "whole dti": OI["green"], "whole noddi": OI["pink"]}
PAT_MARKER = {"gap": "o", "end gap": "s", "whole profile": "D", "region": "^", "whole dti": "v", "whole noddi": "P"}

DEF = "population q=80 isotropic + siren xyz omega0=10"
POP = "population q=80 isotropic"
GU = "graph-unet on population q=80 L4 h128 x1"
TF = "transformer on population q=80 patch8 d192 L6"


def blend_name(near, beyond, model=TF):
    return "graph near {:g} beyond {:g}: {}, {}".format(near, beyond, DEF, model)


# Named settings: label -> (run folder relative to ROOT without the seed suffix, setting string, reference run)
# The reference run is the run whose prior-mean rows are the denominator (the age-bin mean on the same hidden values).
# All runs of the phase-4 protocol (v12, v13, v15) hide the same values for the same --validate-seed.
S = {
    # phase 1 (scan's own values), phase 2 (deviations from the age-bin norm): v13/P12
    "age-bin mean": ("v13/P12", "prior-mean", None),
    "P1 arc-linear": ("v13/P12", "arc-linear", None),
    "P1 arc-linear, constant ends": ("v13/P12", "arc-linear ends=constant", None),
    "P1 linear (3-D)": ("v13/P12", "linear", None),
    "P1 kNN k=20": ("v13/P12", "knn k=20 distance", None),
    "P1 SIREN xyz": ("v13/P12", "siren xyz omega0=10", None),
    "P1 SIREN xyz+tract": ("v13/P12", "siren xyz+tract omega0=30", None),
    "P2 arc-linear, constant ends": ("v13/P12", "arc-linear ends=constant (z)", None),
    "P2 linear (3-D)": ("v13/P12", "linear (z)", None),
    "P2 kNN k=1": ("v13/P12", "knn k=1 distance (z)", None),
    "P2 kNN k=20": ("v13/P12", "knn k=20 distance (z)", None),
    "P2 kNN k=50": ("v13/P12", "knn k=50 distance (z)", None),
    "P2 SIREN xyz+arc": ("v13/P12", "siren xyz+arc omega0=10 (z)", None),
    "P2 SIREN xyz+tract": ("v13/P12", "siren xyz+tract omega0=30 (z)", None),
    "P2 SIREN xyz": ("v13/P12", "siren xyz omega0=10 (z)", None),
    # phase 3: population model (PPCA) and residual imputation: v13/P3
    "P3 PPCA q=10": ("v13/P3", "population q=10 isotropic", None),
    "P3 PPCA q=20": ("v13/P3", "population q=20 isotropic", None),
    "P3 PPCA q=40": ("v13/P3", "population q=40 isotropic", None),
    "P3 PPCA q=80": ("v13/P3", "population q=80 isotropic", None),
    "P3 PPCA q=120": ("v13/P3", "population q=120 isotropic", None),
    "P3 PPCA q=80 + kNN": ("v13/P3", "population q=80 isotropic + knn k=20", None),
    "P3 PPCA q=10 + SIREN": ("v13/P3", "population q=10 isotropic + siren xyz omega0=10", None),
    "P3 PPCA q=20 + SIREN": ("v13/P3", "population q=20 isotropic + siren xyz omega0=10", None),
    "P3 PPCA q=40 + SIREN": ("v13/P3", "population q=40 isotropic + siren xyz omega0=10", None),
    "P3 PPCA q=120 + SIREN": ("v13/P3", "population q=120 isotropic + siren xyz omega0=10", None),
    "P3 PPCA + SIREN": ("v13/P3", DEF, None),
    # phase 4: graph U-Net (v12/S, 7 measures)
    "P4 U-Net (deviations+PPCA)": ("v12/S", GU, None),
    "P4 U-Net + SIREN": ("v12/S", GU + " + siren xyz omega0=10", None),
    "P4 PPCA + SIREN, U-Net beyond": ("v12/S", DEF + ", " + GU + " beyond", None),
    "P4 default (check)": ("v12/S", DEF, None),
    # phase 6: ensembles with the graph U-Net (v15/E), acquisition correction (v15/Q), transformer (v15/T, R3)
    "P6 U-Net blend 0.25/0.75": ("v15/E", blend_name(0.25, 0.75, GU), None),
    "P6 U-Net precision blend": ("v15/E", "precision: {}, {}".format(DEF, GU), None),
    "P6 acq. correction: default": ("v15/Q", DEF, "v15/E"),
    "P6 transformer (200 ep.)": ("v15/T", TF, None),
    "P6 transformer + SIREN": ("v15/T", TF + " + siren xyz omega0=10", None),
    "P6 PPCA + SIREN, transformer beyond": ("v15/T", DEF + ", " + TF + " beyond", None),
    "P6 transformer blend 0.25/0.75": ("v15/T", blend_name(0.25, 0.75), None),
    "P6 transformer blend 0/0.5": ("v15/T", blend_name(0, 0.5), None),
    "P6 transformer blend 0/0.75": ("v15/T", blend_name(0, 0.75), None),
    "P6 transformer blend 0.25/0.5": ("v15/T", blend_name(0.25, 0.5), None),
    "P6 transformer blend 0.5/0.5": ("v15/T", blend_name(0.5, 0.5), None),
    "P6 transformer precision blend": ("v15/T", "precision: {}, {}".format(DEF, TF), None),
    "P6 transformer (400 ep.)": ("v15/R3", TF, None),
    "P6 transformer 400 blend 0.25/0.75": ("v15/R3", blend_name(0.25, 0.75), None),
    "P6 default (E check)": ("v15/E", DEF, None),
    # pooled BCP+HBCD (population model, norm and transformer pooled; BCP scans scored in BCP units against the
    # BCP-alone age-bin mean of v15/E)
    "P6 pooled: PPCA + SIREN": ("v15/P", DEF, "v15/E"),
    "P6 pooled: transformer": ("v15/P", TF, "v15/E"),
    "P6 pooled: blend 0.25/0.75": ("v15/P", blend_name(0.25, 0.75), "v15/E"),
}


def run_path(run, seed):
    return os.path.join(ROOT, "{}_s{}_report".format(run, seed) if not run.startswith("v12/S")
                        else "v12/S{}_report".format(seed), "validation")


_cache = {}


def read(run, seed, name):
    key = (run, seed, name)
    if key not in _cache:
        d = pd.read_csv(os.path.join(run_path(run, seed), name))
        for c in ("age_bin", "group"):  # pooled runs label the BCP groups "BCP 0-3m"
            if c in d and d[c].astype(str).str.startswith("BCP ").any():
                d = d[d[c].astype(str).str.startswith("BCP ")].copy()
                d[c] = d[c].str[4:]
        _cache[key] = d
    return _cache[key]


def cell_ratios(label, seed):
    """(pattern, metric, age bin) -> RMSE ratio to the age-bin mean, of a named setting and seed."""
    run, st, refrun = S[label]
    d = read(run, seed, "validation_by_age_bin.csv")
    r = read(refrun or run, seed, "validation_by_age_bin.csv")
    ref = r[r.setting == "prior-mean"].set_index(["pattern", "metric", "age_bin"]).rmse
    x = d[d.setting == st]
    if x.empty:
        raise KeyError("{}: no setting {!r} in {} seed {}".format(label, st, run, seed))
    q = (x.set_index(["pattern", "metric", "age_bin"]).rmse_completed / ref).rename("r").dropna().reset_index()
    return q


def summary(label, seeds=SEEDS):
    """Per seed: overall (4 patterns), per pattern, per age bin, whole tensor / NODDI family."""
    rows = []
    for seed in seeds:
        q = cell_ratios(label, seed)
        q4 = q[q.pattern.isin(PATS)]
        r = {"setting": label, "seed": seed, "overall": q4.r.mean()}
        r.update(q4.groupby("pattern").r.mean().to_dict())
        r.update(q4.groupby("age_bin").r.mean().to_dict())
        wm = q[q.pattern == "whole measure"]
        for f, ms in FAM.items():
            v = wm[wm.metric.isin(ms)].r
            r["whole " + f] = v.mean() if len(v) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def per_metric(label, seeds=SEEDS, patterns=PATS):
    """Mean over seeds of the ratio per metric (mean over the given patterns and the age bins)."""
    qs = []
    for seed in seeds:
        q = cell_ratios(label, seed)
        qs.append(q[q.pattern.isin(patterns)].assign(seed=seed))
    q = pd.concat(qs)
    return q.groupby(["seed", "metric"]).r.mean().groupby("metric").mean()


def scan_scores(label, seeds=SEEDS, patterns=PATS):
    """Per (scan, seed) score: mean over patterns and metrics of sqrt(MSE / MSE of the age-bin mean)."""
    run, st, refrun = S[label]
    out = []
    for seed in seeds:
        s = read(run, seed, "validation_by_scan.csv")
        rs = read(refrun or run, seed, "validation_by_scan.csv")
        base = rs[(rs.setting == "prior-mean") & rs.pattern.isin(patterns)].set_index(["scan", "pattern", "metric"])
        y = s[(s.setting == st) & s.pattern.isin(patterns)].set_index(["scan", "pattern", "metric"])
        j = y.join(base[["sse", "n"]], rsuffix="_ref", how="inner")
        j = j[(j.sse_ref > 0) & (j.n > 0)]
        r = np.sqrt((j.sse / j.n) / (j.sse_ref / j.n_ref))
        sc = r.groupby(level="scan").mean().rename("r").reset_index()
        grp = y.reset_index().groupby("scan").group.first()
        sc["group"] = sc.scan.map(grp)
        sc["seed"] = seed
        out.append(sc)
    return pd.concat(out, ignore_index=True)


def subject_of(scan):
    m = re.search(r"(sub-[^_]+)", scan)
    return m.group(1) if m else scan.split("_")[0]


def paired(a, b, n_boot=4000, seed=0):
    """Compare per-scan scores b against a (data frames with scan, seed, r). Returns a dict with the geometric mean
    ratio b/a, its normal-theory 95% CI over the scan x seed pairs (as in the documentation), the Wilcoxon p over the
    pairs, the share of pairs where b is better, and two dependence-aware checks: a cluster bootstrap CI that resamples
    subjects (repeated seeds and sessions of a subject stay together) and a Wilcoxon test on the per-subject mean log
    ratio."""
    j = a.merge(b, on=["scan", "seed"], suffixes=("_a", "_b"))
    dl = np.log(j.r_b.to_numpy()) - np.log(j.r_a.to_numpy())
    n = len(dl)
    se = dl.std(ddof=1) / np.sqrt(n)
    res = {"n": n, "ratio": np.exp(dl.mean()), "lo": np.exp(dl.mean() - 1.96 * se),
           "hi": np.exp(dl.mean() + 1.96 * se), "better": float(np.mean(dl < 0))}
    res["p"] = stats.wilcoxon(dl).pvalue if np.any(dl != 0) else 1.0
    subj = j.scan.map(subject_of).to_numpy()
    u, inv = np.unique(subj, return_inverse=True)
    sums = np.bincount(inv, weights=dl)
    cnt = np.bincount(inv)
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        k = np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))
        boots[i] = (k * sums).sum() / (k * cnt).sum()
    res["blo"], res["bhi"] = np.exp(np.percentile(boots, [2.5, 97.5]))
    sm = sums / cnt
    res["n_subj"] = len(u)
    res["p_subj"] = stats.wilcoxon(sm).pvalue if np.any(sm != 0) else 1.0
    return res


def holm(pvals):
    """Holm step-down adjusted p values."""
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    m = len(p)
    run = 0.0
    for k, i in enumerate(order):
        run = max(run, (m - k) * p[i])
        adj[i] = min(1.0, run)
    return adj


def fmt_p(p):
    if not np.isfinite(p):
        return "--"
    if p < 1e-4:
        e = int(np.floor(np.log10(p)))
        return "$<10^{{{}}}$".format(e + 1)
    if p < 0.001:
        return "{:.1e}".format(p).replace("e-0", "e-").replace("e-", r"$\times10^{-") + "}$"
    return "{:.3f}".format(p) if p < 0.1 else "{:.2f}".format(p)


def write_tex(name, text):
    with open(os.path.join(TABLES, name), "w") as fh:
        fh.write(text)


def macro(name, value):
    """A LaTeX macro definition line for numbers quoted in the text."""
    return "\\newcommand{{\\{}}}{{{}}}\n".format(name, value)
