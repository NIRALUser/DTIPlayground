"""E4: what imputation does to a typical analysis (CPU; saved transformers in inference only).

Design
  data       the 220 BCP scans without any missing value (133 subjects), in the 5 folds of
             v16/e4_complete_folds.csv; for fold k the norm (age bins), the population model and the transformer
             were fitted without the subjects of fold k (v16/e4_fold{k}/transformer.pt, which carries its PPCA)
  planted    per replicate: a random half of the subjects is group 1; in 5 random tracts their values are shifted by
             delta = 0.3 between-scan SD (per location and measure, all 7 measures)
  masks      per replicate and scan: the real missingness (valid & missing) of a random donor, a BCP scan of the
             same age bin and another subject (all BCP scans with < 50% missing tracts are donors, so about half of
             the scans receive a mask, as in BCP)
  imputers   complete case (drop a scan with any missing value); available case (drop the scan for a tract with
             any missing value of the measure); age-bin mean; PPCA (posterior mean); PPCA + kNN (k = 20 on the
             PPCA residuals within 4 mm, PPCA beyond); blend of PPCA + kNN with the fold transformer using the
             SHIPPED weight table (its "near" weights were fitted for SIREN cells, here applied to kNN cells);
             multiple imputation (M draws from the PPCA posterior with the per-measure SD calibration of the fold's
             population model, Rubin's rules)
  analyses   per tract and measure (FA, MD), the tract mean per scan:
             (i) trajectory: mean ~ natural spline(log(age + 1), 4 df), OLS with cluster-robust (subject) SEs, on
                 the tracts without a planted effect; against the fit on the complete data: integrated absolute
                 bias (in units of the between-scan SD of the tract mean), CI width ratio, pointwise coverage of
                 the complete-data curve
             (ii) group effect: mean ~ group + spline(log age): estimate, SE, rejection at alpha 0.05, for planted
                 and not planted tracts; bias relative to the planted shift of the tract mean
Writes cache/e4_<tag>.csv (one row per replicate, imputer, tract, measure) and cache/e4_<tag>_timing.txt.

  differential missingness (round-2 review, N3): --mask-groups g1 --donors missing masks every group-1 scan and no
             group-0 scan, so the masks are concentrated in the group with the planted effect
usage: e4_downstream.py [--reps R] [--mi M] [--dev] [--tag NAME] [--start R0] [--delta D] [--donors all|missing]
                        [--mask-groups all|g1]
  --dev: use v15/impute_default_transformer.pt for every fold (NOT leave-fold-out; timing and debugging only)
"""
import argparse
import re
import sys
import time

import numpy as np
import pandas as pd

import common as C

sys.path.insert(0, C.REPO)
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip  # noqa: E402
from dtiplayground.dmri.fiberprofile.analysis.amortized import AmortizedModel  # noqa: E402

V16 = C.ROOT + "/v16"
DELTA = 0.3
N_PLANT = 5
ANALYSED = ("fa", "md")


def spline_basis(t, knots):
    return ip.ns_basis(t, knots)


def ols_cluster(X, y, groups):
    """OLS estimate and cluster-robust (CR1) covariance."""
    XtX = np.linalg.inv(X.T @ X)
    b = XtX @ X.T @ y
    r = y - X @ b
    u, inv = np.unique(groups, return_inverse=True)
    S = np.zeros((X.shape[1], X.shape[1]))
    G = np.zeros((len(u), X.shape[1]))
    np.add.at(G, inv, X * r[:, None])
    S = G.T @ G
    n, p, g = len(y), X.shape[1], len(u)
    cf = g / (g - 1) * (n - 1) / (n - p)
    return b, cf * XtX @ S @ XtX


def ppca_parts(model):
    pp = model._ppca
    return (pp.mu.cpu().numpy().astype(np.float64), pp.W.cpu().numpy().astype(np.float64),
            pp.psi.cpu().numpy().astype(np.float64), pp.cells)


