"""Cell-level analyses of the validation dumps (--validate-dump-dir).

A dump file holds, for every hidden cell of one validation pass (scan, round, pattern), the true value, the age-bin
mean and SD of the scan (left out of its subject), the distance to the nearest observed value of the same measure,
the prediction and SD of the default base (population model + a local method within 4 mm: "base") and of the
transformer ("model_pred"). Runs with several local methods (--validate-population-local knn,siren) write one entry
per local method; both are kept (base = SIREN, base_knn = kNN).

Datasets (each a list of seeds):
  bcp  v15/dump_R3_s{0,1,2} (BCP transformer, 400 epochs), with the transformer of v15/dump_P_s* (trained on BCP +
       HBCD) as the "reference" model on the same cells (phase-6 runs; the cells are identical across runs);
  e1   v16/dump_E1_s{3,4,5}: untouched subjects (E1);
  e3   v16/dump_E3_s{0,1,2}: HBCD alone (E3).
Each dataset is analysed when its dumps exist.

Settings scored per dataset: age-bin mean, kernel age norm (E6; cache/kernel_norm_<run>.npz from e6_kernel_norm.py),
base (PPCA + SIREN), base_knn (PPCA + kNN, when dumped), transformer, fixed 0.25/0.75 blend, the SHIPPED weight table
(ENSEMBLE_TABLES of impute_profiles.py, applied as impute-profiles does), and a weight table refitted on the dataset
and cross-fitted by subject (5 folds). Writes cache/dump_<dataset>_*.csv:
  results      per setting and seed: overall (4 patterns), each pattern, families, relative to the age-bin mean and
               (suffix _k) to the kernel norm
  scans        per-scan scores per setting, seed and pattern group (4pat, each pattern)
  cells        per setting, seed, pattern, metric, age bin, distance bin: sums of squared errors (setting, age-bin
               mean, kernel norm) and counts
  tracts       per setting, seed, pattern, tract, metric: the same sums
  calib        SD calibration (E7) per setting, seed, pattern, metric, weight-table band: n, sum z^2, n |z| <= 1.96
  load         region pattern: sums by the number of tracts hidden together (O7)
  ages         per setting, seed, pattern, metric, age (months): sums
  weights      the refitted weight tables (all cells)
CPU, about 10-15 minutes per dataset.

usage: dump_analysis.py [bcp] [e1] [e3]
"""
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

import common as C

sys.path.insert(0, C.REPO)
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip  # noqa: E402

NEAR, FAR = [0, 0.5, 1, 2, 3], [4, 6, 10, 20]
BAND = ["0-0.5", "0.5-1", "1-2", "2-3", "3-4", "4-6", "6-10", "10-20", ">20", "none"]
DIST_EDGES = [0, 2, 4, 6, 10, 15, 20, 25, np.inf]  # as validation_by_distance.csv
DIST_LABEL = ["0-2", "2-4", "4-6", "6-10", "10-15", "15-20", "20-25", ">25"]
FOUR = ["gap", "end gap", "whole profile", "region"]
MODEL_TAG = "patch8 d192 L6"

V15, V16 = C.ROOT + "/v15", C.ROOT + "/v16"
DATASETS = {
    "bcp": dict(seeds=[(0, V15 + "/dump_R3", V15 + "/dump_P", "v15_R3_s0"),
                       (1, V15 + "/dump_R3_s1", V15 + "/dump_P_s1", "v15_R3_s1"),
                       (2, V15 + "/dump_R3_s2", V15 + "/dump_P_s2", "v15_R3_s2")], cohort="bcp"),
    "e1": dict(seeds=[(s, V16 + "/dump_E1_s{}".format(s), None, "v16_E1_s{}".format(s)) for s in (3, 4, 5)],
               cohort="bcp"),
    "e3": dict(seeds=[(s, V16 + "/dump_E3_s{}".format(s), None, "v16_E3_s{}".format(s)) for s in (0, 1, 2)],
               cohort="hbcd"),
}
_cohorts = {}


