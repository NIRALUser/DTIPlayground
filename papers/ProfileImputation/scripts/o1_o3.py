"""O1 (learning curve) and O3 (finer age bins) on the hidden values of seeds 0-2 (CPU; PPCA fits on the CPU take
about 3-4 minutes each).

O1: per validation fold, a random 25, 50, 75 or 100% of the training subjects (nested draws) give the age-bin norm and
    the population model (PPCA, q = 80 or fewer when the sample is small); PPCA alone and PPCA + kNN (k = 20 on the
    residuals within 4 mm) impute the hidden cells of the dumps.
O3: the same at 100% with 7 finer age bins (0-1, 2-3, 4-6, 7-9, 10-14, 15-24, 25-65 months) for the norm and the
    deviations; also the finer-bin mean alone.
Scores are relative to the 3-bin age-bin mean stored in the dumps (the common reference). Writes
cache/o1o3_results.csv and cache/o1o3_scans.csv.

usage: o1_o3.py [o1] [o3]
"""
import json
import sys
import time

import numpy as np
import pandas as pd

import common as C
from baselines import load_passes

sys.path.insert(0, C.REPO)
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip  # noqa: E402

FOUR = C.PATS
RUNS = [(0, "v15/dump_R3", "v15/R3_s0"), (1, "v15/dump_R3_s1", "v15/R3_s1"), (2, "v15/dump_R3_s2", "v15/R3_s2")]
FINE = "0-1,2-3,4-6,7-9,10-14,15-24,25-65"


def main(parts):
    import torch
    torch.set_num_threads(2)
    tables = ip.read_tables(C.BCP_DIR)
    c = ip.Cohort(tables, ip.read_axes(C.AXIS_DIR, sorted({t.tract for t in tables})))
    ages = ip.scan_ages(c, None, "months", None, None)
    index = {sc: i for i, sc in enumerate(c.scans)}
    configs = []
    if "o1" in parts:
        configs += [("O1", f, ip.DEFAULT_BINS) for f in (0.25, 0.5, 0.75, 1.0)]
    if "o3" in parts:
        configs += [("O3", 1.0, FINE)]
    cells, scans_out = [], []
    for seed, d, run in RUNS:
        passes = load_passes(d)
        st = json.load(open("{}/{}_report/validation/validation_settings.json".format(C.ROOT, run)))
        sample = [index[s] for s in st["scans"]]
        rng = np.random.default_rng(int(st["seed"]) + 1)
        subjects = sorted({ip.subject_of(c.scans[s]) for s in sample})
        rng.shuffle(subjects)
        fold_of = {u: i % 5 for i, u in enumerate(subjects)}
        for f in range(5):
            held = {u for u, i in fold_of.items() if i == f}
            mine = {c.scans[s] for s in sample if fold_of[ip.subject_of(c.scans[s])] == f}
            for exp, frac, spec in configs:
                t0 = time.time()
                bins = ip.bins_from_spec(spec)
                sb = ip.scan_bins(ages, bins)
                usable = [s for s in range(len(c.scans)) if sb[s] >= 0
                          and not ip.too_many_missing(c, c.scan(s), 0.5, s)]
                train_subj = sorted({ip.subject_of(c.scans[s]) for s in usable} - held)
                keep = set(np.random.default_rng([seed, f]).permutation(train_subj)[:int(round(frac * len(train_subj)))])
                train = [s for s in usable if ip.subject_of(c.scans[s]) in keep]
                tages = [a if ip.subject_of(sc) in keep else None for a, sc in zip(ages, c.scans)]
                fprior = ip.Prior.from_cohort(c, bins, tages)
                q = min(80, len(train) - 1)
                model = ip.Population.fit(c, fprior, train, q, "isotropic", device="cpu", sd_folds=0)
                label = "{} {:g}%".format(exp, 100 * frac) if exp == "O1" else "O3 fine bins"
                for (scan, fname), (pos, met, truth, mean, pat, abin) in passes.items():
                    if scan not in mine:
                        continue
                    s = index[scan]
                    nm, nsd = fprior.bin_norm(sb[s])
                    y = c.scan(s)
                    y[pos, met] = np.nan
                    zp, zsd = model.predict((y - nm) / nsd)
                    pv, psd = nm + nsd * zp, nsd * zsd
                    pv = np.where(np.isfinite(pv), pv, nm)
                    dist = ip.nearest_observed(c.points, y, c.valid)
                    kr = ip.impute_scan(y, c, "knn", {"k": 20, "weights": "distance"}, {}, norm=(pv, psd),
                                        relative=True)
                    kr = ip.limit(kr, y, c, dist, 4.0, spatial=True)
                    preds = {"PPCA": pv, "PPCA + kNN": np.where(np.isnan(kr), pv, kr)}
                    if exp == "O3":
                        preds["norm alone"] = nm
                    for lab, p in preds.items():
                        cells.append(pd.DataFrame({"setting": "{}: {}".format(label, lab), "seed": seed, "scan": scan,
                                                   "pattern": pat, "metric": met, "age_bin": abin,
                                                   "e2": (p[pos, met] - truth) ** 2, "r2": (mean - truth) ** 2}))
                print(seed, f, label, len(train), "training scans, q", q, "{:.0f} s".format(time.time() - t0),
                      flush=True)
        X = pd.concat(cells, ignore_index=True)
        a = X.groupby(["setting", "seed", "pattern", "metric", "age_bin"])[["e2", "r2"]].mean()
        rr = np.sqrt(a.e2 / a.r2).rename("r").reset_index()
        rows = []
        for (lab, sd), x in rr.groupby(["setting", "seed"]):
            r = {"setting": lab, "seed": sd, "overall": x[x.pattern.isin(FOUR)].r.mean()}
            for pt, y in x.groupby("pattern"):
                r[pt] = y.r.mean()
            wm = x[x.pattern == "whole measure"]
            r["whole dti"] = wm[wm.metric.isin([0, 1, 2, 3])].r.mean()
            r["whole noddi"] = wm[wm.metric.isin([4, 5, 6])].r.mean()
            rows.append(r)
        pd.DataFrame(rows).to_csv(C.CACHE + "/o1o3_results.csv", index=False)
        s = X.groupby(["setting", "seed", "scan", "pattern", "metric"])[["e2", "r2"]].sum()
        s = s[s.r2 > 0]
        r = np.sqrt(s.e2 / s.r2).rename("r").reset_index()
        g4 = r[r.pattern.isin(FOUR)].groupby(["setting", "seed", "scan"]).r.mean().reset_index().assign(group="4pat")
        gp = r.groupby(["setting", "seed", "scan", "pattern"]).r.mean().reset_index().rename(
            columns={"pattern": "group"})
        pd.concat([g4, gp]).to_csv(C.CACHE + "/o1o3_scans.csv", index=False)


if __name__ == "__main__":
    main(sys.argv[1:] or ["o1", "o3"])
