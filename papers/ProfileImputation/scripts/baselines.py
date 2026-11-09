"""E8: cohort-level generic imputers on the same hidden values as the validation (CPU).

The hidden cells of every validation pass are read from the dumps (v15/dump_R3*: seeds 0-2; or v16/dump_E1_s*),
the scan is masked accordingly, and imputed by:
  offset (measure)     the norm plus the scan's mean observed deviation of the measure
  offset (5 tracts)    the same over the 5 tracts whose axis centroids are nearest to the missing location's tract
  kNN across scans     the inverse-distance-weighted mean deviation of the k most similar training scans
                       (nan-Euclidean distance over the co-observed cells; k = 5, 10, 20, 50), as KNNImputer
  iterative SVD        a rank-r low-rank model (hard-impute: SVD, refill the missing cells, repeat; r = 10, 40, 80,
                       160) of the training deviations; a scan's missing cells from a ridge projection of its observed
                       ones on the loadings
  MICE (tract means)   IterativeImputer (Bayesian ridge, 40 nearest features) on the tract-mean deviations
                       (69 tracts x 7 measures); a hidden tract gets its imputed mean deviation at every location,
                       a partly hidden one its observed mean deviation
Deviations are from the age-bin norm of the training scans of the fold. The folds are those of the validation
(impute_profiles.fold_variants: the validated subjects in 5 folds; training = all usable scans of other subjects),
so the baselines see the same training scans as the population model. Scored as the validation (RMSE ratio to the
age-bin mean of the dump, per pattern, metric and age bin). Writes cache/baselines_<dataset>_{results,scans}.csv.

usage: baselines.py [bcp|e1]
"""
import glob
import json
import os
import sys
import time

import numpy as np
import pandas as pd

import common as C

sys.path.insert(0, C.REPO)
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip  # noqa: E402

FOUR = ["gap", "end gap", "whole profile", "region"]
KS = (5, 10, 20, 50)
RANKS = (10, 40, 80, 160)
SETS = {"bcp": [(0, "v15/dump_R3", "v15/R3_s0"), (1, "v15/dump_R3_s1", "v15/R3_s1"),
                (2, "v15/dump_R3_s2", "v15/R3_s2")],
        "e1": [(s, "v16/dump_E1_s{}".format(s), "v16/E1_s{}".format(s)) for s in (3, 4, 5)]}


def load_passes(d):
    """{(scan, file): (positions, metrics, truth, mean, pattern)} of the SIREN-local transformer entries."""
    out = {}
    for f in sorted(glob.glob(C.ROOT + "/" + d + "/*.npz")):
        z = np.load(f)
        if "patch8 d192 L6" not in str(z["model"]) or ("siren" not in str(z["local"])):
            continue
        tail = str(z["model"]).split("patch8 d192 L6")[1].split(" on ")[0]
        if "+" in tail or "x" in tail:
            continue
        out[(str(z["scan"]), os.path.basename(f))] = (z["position"], z["metric"], z["truth"], z["mean"],
                                                      z["pattern"].astype(str), str(z["age_bin"]))
    return out


def hard_impute(Z, rank, iters=30):
    from sklearn.utils.extmath import randomized_svd
    O = ~np.isnan(Z)
    mu = np.nanmean(np.where(O, Z, np.nan), axis=0)
    mu = np.where(np.isfinite(mu), mu, 0.0)
    X = np.where(O, Z, mu)
    for _ in range(iters):
        Xc = X - mu
        U, S, Vt = randomized_svd(Xc, rank, random_state=0)
        R = (U * S) @ Vt + mu
        X = np.where(O, Z, R)
        mu = X.mean(axis=0)
    Xc = X - mu
    U, S, Vt = randomized_svd(Xc, rank, random_state=0)
    L = (Vt.T * S) / np.sqrt(len(Z))  # loadings: z = mu + L x, x ~ N(0, I)
    resid = (Xc - (U * S) @ Vt)[O]
    s2 = float(np.mean(resid ** 2)) if resid.size else 1.0
    return mu, L, max(s2, 1e-4)