def cohort(kind):
    if kind not in _cohorts:
        d, age_csv = (C.BCP_DIR, None) if kind == "bcp" else (C.HBCD_DIR, C.HBCD_AGES)
        tables = ip.read_tables(d)
        c = ip.Cohort(tables, None)
        ages = ip.scan_ages(c, age_csv, "months", None, None)
        _cohorts[kind] = (c, dict(zip(c.scans, ages)))
    return _cohorts[kind]


def load(d):
    """All dumped cells of the transformer blends in folder *d*: one row per cell and local method."""
    rows = []
    for f in sorted(glob.glob(d + "/*.npz")):
        z = np.load(f)
        if MODEL_TAG not in str(z["model"]) or "+" in str(z["model"]).split(MODEL_TAG)[1].split(" on ")[0]:
            continue  # only the plain transformer (no extra inputs or members)
        rows.append(pd.DataFrame({k: z[k] for k in ("position", "metric", "pattern", "truth", "mean", "sd", "dist",
                                                     "base", "near", "base_sd", "model_pred", "model_sd")}).assign(
            scan=str(z["scan"]), age_bin=str(z["age_bin"]), local=str(z["local"]), call=os.path.basename(f)))
    if not rows:
        return None
    X = pd.concat(rows, ignore_index=True)
    X["age_bin"] = X.age_bin.str.replace("^BCP ", "", regex=True)
    return X


def split_local(X):
    """One row per cell: base = SIREN residuals (or the only local method), base_knn when kNN was dumped too."""
    X["k"] = X.groupby(["scan", "local"]).call.transform(lambda c: pd.factorize(c)[0])
    locs = X.local.unique()
    sir = [l for l in locs if "siren" in l]
    knn = [l for l in locs if "knn" in l]
    key = ["scan", "k", "position", "metric"]
    A = X[X.local == (sir[0] if sir else locs[0])].drop(columns=["local"])
    if knn and sir:
        B = X[X.local == knn[0]][key + ["base", "near", "base_sd"]].rename(
            columns={"base": "base_knn", "near": "near_knn", "base_sd": "base_knn_sd"})
        A = A.merge(B, on=key, how="left")
    return A.reset_index(drop=True)


def band(df, near_col="near"):
    d = df.dist.to_numpy()
    none = ~np.isfinite(d) | (df.pattern == "whole measure").to_numpy()
    nb = np.clip(np.searchsorted(NEAR, d, side="right") - 1, 0, 4)
    fb = np.clip(np.searchsorted(FAR, d, side="right") - 1, 0, 3)
    return np.where(none, 9, np.where(df[near_col].to_numpy(), nb, 5 + fb))


def zcols(df, base_col="base"):
    s = df.sd.to_numpy()
    m = df["mean"].to_numpy()
    return ((df[base_col].to_numpy() - m) / s, (df.model_pred.to_numpy() - m) / s, (df.truth.to_numpy() - m) / s)


def cell_weight(df):
    r2 = ((df["mean"] - df.truth) / df.sd) ** 2
    g = r2.groupby([df.pattern, df.metric, df.age_bin]).transform("mean")
    return (1.0 / g.clip(lower=1e-6)).to_numpy()


def fit_table(tr, base_col="base", near_col="near"):
    b, g, t = zcols(tr, base_col)
    ok = np.isfinite(b) & np.isfinite(g)
    cw = cell_weight(tr)[ok]
    key = (tr.metric.to_numpy() * 10 + band(tr, near_col))[ok]
    num = pd.Series(cw * ((t - b) * (g - b))[ok]).groupby(key).sum()
    den = pd.Series(cw * ((g - b) ** 2)[ok]).groupby(key).sum()
    return (num / den.clip(lower=1e-9)).clip(0, 1)


def table_weights(df, table, near_col="near"):
    key = df.metric.to_numpy() * 10 + band(df, near_col)
    return np.array([table.get(k, 0.5) for k in key])


def shipped(kind):
    t = ip.ENSEMBLE_TABLES[kind]
    out = {}
    for mi, m in enumerate(C.METRICS):
        for g in range(10):
            out[mi * 10 + g] = t[m][g]
    return out