def ppca_post(mu, W, psi, cells, z):
    zc = z.reshape(-1)[cells]
    o = np.isfinite(zc)
    Wo = W[o] / psi[o, None]
    Sig = np.linalg.inv(np.eye(W.shape[1]) + Wo.T @ W[o])
    x = Sig @ (Wo.T @ (zc[o] - mu[o]))
    return x, Sig


def sd_scales(log, metrics):
    m = re.search(r"Population SDs scaled per metric by (.*?) \(", open(log).read())
    if not m:
        return np.ones(len(metrics))
    d = dict(re.findall(r"(\w+) ([\d.]+)", m.group(1)))
    return np.array([float(d.get(x, 1.0)) for x in metrics])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=50)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--mi", type=int, default=10)
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--tag", default="main")
    ap.add_argument("--delta", type=float, default=DELTA, help="planted shift in between-scan SD (default 0.3)")
    ap.add_argument("--donors", choices=("all", "missing"), default="all",
                    help="mask donors: all BCP scans (about half have missing values) or only those with missing values")
    ap.add_argument("--mask-groups", choices=("all", "g1"), default="all",
                    help="scans that receive a donor mask: all, or only those of group 1 (differential missingness: "
                         "the group with the planted effect is the group with the missing values)")
    a = ap.parse_args()
    t_start = time.time()
    tables = ip.read_tables(C.BCP_DIR)
    c = ip.Cohort(tables, ip.read_axes(C.AXIS_DIR, sorted({t.tract for t in tables})))
    ages = ip.scan_ages(c, None, "months", None, None)
    bins = ip.bins_from_spec(ip.DEFAULT_BINS)
    sb = ip.scan_bins(ages, bins)
    P, M = c.n_positions, len(c.metrics)
    folds = pd.read_csv(V16 + "/e4_complete_folds.csv")
    idx = {s: i for i, s in enumerate(c.scans)}
    comp = np.array([idx[s] for s in folds.scan])
    fold = folds.fold.to_numpy()
    subj = np.array([ip.subject_of(c.scans[s]) for s in comp])
    donors = [s for s in range(len(c.scans)) if sb[s] >= 0 and not ip.too_many_missing(c, c.scan(s), 0.5, s)]
    if a.donors == "missing":
        donors = [s for s in donors if (np.isnan(c.values[s]) & c.valid).any()]
    dsubj = np.array([ip.subject_of(c.scans[s]) for s in donors])
    valid = c.valid
    loc_sd = np.nanstd(c.values[comp], axis=0)  # between-scan SD of the complete scans
    # fold models and norms
    models, norms, scales, parts = [], [], [], []
    for k in range(5):
        held = set(folds.subject[folds.fold == k])
        pr = ip.Prior.from_cohort(c, bins, [ag if ip.subject_of(sc) not in held else None
                                            for ag, sc in zip(ages, c.scans)])
        norms.append([pr.bin_norm(b) for b in range(len(bins))])
        path = C.ROOT + "/v15/impute_default_transformer.pt" if a.dev else V16 + "/e4_fold{}/transformer.pt".format(k)
        mdl = AmortizedModel.load(path, c, device="cpu")
        models.append(mdl)
        parts.append(ppca_parts(mdl))
        scales.append(sd_scales(V16 + "/e4_fold{}.log".format(k), c.metrics) if not a.dev else np.ones(M))
    table = ip.EnsembleWeights.parse("table", "cohort")
    tract_slices = list(c.slices.values())
    ana = [c.metrics.index(m) for m in ANALYSED]
    lt = np.log(np.array([ages[s] for s in comp]) + 1.0)
    knots = ip.spline_knots(lt, 4)
    B = spline_basis(lt, knots)
    grid = np.linspace(np.percentile(lt, 5), np.percentile(lt, 95), 40)
    Bg = spline_basis(grid, knots)
    Xtraj = np.column_stack([np.ones(len(lt)), B])
    Xg = np.column_stack([np.ones(len(grid)), Bg])
    timing = []
    rows = []
    for rep in range(a.start, a.start + a.reps):
        t0 = time.time()
        rng = np.random.default_rng(1000 + rep)
        us = np.unique(subj)
        g1 = set(rng.choice(us, size=len(us) // 2, replace=False))
        group = np.array([1.0 if u in g1 else 0.0 for u in subj])
        planted = rng.choice(len(c.tracts), N_PLANT, replace=False)
        Y = c.values[comp].astype(np.float64).copy()
        for t in planted:
            sl = tract_slices[t]
            Y[group == 1, sl, :] += a.delta * loc_sd[None, sl, :]
        masks = np.zeros(Y.shape, dtype=bool)
        for i, s in enumerate(comp):
            pool = [d for d, u in zip(donors, dsubj) if sb[d] == sb[s] and u != subj[i]]
            dn = pool[rng.integers(len(pool))]
            masks[i] = valid & np.isnan(c.values[dn])
        if a.mask_groups == "g1":  # same random stream; only group 1 keeps its masks
            masks[group == 0] = False
        has = masks.reshape(len(comp), -1).any(axis=1)
        imp = {"age-bin mean": Y.copy(), "PPCA": Y.copy(), "PPCA + kNN": Y.copy(), "blend (table)": Y.copy()}
        mi = [Y.copy() for _ in range(a.mi)]
        for i in np.flatnonzero(has):
            k = fold[i]
            nm, nsd = norms[k][sb[comp[i]]]
            Ym = np.where(masks[i], np.nan, Y[i])
            z = np.where(valid, (Ym - nm) / nsd, np.nan)
            mu, W, psi, cells = parts[k]
            x, Sig = ppca_post(mu, W, psi, cells, z)
            zp = np.full(P * M, np.nan)
            zp[cells] = mu + W @ x
            zp = zp.reshape(P, M)
            pv = nm + nsd * zp
            psd_full = np.full(P * M, np.nan)
            psd_full[cells] = np.sqrt(psi + ((W @ Sig) * W).sum(axis=1))
            psd = nsd * psd_full.reshape(P, M)
            miss = masks[i]
            imp["age-bin mean"][i][miss] = nm[miss]
            imp["PPCA"][i][miss] = pv[miss]
            dist = ip.nearest_observed(c.points, Ym, valid)
            kr = ip.impute_scan(Ym, c, "knn", {"k": 20, "weights": "distance"}, {}, norm=(pv, psd), relative=True)
            kr = ip.limit(kr, Ym, c, dist, 4.0, spatial=True)
            base = np.where(np.isnan(kr), pv, kr)
            imp["PPCA + kNN"][i][miss] = base[miss]
            gm, gs = models[k].predict(z, crossfit=0)
            gv = nm + nsd * gm
            near = ~np.isnan(kr)
            w = table.of(c.metrics, near, dist)
            ok = np.isfinite(gv) & np.isfinite(base)
            bl = np.where(ok, (1 - w) * base + w * gv, base)
            imp["blend (table)"][i][miss] = bl[miss]
            # multiple imputation from the PPCA posterior (calibrated per measure)
            L = np.linalg.cholesky(Sig + 1e-10 * np.eye(len(Sig)))
            for mdraw in mi:
                xd = x + L @ rng.standard_normal(len(x))
                zd = np.full(P * M, np.nan)
                zd[cells] = mu + W @ xd + np.sqrt(psi) * rng.standard_normal(len(psi))
                zd = zd.reshape(P, M)
                zd = zp + (zd - zp) * scales[k][None, :]
                v = nm + nsd * zd
                mdraw[i][miss] = v[miss]
        t_imp = time.time() - t0

        # analyses
        def tract_means(V):
            return np.stack([np.nanmean(V[:, sl, :], axis=1) for sl in tract_slices], axis=1)  # scans x T x M
        full_tm = tract_means(Y)
        sets = {name: tract_means(V) for name, V in imp.items()}
        mis_tm = np.stack([masks[:, sl, :].any(axis=1) for sl in tract_slices], axis=1)
        mi_tm = [tract_means(V) for V in mi]
        Xgrp = np.column_stack([np.ones(len(lt)), group, B])

        def fit_all(tm, keep):
            out = {}
            for t in range(len(c.tracts)):
                for m in ana:
                    sel = keep[:, t, m] if keep.ndim == 3 else keep
                    y = tm[sel, t, m]
                    if sel.sum() < 30:
                        continue
                    bt, Vt = ols_cluster(Xtraj[sel], y, subj[sel])
                    if np.unique(group[sel]).size > 1:
                        bg, Vg = ols_cluster(Xgrp[sel], y, subj[sel])
                        out[(t, m)] = (bt, Vt, bg[1], np.sqrt(Vg[1, 1]), sel.sum())
                    else:  # one group left (complete case under differential missingness): no group estimate
                        out[(t, m)] = (bt, Vt, np.nan, np.nan, sel.sum())
            return out
        everyone = np.ones(len(comp), dtype=bool)
        ref = fit_all(full_tm, everyone)
        fits = {"complete case": fit_all(full_tm, ~has), "available case": fit_all(full_tm, ~mis_tm)}
        for name, tm in sets.items():
            fits[name] = fit_all(tm, everyone)
        mi_fits = [fit_all(tm, everyone) for tm in mi_tm]
        sdt = np.nanstd(full_tm, axis=0)
        for name, F in list(fits.items()) + [("multiple imputation (PPCA)", None)]:
            for (t, m), (bt0, Vt0, d0, se0, n0) in ref.items():
                if F is not None:
                    if (t, m) not in F:
                        continue
                    bt, Vt, d, se, n = F[(t, m)]
                    curve, cvar = Xg @ bt, np.einsum("gi,ij,gj->g", Xg, Vt, Xg)
                else:  # Rubin's rules
                    fs = [f[(t, m)] for f in mi_fits]
                    curves = np.stack([Xg @ f[0] for f in fs])
                    wv = np.mean([np.einsum("gi,ij,gj->g", Xg, f[1], Xg) for f in fs], axis=0)
                    curve, cvar = curves.mean(0), wv + (1 + 1 / len(fs)) * curves.var(0, ddof=1)
                    ds = np.array([f[2] for f in fs])
                    d = ds.mean()
                    se = np.sqrt(np.mean([f[3] ** 2 for f in fs]) + (1 + 1 / len(fs)) * ds.var(ddof=1))
                    n = fs[0][4]
                c0 = Xg @ bt0
                w0 = 2 * 1.96 * np.sqrt(np.einsum("gi,ij,gj->g", Xg, Vt0, Xg))
                half = 1.96 * np.sqrt(cvar)
                true_shift = a.delta * np.nanmean(loc_sd[tract_slices[t], m]) if t in planted else 0.0
                rows.append(dict(rep=rep, delta_planted=a.delta, donors=a.donors, mask_groups=a.mask_groups, imputer=name, tract=c.tracts[t], metric=c.metrics[m],
                                 planted=t in planted, n=n, missing_share=float(mis_tm[:, t, m].mean()),
                                 bias=np.mean(np.abs(curve - c0)) / sdt[t, m],
                                 ci_ratio=np.mean(2 * half) / np.mean(w0),
                                 coverage=np.mean(np.abs(curve - c0) <= half),
                                 delta=d, se=se, delta_full=d0, se_full=se0, true_shift=true_shift,
                                 reject=float(abs(d / se) > 1.96) if np.isfinite(d / se) else np.nan))
        timing.append((rep, t_imp, time.time() - t0, int(has.sum())))
        print("rep {} done: {} masked scans, imputation {:.0f} s, total {:.0f} s".format(
            rep, int(has.sum()), t_imp, time.time() - t0), flush=True)
        pd.DataFrame(rows).to_csv("{}/e4_{}.csv".format(C.CACHE, a.tag), index=False)
    with open("{}/e4_{}_timing.txt".format(C.CACHE, a.tag), "w") as fh:
        for r in timing:
            fh.write("rep {} imputation {:.1f} s total {:.1f} s masked scans {}\n".format(*r))
        fh.write("wall {:.0f} s\n".format(time.time() - t_start))


if __name__ == "__main__":
    main()
