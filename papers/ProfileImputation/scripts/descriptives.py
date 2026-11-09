"""Dataset descriptives of the profile tables (BCP normative cohort, HBCD reference cohort): scans, subjects, sessions,
ages, acquisitions, and the missingness of the real (cleaned) profiles. Reads the profile tables with the reader of
impute-profiles itself, so the cells are those the method sees. Writes tables/descriptives_macros.tex,
tables/tab_data.tex and scripts/cache/desc_*.csv."""
import re
import sys
from collections import Counter

import numpy as np
import pandas as pd

import common as C

sys.path.insert(0, C.REPO)
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip  # noqa: E402

BINS = ip.bins_from_spec(ip.DEFAULT_BINS)


def load(d, age_csv=None):
    tables = ip.read_tables(d)
    axes = ip.read_axes(C.AXIS_DIR, sorted({t.tract for t in tables}))
    c = ip.Cohort(tables, axes)
    if age_csv:
        ages = ip.scan_ages(c, age_csv, "months", None, None)
    else:
        ages = ip.scan_ages(c, None, "months", None, None)
    return c, np.asarray([np.nan if a is None else float(a) for a in ages])


def basic(c, ages, name):
    subj = [ip.subject_of(s) for s in c.scans]
    per = Counter(subj)
    b = ip.scan_bins(list(ages), BINS)
    out = {"name": name, "scans": len(c.scans), "subjects": len(per),
           "sess_median": float(np.median(list(per.values()))), "sess_max": max(per.values()),
           "subj_1": sum(v == 1 for v in per.values()), "subj_2plus": sum(v >= 2 for v in per.values()),
           "age_min": np.nanmin(ages), "age_max": np.nanmax(ages), "age_median": np.nanmedian(ages),
           "age_q1": np.nanpercentile(ages, 25), "age_q3": np.nanpercentile(ages, 75),
           "tracts": len(c.tracts), "positions": c.n_positions, "metrics": len(c.metrics)}
    for i, (lo, hi, lab) in enumerate(BINS):
        out["bin_" + lab] = int(np.sum(b == i))
        out["subj_" + lab] = len({subj[k] for k in np.flatnonzero(b == i)})
    out["bin_none"] = int(np.sum(b < 0))
    acq = Counter(m.group(1) if m else "none" for m in (re.search(r"_acq-([^_]+)", s) for s in c.scans))
    out["acq"] = dict(acq)
    return out, b


def missingness(c):
    """Per scan x tract x metric: whole profile missing, partial (start/end, interior gap), lengths in positions."""
    rows = []
    V = c.values
    for tract, sl in c.slices.items():
        for m, metric in enumerate(c.metrics):
            valid = c.valid[sl, m]
            if not valid.any():
                continue
            X = V[:, sl, m][:, valid]  # scans x positions of the table
            miss = np.isnan(X)
            n = miss.shape[1]
            for s in range(len(c.scans)):
                k = miss[s]
                if not k.any():
                    continue
                if k.all():
                    rows.append((s, tract, metric, "whole", n, n, 0, 0, 0))
                    continue
                obs = np.flatnonzero(~k)
                start = obs[0]
                end = n - 1 - obs[-1]
                interior = int(k[obs[0]:obs[-1] + 1].sum())
                rows.append((s, tract, metric, "partial", n, int(k.sum()), int(start), int(end), interior))
    return pd.DataFrame(rows, columns=["scan", "tract", "metric", "kind", "n_pos", "n_missing", "start", "end",
                                       "interior"])


def axis_proximity(c):
    from scipy.spatial import cKDTree
    d = np.full(c.n_positions, np.nan)
    for t, sl in c.slices.items():
        own = np.zeros(c.n_positions, bool)
        own[sl] = True
        other = ~own & c.has_point
        tree = cKDTree(c.points[other])
        q = own & c.has_point
        d[q] = tree.query(c.points[q])[0]
    per_tract = pd.Series({t: np.nanmedian(d[sl]) for t, sl in c.slices.items()})
    return d, per_tract