def crossfit_w(df, base_col="base", near_col="near", folds=5):
    subs = df.scan.map(C.subject_of)
    u = np.random.default_rng(0).permutation(subs.unique())
    fold = subs.map({s: i % folds for i, s in enumerate(u)}).to_numpy()
    w = np.full(len(df), np.nan)
    for k in range(folds):
        te = fold == k
        if te.any() and (~te).any():
            tab = fit_table(df[~te], base_col, near_col)
            w[te] = table_weights(df[te], tab.to_dict(), near_col)
    return w


def mix(b, g, w):
    ok = np.isfinite(b) & np.isfinite(g)
    return np.where(ok, (1 - w) * b + w * g, np.where(np.isfinite(b), b, g))


def mix_sd(bs, gs, w):
    ok = np.isfinite(bs) & np.isfinite(gs)
    return np.where(ok, np.sqrt((1 - w) * bs ** 2 + w * gs ** 2), np.where(np.isfinite(bs), bs, gs))


def predictions(X, kind_table, has_ref):
    """{setting: (prediction, sd or None)} of one dataset (all seeds)."""
    P = {"age-bin mean": (X["mean"].to_numpy(), X.sd.to_numpy())}
    if "kernel" in X:
        P["kernel norm"] = (X.kernel.to_numpy(), None)
    b, g = X.base.to_numpy(), X.model_pred.to_numpy()
    bs, gs = X.base_sd.to_numpy(), X.model_sd.to_numpy()
    P["PPCA + SIREN"] = (b, bs)
    P["transformer"] = (g, gs)
    wf = np.where(X.near, 0.25, 0.75)
    P["fixed 0.25/0.75"] = (mix(b, g, wf), mix_sd(bs, gs, wf))
    ws = table_weights(X, shipped(kind_table))
    P["table (shipped)"] = (mix(b, g, ws), mix_sd(bs, gs, ws))
    wc = crossfit_w(X)
    P["table (cross-fitted)"] = (mix(b, g, wc), mix_sd(bs, gs, wc))
    if "base_knn" in X:
        bk, bks = X.base_knn.to_numpy(), X.base_knn_sd.to_numpy()
        P["PPCA + kNN"] = (bk, bks)
        wk = table_weights(X, shipped(kind_table), "near_knn")
        P["kNN base, table (shipped)"] = (mix(bk, g, wk), mix_sd(bks, gs, wk))
        wkc = crossfit_w(X, "base_knn", "near_knn")
        P["kNN base, table (cross-fitted)"] = (mix(bk, g, wkc), mix_sd(bks, gs, wkc))
    if has_ref:
        gr, grs = X.model_pred_ref.to_numpy(), X.model_sd_ref.to_numpy()
        P["reference transformer"] = (gr, grs)
        P["reference fixed 0.25/0.75"] = (mix(b, gr, wf), mix_sd(bs, grs, wf))
        wr = table_weights(X, shipped("reference"))
        P["reference table (shipped)"] = (mix(b, gr, wr), mix_sd(bs, grs, wr))
        Xr = X.assign(model_pred=gr)
        wrc = crossfit_w(Xr)
        P["reference table (cross-fitted)"] = (mix(b, gr, wrc), mix_sd(bs, grs, wrc))
        P["mean of both transformers, fixed"] = (mix(b, (g + gr) / 2, wf), None)
    return P


def scores(X, pred, ref_col="mean"):
    """Score as the validation: per (pattern, metric, age bin) RMSE ratio; overall = mean over the 4 patterns."""
    p = np.where(np.isfinite(pred), pred, X["mean"])
    g = pd.DataFrame({"pattern": X.pattern, "metric": X.metric, "age_bin": X.age_bin,
                      "e2": (p - X.truth) ** 2, "r2": (X[ref_col] - X.truth) ** 2})
    a = g.groupby(["pattern", "metric", "age_bin"])[["e2", "r2"]].mean()
    rr = np.sqrt(a.e2 / a.r2).rename("r").reset_index()
    out = {"overall": rr[rr.pattern.isin(FOUR)].r.mean()}
    for pt in rr.pattern.unique():
        out[pt] = rr[rr.pattern == pt].r.mean()
    for f, ms in (("whole dti", [0, 1, 2, 3]), ("whole noddi", [4, 5, 6])):
        x = rr[(rr.pattern == "whole measure") & rr.metric.isin(ms)].r
        out[f] = x.mean() if len(x) else np.nan
    return out