def project(mu, L, s2, z):
    o = np.isfinite(z)
    Lo = L[o]
    A = Lo.T @ Lo / s2 + np.eye(L.shape[1])
    x = np.linalg.solve(A, Lo.T @ (z[o] - mu[o]) / s2)
    return mu + L @ x


def main(name):
    tables = ip.read_tables(C.BCP_DIR)
    c = ip.Cohort(tables, ip.read_axes(C.AXIS_DIR, sorted({t.tract for t in tables})))
    ages = ip.scan_ages(c, None, "months", None, None)
    bins = ip.bins_from_spec(ip.DEFAULT_BINS)
    sb = ip.scan_bins(ages, bins)
    P, M = c.n_positions, len(c.metrics)
    usable = [s for s in range(len(c.scans)) if sb[s] >= 0 and not ip.too_many_missing(c, c.scan(s), 0.5, s)]
    index = {sc: i for i, sc in enumerate(c.scans)}
    valid = c.valid
    # tract geometry: centroid of each tract's axis, 5 nearest tracts
    cent = np.stack([np.nanmean(c.points[sl], axis=0) for sl in c.slices.values()])
    dd = np.linalg.norm(cent[:, None] - cent[None], axis=2)
    np.fill_diagonal(dd, np.inf)
    near5 = np.argsort(dd, axis=1)[:, :5]
    T = len(c.tracts)
    onehot = np.zeros((T, P))
    onehot[c.tract_of, np.arange(P)] = 1
    tract_n = onehot @ valid.astype(float)  # T x M
    rows_res, rows_scan = [], []
    for seed, d, run in SETS[name]:
        passes = load_passes(d)
        if not passes:
            print("no dumps in", d)
            continue
        st = json.load(open("{}/{}_report/validation/validation_settings.json".format(C.ROOT, run)))
        sample = [index[s] for s in st["scans"]]
        rng = np.random.default_rng(int(st["seed"]) + 1)
        subjects = sorted({ip.subject_of(c.scans[s]) for s in sample})
        rng.shuffle(subjects)
        fold_of = {u: i % 5 for i, u in enumerate(subjects)}
        cells = []
        for f in range(5):
            t0 = time.time()
            held = {u for u, i in fold_of.items() if i == f}
            train = [s for s in usable if ip.subject_of(c.scans[s]) not in held]
            fprior = ip.Prior.from_cohort(c, bins, [a if ip.subject_of(sc) not in held else None
                                                    for a, sc in zip(ages, c.scans)])
            norms = [fprior.bin_norm(b) for b in range(len(bins))]
            Z = np.stack([(c.scan(s) - norms[sb[s]][0]) / norms[sb[s]][1] for s in train])
            Z = np.where(valid[None], Z, np.nan).reshape(len(train), -1).astype(np.float32)
            O = np.isfinite(Z)
            Z0 = np.where(O, Z, 0).astype(np.float32)
            svd = {r: hard_impute(Z.astype(np.float64), r) for r in RANKS}
            # tract-mean deviations of the training scans
            Zr = np.where(O, Z, 0).reshape(len(train), P, M)
            Or = O.reshape(len(train), P, M)
            tm = np.einsum("tp,spm->stm", onehot, Zr) / np.maximum(np.einsum("tp,spm->stm", onehot, Or), 1)
            tm = np.where(np.einsum("tp,spm->stm", onehot, Or) > 0, tm, np.nan).reshape(len(train), -1)
            from sklearn.experimental import enable_iterative_imputer  # noqa: F401
            from sklearn.impute import IterativeImputer
            mice = IterativeImputer(max_iter=10, n_nearest_features=40, random_state=0, skip_complete=True)
            mice.fit(tm)
            print(name, seed, "fold", f, len(train), "training scans, models {:.0f} s".format(time.time() - t0),
                  flush=True)
            mine = {c.scans[s] for s in sample if fold_of[ip.subject_of(c.scans[s])] == f}
            for (scan, fname), (pos, met, truth, mean, pat, abin) in passes.items():
                if scan not in mine:
                    continue
                s = index[scan]
                nm, nsd = norms[sb[s]]
                y = c.scan(s)
                y[pos, met] = np.nan
                z = np.where(valid, (y - nm) / nsd, np.nan)
                zf = z.reshape(-1).astype(np.float32)
                o = np.isfinite(zf)
                preds = {}
                # scan offsets
                off = np.nanmean(z, axis=0)
                off = np.where(np.isfinite(off), off, 0.0)
                preds["offset (measure)"] = off[met]
                tz = np.einsum("tp,pm->tm", onehot, np.where(np.isfinite(z), z, 0))
                tn = np.einsum("tp,pm->tm", onehot, np.isfinite(z).astype(float))
                t5 = tz[near5].sum(axis=1) / np.maximum(tn[near5].sum(axis=1), 1)
                t5 = np.where(tn[near5].sum(axis=1) > 0, t5, off[None, :])
                preds["offset (5 tracts)"] = t5[c.tract_of[pos], met]
                # kNN across scans (nan-Euclidean over co-observed cells)
                co = O & o[None]
                diff = np.where(co, Z0 - np.where(o, zf, 0)[None], 0)
                ncom = co.sum(axis=1)
                dist = np.sqrt((diff ** 2).sum(axis=1) / np.maximum(ncom, 1) * o.sum())
                dist = np.where(ncom > 0, dist, np.inf)
                order = np.argsort(dist)
                flat = pos * M + met
                for k in KS:
                    nb = order[:k]
                    w = 1.0 / np.maximum(dist[nb], 1e-6)
                    vals = Z[nb][:, flat]
                    ok = np.isfinite(vals)
                    pr = (np.where(ok, vals, 0) * w[:, None]).sum(0) / np.maximum((ok * w[:, None]).sum(0), 1e-12)
                    preds["kNN across scans, k={}".format(k)] = np.where(ok.any(0), pr, 0.0)
                for r, (mu, L, s2) in svd.items():
                    zz = np.where(o, zf, np.nan).astype(np.float64)
                    preds["iterative SVD, rank {}".format(r)] = project(mu, L, s2, zz)[flat]
                # MICE on tract means
                tmz = np.where(tn > 0, tz / np.maximum(tn, 1), np.nan).reshape(1, -1)
                imp = mice.transform(tmz).reshape(T, M)
                preds["MICE (tract means)"] = imp[c.tract_of[pos], met]
                for lab, pz in preds.items():
                    pv = nm[pos, met] + nsd[pos, met] * pz
                    cells.append(pd.DataFrame({"setting": lab, "seed": seed, "scan": scan, "call": fname,
                                               "pattern": pat, "metric": met, "age_bin": abin,
                                               "e2": (pv - truth) ** 2, "r2": (mean - truth) ** 2}))
        X = pd.concat(cells, ignore_index=True)
        a = X.groupby(["setting", "pattern", "metric", "age_bin"])[["e2", "r2"]].mean()
        rr = np.sqrt(a.e2 / a.r2).rename("r").reset_index()
        for lab, x in rr.groupby("setting"):
            r = {"setting": lab, "seed": seed, "overall": x[x.pattern.isin(FOUR)].r.mean()}
            for pt, y in x.groupby("pattern"):
                r[pt] = y.r.mean()
            wm = x[x.pattern == "whole measure"]
            r["whole dti"] = wm[wm.metric.isin([0, 1, 2, 3])].r.mean()
            r["whole noddi"] = wm[wm.metric.isin([4, 5, 6])].r.mean()
            rows_res.append(r)
        s = X.groupby(["setting", "scan", "pattern", "metric"])[["e2", "r2"]].sum()
        s = s[s.r2 > 0]
        r = np.sqrt(s.e2 / s.r2).rename("r").reset_index()
        g4 = r[r.pattern.isin(FOUR)].groupby(["setting", "scan"]).r.mean().reset_index().assign(group="4pat")
        gp = r.groupby(["setting", "scan", "pattern"]).r.mean().reset_index().rename(columns={"pattern": "group"})
        rows_scan.append(pd.concat([g4, gp]).assign(seed=seed))
        pd.DataFrame(rows_res).to_csv("{}/baselines_{}_results.csv".format(C.CACHE, name), index=False)
        pd.concat(rows_scan).to_csv("{}/baselines_{}_scans.csv".format(C.CACHE, name), index=False)
        print(pd.DataFrame(rows_res).groupby("setting").mean(numeric_only=True).round(3).to_string(), flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bcp")