def main():
    mac = ""
    bcp, bage = load(C.BCP_DIR)
    hbcd, hage = load(C.HBCD_DIR, C.HBCD_AGES)
    rows = []
    for c, ages, name in ((bcp, bage, "BCP"), (hbcd, hage, "HBCD")):
        b, _ = basic(c, ages, name)
        rows.append(b)
        pd.DataFrame({"scan": c.scans, "age": ages}).to_csv(C.CACHE + "/desc_ages_{}.csv".format(name), index=False)
    D = pd.DataFrame(rows)
    D.to_csv(C.CACHE + "/desc_basic.csv", index=False)
    print(D.T.to_string())
    b, h = rows
    for key, val in b.items():
        if key in ("name", "acq"):
            continue
        tag = key.replace("0-3m", "A").replace("4-9m", "B").replace("10-60m", "C").replace("q1", "QOne")
        tag = tag.replace("q3", "QThree").replace("subj_1", "subjOne").replace("2plus", "TwoPlus")
        tag = re.sub(r"[^A-Za-z]", "", tag)
        mac += C.macro("bcp" + tag, "{:g}".format(round(val, 1)) if isinstance(val, float) else "{:,}".format(val))
        hv = h[key]
        mac += C.macro("hbcd" + tag, "{:g}".format(round(hv, 1)) if isinstance(hv, float) else "{:,}".format(hv))
    acq = b["acq"]
    for i, (k, v) in enumerate(sorted(acq.items(), key=lambda x: -x[1])):
        mac += C.macro("bcpAcq" + "ABC"[i] + "Name", k.replace("_", r"\_"))
        mac += C.macro("bcpAcq" + "ABC"[i] + "N", str(v))

    # missingness of the real profiles (BCP)
    M = missingness(bcp)
    M.to_csv(C.CACHE + "/desc_missing_BCP.csv", index=False)
    cells = int(sum(bcp.valid[:, m].sum() for m in range(len(bcp.metrics))) * len(bcp.scans))
    nmiss = int(sum(np.isnan(bcp.values[:, bcp.valid[:, m], m]).sum() for m in range(len(bcp.metrics))))
    whole = M[M.kind == "whole"]
    part = M[M.kind == "partial"]
    n_prof = len(bcp.scans) * sum(1 for t, sl in bcp.slices.items() for m in range(len(bcp.metrics))
                                  if bcp.valid[sl, m].any())
    # whole profiles missing in all metrics of a tract (a rejected tract) vs in some metrics
    wt = whole.groupby(["scan", "tract"]).metric.nunique()
    nm = len(bcp.metrics)
    # scans missing more than half of their tracts (not imputed, not validated)
    tract_missing = whole[whole.metric == bcp.metrics[0]].groupby("scan").size()
    pm = part.copy()
    pm["ends"] = (pm.start > 0) | (pm.end > 0)
    pm["inner"] = pm.interior > 0
    mac += C.macro("missCellShare", "{:.2f}".format(100.0 * nmiss / cells))
    mac += C.macro("missCells", "{:,}".format(nmiss))
    mac += C.macro("allCells", "{:,}".format(cells))
    mac += C.macro("missWholeN", "{:,}".format(len(whole)))
    mac += C.macro("missProfilesN", "{:,}".format(n_prof))
    mac += C.macro("missWholeShare", "{:.2f}".format(100.0 * len(whole) / n_prof))
    mac += C.macro("missWholeCellShare", "{:.1f}".format(100.0 * whole.n_missing.sum() / nmiss))
    mac += C.macro("missRejectedTracts", "{:,}".format(int((wt == nm).sum())))
    mac += C.macro("missTractPartialMetrics", "{:,}".format(int((wt < nm).sum())))
    mac += C.macro("missPartialN", "{:,}".format(len(part)))
    mac += C.macro("missPartialEnds", "{:,}".format(int(pm.ends.sum())))
    mac += C.macro("missPartialInner", "{:,}".format(int(pm.inner.sum())))
    endlen = np.concatenate([pm.start[pm.start > 0], pm.end[pm.end > 0]])
    mac += C.macro("missEndLenMedian", "{:g}".format(np.median(endlen)) if len(endlen) else "--")
    mac += C.macro("missEndLenMax", "{:g}".format(np.max(endlen)) if len(endlen) else "--")
    mac += C.macro("missScansAny", "{:,}".format(M.scan.nunique()))
    mac += C.macro("missScansHalf", "{:,}".format(int((tract_missing > 0.5 * len(bcp.tracts)).sum())))
    # families missing entirely in a scan
    fam_missing = {}
    for f, ms in C.FAM.items():
        idx = [bcp.metrics.index(m) for m in ms if m in bcp.metrics]
        fam_missing[f] = int(np.sum([np.isnan(bcp.values[s][:, idx][bcp.valid[:, idx]]).all()
                                     for s in range(len(bcp.scans))]))
        mac += C.macro("missFamily" + f.capitalize(), str(fam_missing[f]))
    # per tract: share of scans with the whole profile missing (all metrics)
    rej = whole.groupby(["scan", "tract"]).metric.nunique().reset_index()
    rej = rej[rej.metric == nm].groupby("tract").size().reindex(bcp.tracts, fill_value=0) / len(bcp.scans)
    rej.rename("share").to_csv(C.CACHE + "/desc_rejected_by_tract.csv")
    mac += C.macro("missTractMax", "{:.1f}".format(100 * rej.max()))
    mac += C.macro("missTractMaxName", rej.idxmax().replace("_", r"\_"))
    mac += C.macro("missTractMedian", "{:.1f}".format(100 * rej.median()))
    # axis proximity
    d, per_tract = axis_proximity(bcp)
    per_tract.rename("median_mm").to_csv(C.CACHE + "/desc_axis_proximity.csv")
    mac += C.macro("axisTractMedian", "{:.1f}".format(per_tract.median()))
    mac += C.macro("axisWithinTwo", "{:.0f}".format(100 * np.nanmean(d <= 2.0)))
    mac += C.macro("axisWithinFour", "{:.0f}".format(100 * np.nanmean(d <= 4.0)))

    # missingness of both cohorts (round-2 review, N1b): cells missing, rejected tracts (no observed value of any
    # measure, the rule of --max-missing-tracts) per scan
    miss = {}
    for c, name in ((bcp, "bcp"), (hbcd, "hbcd")):
        ncell = int(sum(c.valid[:, m].sum() for m in range(len(c.metrics))) * len(c.scans))
        nmis = int(sum(np.isnan(c.values[:, c.valid[:, m], m]).sum() for m in range(len(c.metrics))))
        rt = np.array([ip.missing_tracts(c, c.values[s], s) for s in range(len(c.scans))])
        aff = rt[:, 0] > 0
        miss[name] = dict(cells=100.0 * nmis / ncell, aff=int(aff.sum()), affs=100.0 * aff.mean(),
                          med=float(np.median(rt[aff, 0])), mean=float(rt[aff, 0].mean()),
                          half=int((rt[:, 0] > 0.5 * rt[:, 1]).sum()))
        pd.DataFrame({"scan": c.scans, "missing_tracts": rt[:, 0], "tracts": rt[:, 1]}).to_csv(
            C.CACHE + "/desc_rejected_tracts_{}.csv".format(name.upper()), index=False)
        for k, v in miss[name].items():
            mac += C.macro(name + "Miss" + k.capitalize(), "{:g}".format(v) if k == "med" else
                           ("{:.1f}".format(v) if isinstance(v, float) else "{:,}".format(v)))
    C.write_tex("descriptives_macros.tex", mac)
    mb, mh = miss["bcp"], miss["hbcd"]

    # data table
    def bins_row(r, key):
        return " & ".join("{:,}".format(r[key + lab]) for lab in ("0-3m", "4-9m", "10-60m"))
    tex = [r"\begin{tabular}{lrr}", r"\toprule", r" & BCP & HBCD \\", r"\midrule",
           r"Scans & {:,} & {:,} \\".format(b["scans"], h["scans"]),
           r"Subjects & {:,} & {:,} \\".format(b["subjects"], h["subjects"]),
           r"Subjects with $\geq 2$ scans & {:,} & {:,} \\".format(b["subj_2plus"], h["subj_2plus"]),
           r"Scans per subject, median (max) & {:g} ({}) & {:g} ({}) \\".format(b["sess_median"], b["sess_max"],
                                                                                h["sess_median"], h["sess_max"]),
           r"Age, months: median [IQR] & {:.1f} [{:.1f}, {:.1f}] & {:.1f} [{:.1f}, {:.1f}] \\".format(
               b["age_median"], b["age_q1"], b["age_q3"], h["age_median"], h["age_q1"], h["age_q3"]),
           r"Age range, months & {:.1f}--{:.1f} & {:.1f}--{:.1f} \\".format(b["age_min"], b["age_max"],
                                                                          h["age_min"], h["age_max"]),
           r"Scans aged 0--3 / 4--9 / 10--60 mo & {} & {} \\".format(bins_row(b, "bin_").replace(" & ", " / "),
                                                                     bins_row(h, "bin_").replace(" & ", " / ")),
           r"Scans outside the age bins & {:,} & {:,} \\".format(b["bin_none"], h["bin_none"]),
           r"Tracts / profile locations & {} / {:,} & {} / {:,} \\".format(b["tracts"], b["positions"],
                                                                          h["tracts"], h["positions"]),
           r"Measures & {} & {} \\".format(b["metrics"], h["metrics"]),
           r"\midrule",
           r"Cells missing after QC (\%) & {:.1f} & {:.1f} \\".format(mb["cells"], mh["cells"]),
           r"Scans with $\geq 1$ rejected tract & {:,} ({:.0f}\%) & {:,} ({:.0f}\%) \\".format(
               mb["aff"], mb["affs"], mh["aff"], mh["affs"]),
           r"Rejected tracts per affected scan, median (mean) & {:g} ({:.1f}) & {:g} ({:.1f}) \\".format(
               mb["med"], mb["mean"], mh["med"], mh["mean"]),
           r"Scans missing $>50\%$ of their tracts & {:,} & {:,} \\".format(mb["half"], mh["half"]),
           r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_data.tex", "\n".join(tex) + "\n")
    print(mac)


if __name__ == "__main__":
    main()
