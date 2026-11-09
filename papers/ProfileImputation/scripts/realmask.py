"""Real-mask pass by donor load (round-2 review, N1/R1).

The real-mask pass of --validate-real-masks hides in a validated scan the missing cells of a donor scan (same age bin,
another subject). The donor is drawn from every scan with missing values, including donors that miss more than the
--max-missing-tracts share (0.5) of their tracts, which impute-profiles itself leaves unimputed. The dumps do not name
the donor, so it is recovered here: a donor d matches a pass when (missing cells of d) & (observed cells of the scan)
equals the hidden cells of the pass. Its load is ip.missing_tracts (tracts with no observed value of any metric, the
rule of --max-missing-tracts).

For the dump datasets e1 (BCP, untouched subjects) and e3 (HBCD alone), with the predictions of dump_analysis.py
(identical settings, the same cross-fitting), writes
  cache/realmask_<ds>_passes.csv  one row per real-mask pass: seed, scan, k, donor(s), donor missing tracts, tracts,
                                  donor share, hidden locations, share of the scan's locations hidden, cells
  cache/realmask_<ds>_sums.csv    per setting, seed, pass, metric, age bin: sums of squared errors (setting, age-bin
                                  mean) and counts
PPCA alone is not in the dumps (see the paper). CPU, about 15 minutes per dataset.

usage: realmask.py [e1] [e3]
"""
import sys

import numpy as np
import pandas as pd

import common as C
import dump_analysis as D
from dump_analysis import ip


def donor_table(c, X, seed, ages):
    """Recover the donor of every real-mask pass of X (cells of one seed). The draws of validate() are replayed
    (np.random.default_rng(seed + 3), one donor per round, 3 rounds per scan, scans in the order of their dumps, the
    same pool); a replayed donor is accepted when its missing cells reproduce the hidden cells exactly. Passes without
    an accepted replay fall back to matching: every donor whose missing cells reproduce them (same age bin
    preferred); the load is then the smallest of the matches."""
    nsc, npos, nm = c.values.shape
    miss = np.zeros((nsc, npos * nm), bool)
    for d in range(nsc):
        miss[d] = (np.isnan(c.values[d]) & c.valid_of(d)).ravel()
    donors = np.flatnonzero(miss.any(axis=1))
    load = {d: ip.missing_tracts(c, c.values[d], d) for d in donors}
    index = {s: i for i, s in enumerate(c.scans)}
    subj = np.array([ip.subject_of(s) for s in c.scans])
    sbin = np.asarray(ip.scan_bins([ages.get(s) for s in c.scans], ip.bins_from_spec(ip.DEFAULT_BINS)))
    R = X[X.pattern == "real mask"]
    order = R.drop_duplicates(["scan", "k"])[["scan", "k"]]
    hidden = {key: g for key, g in R.groupby(["scan", "k"])}
    rng = np.random.default_rng(seed + 3)
    rounds = 3  # --validate-rounds of the v16 runs
    drawn = {}
    for sc in X.drop_duplicates("scan").scan.tolist():
        s = index[sc]
        pool = [d for d in donors if sbin[s] >= 0 and sbin[d] == sbin[s] and subj[d] != subj[s]] or \
            [d for d in donors if subj[d] != subj[s]]
        drawn[sc] = [pool[rng.integers(len(pool))] for _ in range(rounds)]
    rows = []
    for sc, k in order.itertuples(index=False):
        g = hidden[(sc, k)]
        s = index[sc]
        obs = (~np.isnan(c.values[s]) & c.valid).ravel()
        h = np.zeros(npos * nm, bool)
        h[g.position.to_numpy() * nm + g.metric.to_numpy()] = True
        ok = [d for d in drawn[sc] if (miss[d][obs] == h[obs]).all()]
        how = "replayed"
        if ok:
            hit = np.array(ok[:1])
        else:
            cand = donors[subj[donors] != subj[s]]
            hit = cand[((miss[cand][:, obs]) == h[obs]).all(axis=1)]
            same = hit[sbin[hit] == sbin[s]]
            hit = same if len(same) else hit
            how = "matched"
        mt = [load[d][0] for d in hit]
        nt = [load[d][1] for d in hit]
        rows.append(dict(scan=sc, k=k, how=how, n_match=len(hit), donor=";".join(c.scans[d] for d in hit[:3]),
                         donor_missing=min(mt) if mt else np.nan, donor_missing_max=max(mt) if mt else np.nan,
                         donor_tracts=nt[0] if nt else np.nan, hidden_locs=g.position.nunique(),
                         share_hidden=g.position.nunique() / npos, cells=len(g), age_bin=g.age_bin.iloc[0]))
    P = pd.DataFrame(rows)
    P["donor_share"] = P.donor_missing / P.donor_tracts
    return P


def main(names):
    for name in names:
        spec = D.DATASETS[name]
        c, ages = D.cohort(spec["cohort"])
        parts, passes = [], []
        for seed, d, _, _ in spec["seeds"]:
            A = D.load(d)
            if A is None:
                continue
            A = D.split_local(A)
            P = donor_table(c, A, seed, ages)
            print(name, seed, len(P), "passes; replayed", (P.how == "replayed").mean(), "matched",
                  (P.n_match >= 1).mean(), "ambiguous load", (P.donor_missing != P.donor_missing_max).sum(),
                  flush=True)
            A["seed"] = seed
            A["scan"] = A.scan + "#{}".format(seed)
            P["seed"] = seed
            P["scan"] = P.scan + "#{}".format(seed)
            parts.append(A)
            passes.append(P)
        X = pd.concat(parts, ignore_index=True)
        P = pd.concat(passes, ignore_index=True)
        P.to_csv("{}/realmask_{}_passes.csv".format(C.CACHE, name), index=False)
        pred = D.predictions(X, "cohort", False)
        R = (X.pattern == "real mask").to_numpy()
        r2 = (X["mean"] - X.truth).to_numpy() ** 2
        out = []
        for label, (p, _) in pred.items():
            pf = np.where(np.isfinite(p), p, X["mean"])
            e2 = (pf - X.truth.to_numpy()) ** 2
            g = pd.DataFrame({"seed": X.seed, "scan": X.scan, "k": X.k, "metric": X.metric, "age_bin": X.age_bin,
                              "e2": e2, "r2": r2})[R]
            a = g.groupby(["seed", "scan", "k", "metric", "age_bin"]).agg(
                e2=("e2", "sum"), r2=("r2", "sum"), n=("e2", "size")).reset_index()
            out.append(a.assign(setting=label))
        pd.concat(out, ignore_index=True).to_csv("{}/realmask_{}_sums.csv".format(C.CACHE, name), index=False)
        print(name, "done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["e1", "e3"])
