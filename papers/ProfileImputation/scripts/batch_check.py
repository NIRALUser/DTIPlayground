"""M4/E5: does the batch correction (one shift and scale per cell at the same age) leave an age-by-cohort interaction?

BCP and HBCD are pooled and corrected to BCP with the defaults of impute-profiles (spline of 6 df in log(age + 1),
constant shift, scale limits 3). Within age windows covered by both cohorts, the mean corrected value of each cohort
is compared per cell (difference in units of the BCP between-scan SD of the window), and summarised per measure by
the median over cells. If the correction were right at every age, the differences would scatter around 0 in every
window. Also writes the age distribution of both cohorts within the three age bins (age composition of the bins).
Writes cache/batch_check.csv and cache/batch_age_composition.csv.
"""
import sys

import numpy as np
import pandas as pd

import common as C

sys.path.insert(0, C.REPO)
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip  # noqa: E402

WINDOWS = [(0, 1.5), (1.5, 3.5), (3.5, 6.5), (6.5, 9.5), (9.5, 16)]


def main():
    tables = ip.read_batches([C.BCP_DIR, C.HBCD_DIR], ["BCP", "HBCD"])
    c = ip.Cohort(tables, None)
    ages = ip.scan_ages(c, C.HBCD_AGES, "months", None, None)
    corr = ip.BatchCorrection.fit(c, ages, 0, 6, 2, 1.0, (), shift="constant",
                                  limits=ip.batch_scale_limits(ip.BATCH_SCALE_LIMIT, c.metrics))
    V = corr.apply(c.values, ages, c.scan_batch)
    a = np.array([np.nan if x is None else x for x in ages])
    rows = []
    for lo, hi in WINDOWS:
        sel = (a >= lo) & (a < hi)
        b = sel & (c.scan_batch == 0)
        h = sel & (c.scan_batch == 1)
        if b.sum() < 5 or h.sum() < 5:
            continue
        mb, mh = np.nanmean(V[b], axis=0), np.nanmean(V[h], axis=0)
        sd = np.nanstd(V[b], axis=0)
        # age composition within the window: the BCP mean at the HBCD ages would differ by the age trend; report
        # the mean ages as well
        dz = (mh - mb) / np.where(sd > 0, sd, np.nan)
        for m, metric in enumerate(c.metrics):
            x = dz[:, m]
            x = x[np.isfinite(x)]
            rows.append(dict(window="{:g}-{:g}".format(lo, hi), metric=metric, n_bcp=int(b.sum()),
                             n_hbcd=int(h.sum()), age_bcp=float(np.nanmean(a[b])), age_hbcd=float(np.nanmean(a[h])),
                             median_dz=float(np.median(x)), q25=float(np.percentile(x, 25)),
                             q75=float(np.percentile(x, 75))))
    pd.DataFrame(rows).to_csv(C.CACHE + "/batch_check.csv", index=False)
    comp = []
    sbin = ip.scan_bins(ages, ip.bins_from_spec(ip.DEFAULT_BINS))
    for name, bi in (("BCP", 0), ("HBCD", 1)):
        for k, (lo, hi, lab) in enumerate(ip.bins_from_spec(ip.DEFAULT_BINS)):
            x = a[(c.scan_batch == bi) & (sbin == k)]
            comp.append(dict(cohort=name, bin=lab, n=len(x), mean=np.mean(x) if len(x) else np.nan,
                             median=np.median(x) if len(x) else np.nan,
                             q10=np.percentile(x, 10) if len(x) else np.nan,
                             q90=np.percentile(x, 90) if len(x) else np.nan))
    pd.DataFrame(comp).to_csv(C.CACHE + "/batch_age_composition.csv", index=False)
    print(pd.DataFrame(rows).round(2).to_string())
    print(pd.DataFrame(comp).round(2).to_string())


if __name__ == "__main__":
    main()