def scan_scores(X, pred):
    p = np.where(np.isfinite(pred), pred, X["mean"])
    g = pd.DataFrame({"scan": X.scan, "pattern": X.pattern, "metric": X.metric,
                      "e2": (p - X.truth) ** 2, "r2": (X["mean"] - X.truth) ** 2})
    s = g.groupby(["scan", "pattern", "metric"])[["e2", "r2"]].sum()
    s = s[s.r2 > 0]
    r = np.sqrt(s.e2 / s.r2).rename("r").reset_index()
    out = [r[r.pattern.isin(FOUR)].groupby("scan").r.mean().rename("r").reset_index().assign(group="4pat")]
    for pt in r.pattern.unique():
        out.append(r[r.pattern == pt].groupby("scan").r.mean().rename("r").reset_index().assign(group=pt))
    return pd.concat(out, ignore_index=True)


def main(names):
    for name in names:
        spec = DATASETS[name]
        c, ages = cohort(spec["cohort"])
        tract_of = np.asarray(c.tracts)[c.tract_of]
        parts = []
        for seed, d, dref, kn in spec["seeds"]:
            A = load(d)
            if A is None:
                print(name, "seed", seed, ": no dumps in", d)
                continue
            A = split_local(A)
            if dref and os.path.isdir(dref):
                B = load(dref)
                B = split_local(B)
                key = ["scan", "k", "position", "metric"]
                A = A.merge(B[key + ["truth", "model_pred", "model_sd"]].rename(
                    columns={"truth": "truth_ref", "model_pred": "model_pred_ref", "model_sd": "model_sd_ref"}),
                    on=key)
                assert np.allclose(A.truth, A.truth_ref), "hidden cells differ between runs"
            kf = "{}/kernel_norm_{}.npz".format(C.CACHE, kn)
            if os.path.isfile(kf):
                K = np.load(kf)
                kern = np.full(len(A), np.nan)
                for sc, idx in A.groupby("scan").indices.items():
                    if sc in K.files:
                        kern[idx] = K[sc][A.position.to_numpy()[idx], A.metric.to_numpy()[idx]]
                A["kernel"] = kern
            A["seed"] = seed
            A["scan"] = A.scan + "#{}".format(seed)
            parts.append(A)
        if not parts:
            continue
        X = pd.concat(parts, ignore_index=True)
        print(name, len(X), "cells", flush=True)
        X["tract"] = tract_of[X.position.to_numpy()]
        X["age"] = [ages.get(s.split("#")[0]) for s in X.scan]
        has_ref = "model_pred_ref" in X
        kind_table = "cohort"
        P = predictions(X, kind_table, has_ref)
        # weight tables refitted on all cells
        W = []
        for lab, x in [("cohort", X)] + ([("reference", X.assign(model_pred=X.model_pred_ref))] if has_ref else []):
            w = fit_table(x)
            W += [dict(table=lab, metric=C.METRICS[m], band=BAND[g], weight=float(w.get(m * 10 + g, np.nan)))
                   for m in range(7) for g in range(10)]
        pd.DataFrame(W).to_csv("{}/dump_{}_weights.csv".format(C.CACHE, name), index=False)
        res, sc, cells, tr, cal, ld, ag = [], [], [], [], [], [], []
        d = X.dist.to_numpy()
        dbin = np.where(np.isfinite(d), np.clip(np.searchsorted(DIST_EDGES, d, side="right") - 1, 0, 7), -1)
        bnd = band(X)
        r2 = (X["mean"] - X.truth).to_numpy() ** 2
        k2 = (X.kernel - X.truth).to_numpy() ** 2 if "kernel" in X else np.full(len(X), np.nan)
        # O7: number of tracts hidden together in the region pass of the cell
        reg = X.pattern == "region"
        ntr = X[reg].groupby(["scan", "k"]).tract.transform("nunique")
        load_n = pd.Series(np.nan, index=X.index)
        load_n[reg] = ntr
        for label, (p, sdv) in P.items():
            pf = np.where(np.isfinite(p), p, X["mean"])
            e2 = (pf - X.truth.to_numpy()) ** 2
            for seed in sorted(X.seed.unique()):
                sel = (X.seed == seed).to_numpy()
                xs = X[sel]
                r = scores(xs, pf[sel])
                if "kernel" in X and np.isfinite(xs.kernel).all():
                    rk = scores(xs, pf[sel], "kernel")
                    r.update({k + "_k": v for k, v in rk.items()})
                res.append(dict(setting=label, seed=seed, **r))
                s = scan_scores(xs, pf[sel])
                s["scan"] = s.scan.str.replace(r"#\d+$", "", regex=True)
                sc.append(s.assign(setting=label, seed=seed))
            base = pd.DataFrame({"seed": X.seed, "pattern": X.pattern, "metric": X.metric, "age_bin": X.age_bin,
                                 "e2": e2, "r2": r2, "k2": k2})
            a = base.assign(dbin=dbin).groupby(["seed", "pattern", "metric", "age_bin", "dbin"]).agg(
                e2=("e2", "sum"), r2=("r2", "sum"), k2=("k2", "sum"), n=("e2", "size")).reset_index()
            cells.append(a.assign(setting=label))
            a = base.assign(tract=X.tract).groupby(["seed", "pattern", "tract", "metric"]).agg(
                e2=("e2", "sum"), r2=("r2", "sum"), n=("e2", "size")).reset_index()
            tr.append(a.assign(setting=label))
            a = base[reg.to_numpy()].assign(load=load_n[reg].to_numpy()).groupby(
                ["seed", "metric", "age_bin", "load"]).agg(e2=("e2", "sum"), r2=("r2", "sum"),
                                                          n=("e2", "size")).reset_index()
            ld.append(a.assign(setting=label))
            a = base.assign(age=X.age).groupby(["seed", "pattern", "metric", "age_bin", "age"]).agg(
                e2=("e2", "sum"), r2=("r2", "sum"), n=("e2", "size")).reset_index()
            ag.append(a.assign(setting=label))
            if sdv is not None:
                z = (p - X.truth.to_numpy()) / sdv
                ok = np.isfinite(z)
                cb = pd.DataFrame({"seed": X.seed, "pattern": X.pattern, "metric": X.metric, "band": bnd,
                                   "z2": np.where(ok, z, 0) ** 2, "in": (np.abs(z) <= 1.96) & ok, "ok": ok})
                a = cb.groupby(["seed", "pattern", "metric", "band"]).agg(n=("ok", "sum"), z2=("z2", "sum"),
                                                                           within=("in", "sum")).reset_index()
                cal.append(a.assign(setting=label))
            print("  ", label, {k: round(v, 4) for k, v in scores(X, pf).items() if isinstance(v, float)},
                  flush=True)
        pre = "{}/dump_{}_".format(C.CACHE, name)
        pd.DataFrame(res).to_csv(pre + "results.csv", index=False)
        pd.concat(sc, ignore_index=True).to_csv(pre + "scans.csv", index=False)
        pd.concat(cells, ignore_index=True).to_csv(pre + "cells.csv", index=False)
        pd.concat(tr, ignore_index=True).to_csv(pre + "tracts.csv", index=False)
        pd.concat(cal, ignore_index=True).to_csv(pre + "calib.csv", index=False)
        pd.concat(ld, ignore_index=True).to_csv(pre + "load.csv", index=False)
        pd.concat(ag, ignore_index=True).to_csv(pre + "ages.csv", index=False)
        del X, P


if __name__ == "__main__":
    main(sys.argv[1:] or ["bcp", "e1", "e3"])
