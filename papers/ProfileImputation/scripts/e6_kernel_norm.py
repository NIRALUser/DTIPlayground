"""E6: a continuous (kernel) age norm as a second, reference-independent baseline.

For each seed of the phase-4 protocol (0-2; and any v16 run given on the command line), the validated scans are split
into the same 5 folds by subject as in impute_profiles.validate (fold_variants: rng seed + 1, sorted subjects
shuffled, i % 5), and a local-linear kernel norm in log(age + 1 month) (bandwidth by leave-one-out CV, as
--age-norm kernel) is fitted on the usable scans of all other subjects. The norm mean at each validated scan's age is
saved to cache/kernel_norm_<run>.npz (key: scan name; positions x metrics). dump_analysis.py scores it on the dumped
hidden cells. CPU, about 2-4 minutes per fold.

usage: e6_kernel_norm.py [RUN ...]   RUN: a validation report folder relative to ROOT (default: v15/R3_s0..2)
"""
import json
import sys
import time

import numpy as np

import common as C

sys.path.insert(0, C.REPO)
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip  # noqa: E402


def main(runs, profiles=C.BCP_DIR, age_csv=None):
    tables = ip.read_tables(profiles)
    c = ip.Cohort(tables, ip.read_axes(C.AXIS_DIR, sorted({t.tract for t in tables})))
    ages = ip.scan_ages(c, age_csv, "months", None, None)
    bins = ip.bins_from_spec(ip.DEFAULT_BINS)
    sb = ip.scan_bins(ages, bins)
    usable = [s for s in range(len(c.scans)) if sb[s] >= 0 and not ip.too_many_missing(c, c.scan(s), 0.5, s)]
    index = {sc: i for i, sc in enumerate(c.scans)}
    for run in runs:
        st = json.load(open("{}/{}_report/validation/validation_settings.json".format(C.ROOT, run)))
        sample = [index[s] for s in st["scans"] if s in index]
        seed = int(st["seed"])
        rng = np.random.default_rng(seed + 1)
        subjects = sorted({ip.subject_of(c.scans[s]) for s in sample})
        rng.shuffle(subjects)
        fold_of = {u: i % 5 for i, u in enumerate(subjects)}
        out = {}
        for f in range(5):
            t0 = time.time()
            held = {u for u, i in fold_of.items() if i == f}
            train = [s for s in usable if ip.subject_of(c.scans[s]) not in held]
            norm = ip.AgeNorm.fit(c, ages, train, "kernel", bins, bandwidth="cv", device="cpu", sd_folds=0)
            for s in sample:
                if fold_of[ip.subject_of(c.scans[s])] == f:
                    out[c.scans[s]] = norm.at(ages[s])[0].astype(np.float32)
            print(run, "fold", f, "bandwidth", norm.info.get("bandwidth"), "{:.0f} s".format(time.time() - t0),
                  flush=True)
        name = run.replace("/", "_")
        np.savez_compressed("{}/kernel_norm_{}.npz".format(C.CACHE, name), **out)


if __name__ == "__main__":
    args = sys.argv[1:] or ["v15/R3_s0", "v15/R3_s1", "v15/R3_s2"]
    bcp = [a for a in args if not a.startswith("v16/E3")]
    hbcd = [a for a in args if a.startswith("v16/E3")]
    if bcp:
        main(bcp)
    if hbcd:  # HBCD alone (E3)
        main(hbcd, C.HBCD_DIR, C.HBCD_AGES)
