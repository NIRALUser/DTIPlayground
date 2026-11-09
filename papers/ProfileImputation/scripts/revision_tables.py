"""Tables and numbers added in revision 1 (review_r1.md): realistic weighting and pattern-specific contrasts (M2/E2
fallback), per-tract results (O6), missingness load (O7), the kernel-norm reference and absolute RMSEs (M3/E6),
calibration of the released default (M8/E7), cohort-level baselines (M6/E8), pooling per age bin (M4/E5),
supplementary tables for claims previously supported by the documentation only (M7), the tuning budget (M6), and the
acquisition x age-bin table (minor 17). Run after make_tables.py, dump_analysis.py, baselines.py and batch_check.py.
Writes tables/rev_*.tex and tables/macros_rev.tex."""
import glob
import os
import pickle
import re

import numpy as np
import pandas as pd
from scipy import stats

import common as C

MAC = []
FOUR = C.PATS


def mac(name, value):
    MAC.append(C.macro(name, value))


def f3(x):
    return "--" if x is None or not np.isfinite(x) else "{:.3f}".format(x)


def write(name, lines):
    C.write_tex(name, "\n".join(lines) + "\n")


DS = pd.read_csv(C.CACHE + "/dump_bcp_scans.csv")
DR = pd.read_csv(C.CACHE + "/dump_bcp_results.csv")
DCELLS = pd.read_csv(C.CACHE + "/dump_bcp_cells.csv")
DCELLS["metric"] = [C.METRICS[int(m)] for m in DCELLS.metric]
DUMP = {"D default": "PPCA + SIREN", "D transformer": "transformer", "D fixed": "fixed 0.25/0.75",
        "D table shipped": "table (shipped)", "D released": "table (cross-fitted)",
        "D ref transformer": "reference transformer", "D ref fixed": "reference fixed 0.25/0.75",
        "D ref table": "reference table (cross-fitted)", "D ref table shipped": "reference table (shipped)",
        "D mean transformers": "mean of both transformers, fixed"}


def scans(label, pattern="4pat"):
    if label in DUMP:
        d = DS[(DS.setting == DUMP[label]) & (DS.group == pattern)]
        return d[["scan", "seed", "r"]].copy()
    if label.startswith("B "):
        b = pd.read_csv(C.CACHE + "/baselines_bcp_scans.csv")
        d = b[(b.setting == label[2:]) & (b.group == pattern)]
        return d[["scan", "seed", "r"]].copy()
    pats = C.PATS if pattern == "4pat" else [pattern]
    return C.scan_scores(label, patterns=pats)


def summ(label):
    if label in DUMP:
        return DR[DR.setting == DUMP[label]].mean(numeric_only=True)
    return C.summary(label).mean(numeric_only=True)


# ----------------------------------------------------------------------------------------------------------------
def real_weights():
    """Share of the real missing cells (BCP after QC) per pattern."""
    M = pd.read_csv(C.CACHE + "/desc_missing_BCP.csv")
    whole = M[M.kind == "whole"].n_missing.sum()
    part = M[M.kind == "partial"]
    ends = (part.start + part.end).sum()
    inner = part.interior.sum()
    tot = whole + ends + inner
    w = {"whole profile": whole / tot, "end gap": ends / tot, "gap": inner / tot}
    mac("realShareWhole", "{:.1f}".format(100 * w["whole profile"]))
    mac("realShareEnd", "{:.2f}".format(100 * w["end gap"]))
    mac("realShareGap", "{:.2f}".format(100 * w["gap"]))
    # rejected tracts per scan (scans with rejections)
    rej = M[(M.kind == "whole")].groupby(["scan", "tract"]).size().groupby("scan").size()
    mac("rejMedian", "{:g}".format(rej.median()))
    mac("rejQThree", "{:g}".format(rej.quantile(0.75)))
    mac("rejPNinetyFive", "{:g}".format(rej.quantile(0.95)))
    mac("rejMax", "{:g}".format(rej.max()))
    mac("rejTenPlus", "{:d}".format(int((rej >= 10).sum())))
    mac("rejScans", "{:d}".format(len(rej)))
    return w


PATTERN_CONTRASTS = [
    ("PPCA + kNN vs PPCA + SIREN", "P3 PPCA + SIREN", "P3 PPCA q=80 + kNN"),
    ("PPCA alone vs PPCA + SIREN", "P3 PPCA + SIREN", "P3 PPCA q=80"),
    ("Transformer (400) vs PPCA + SIREN", "P3 PPCA + SIREN", "D transformer"),
    ("U-Net vs PPCA + SIREN", "P3 PPCA + SIREN", "P4 U-Net (deviations+PPCA)"),
    ("Released default vs PPCA + SIREN", "P3 PPCA + SIREN", "D released"),
    ("Released default vs PPCA + kNN", "P3 PPCA q=80 + kNN", "D released"),
    ("Released default vs PPCA alone", "P3 PPCA q=80", "D released"),
    ("HBCD-reference blend vs released default", "D released", "D ref table"),
]


def table_patterns():
    rows = []
    for desc, a, b in PATTERN_CONTRASTS:
        for p in ["whole profile", "region", "gap", "end gap"]:
            r = C.paired(scans(a, p), scans(b, p))
            rows.append(dict(contrast=desc, pattern=p, **r))
    R = pd.DataFrame(rows)
    R["p_holm"] = C.holm(R.p_subj)
    R.to_csv(C.CACHE + "/rev_pattern_contrasts.csv", index=False)
    lines = [r"\begin{tabular}{lcccc}", r"\toprule",
             r"Contrast (compared vs reference) & Whole profile & Region & Interior gap & End gap \\", r"\midrule"]
    for desc, _, _ in PATTERN_CONTRASTS:
        cells = []
        for p in ["whole profile", "region", "gap", "end gap"]:
            r = R[(R.contrast == desc) & (R.pattern == p)].iloc[0]
            cells.append(r"{:.3f} [{:.3f}, {:.3f}]".format(r.ratio, r.blo, r.bhi))
        lines.append(desc + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_patterns.tex", lines)
    for i, (desc, _, _) in enumerate(PATTERN_CONTRASTS):
        for p, t in [("whole profile", "Whole"), ("region", "Region"), ("gap", "Gap"), ("end gap", "End")]:
            r = R[(R.contrast == desc) & (R.pattern == p)].iloc[0]
            tag = "pc" + "ABCDEFGH"[i] + t
            mac(tag, "{:.3f}".format(r.ratio))
            mac(tag + "Ci", "{:.3f}--{:.3f}".format(r.blo, r.bhi))
            mac(tag + "Better", "{:.0f}".format(100 * r.better))
    return R


def table_main_rev(w):
    """Main settings: whole-profile-led view, real-frequency weighted score, kernel-norm reference, absolute RMSE."""
    M = pd.read_csv(C.CACHE + "/main_table.csv").set_index("label")
    rows = [("Age-bin mean", "age-bin mean"), ("Kernel age norm (alone)", "K"),
            ("Phase 2: SIREN on deviations", "P2 SIREN xyz"),
            ("PPCA alone", "P3 PPCA q=80"), ("PPCA + kNN", "P3 PPCA q=80 + kNN"), ("PPCA + SIREN", "P3 PPCA + SIREN"),
            ("Graph U-Net alone", "P4 U-Net (deviations+PPCA)"), ("Transformer alone (400)", "P6 transformer (400 ep.)"),
            ("Blend, fixed (400)", "P6 transformer 400 blend 0.25/0.75"),
            ("Released default (table)", "D table blend (released default)"),
            ("HBCD-trained transformer, table", "D reference table blend")]
    # kernel-norm RMSE per (seed, pattern, metric, age bin) from the dumps (same hidden cells as every run)
    kc = DCELLS[DCELLS.setting == "PPCA + SIREN"].groupby(["seed", "pattern", "metric", "age_bin"])[["k2", "r2", "n"]].sum()
    krmse = np.sqrt(kc.k2 / kc.n)
    armse = np.sqrt(kc.r2 / kc.n)
    lab2dump = {"D table blend (released default)": "table (cross-fitted)",
                "D reference table blend": "reference table (cross-fitted)"}
    out = []
    for name, lab in rows:
        if lab == "K":
            q = np.sqrt(kc.k2 / kc.n).rename("rmse").reset_index()
        elif lab in lab2dump:
            x = DCELLS[DCELLS.setting == lab2dump[lab]].groupby(["seed", "pattern", "metric", "age_bin"])[["e2", "n"]].sum()
            q = np.sqrt(x.e2 / x.n).rename("rmse").reset_index()
        else:
            run, st, _ = C.S[lab]
            parts = []
            for s in C.SEEDS:
                d = C.read(run, s, "validation_by_age_bin.csv")
                d = d[d.setting == st][["pattern", "metric", "age_bin", "rmse_completed"]].assign(seed=s)
                parts.append(d.rename(columns={"rmse_completed": "rmse"}))
            q = pd.concat(parts)
        q = q.set_index(["seed", "pattern", "metric", "age_bin"]).rmse
        rk = (q / krmse).dropna().reset_index().rename(columns={0: "r"})
        ra = (q / armse).dropna().reset_index().rename(columns={0: "r"})
        rk.columns = list(rk.columns[:-1]) + ["r"]
        ra.columns = list(ra.columns[:-1]) + ["r"]

        def pat(df, p):
            return df[df.pattern == p].groupby("seed").r.mean().mean()
        k4 = rk[rk.pattern.isin(FOUR)].groupby("seed").r.mean().mean()
        pw = {p: pat(ra, p) for p in ["whole profile", "end gap", "gap"]}
        realw = sum(w[p] * pw[p] for p in pw)
        absq = q.reset_index()
        absq = absq[absq.pattern.isin(FOUR)].groupby(["seed", "metric"]).rmse.mean().groupby("metric").mean()
        out.append(dict(setting=name, label=lab, whole=pw["whole profile"], region=pat(ra, "region"),
                        real=realw, k_overall=k4, k_whole=pat(rk, "whole profile"), k_region=pat(rk, "region"),
                        **{"abs_" + m: absq.get(m, np.nan) for m in C.METRICS}))
    R = pd.DataFrame(out)
    R.to_csv(C.CACHE + "/rev_main.csv", index=False)
    lines = [r"\begin{tabular}{lccccccc}", r"\toprule",
             r" & \multicolumn{3}{c}{vs age-bin mean} & \multicolumn{3}{c}{vs kernel age norm} \\",
             r"\cmidrule(lr){2-4}\cmidrule(lr){5-7}",
             r"Setting & Whole & Region & Real-weighted & Overall & Whole & Region \\", r"\midrule"]
    for _, r in R.iterrows():
        lines.append(r"{} & {} & {} & {} & {} & {} & {} \\".format(r.setting, f3(r.whole), f3(r.region), f3(r.real),
                                                                   f3(r.k_overall), f3(r.k_whole), f3(r.k_region)))
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_main.tex", lines)
    scale = {"fa": 1e3, "NDI": 1e3, "ODI": 1e3, "FWF": 1e3, "md": 1e6, "rd": 1e6, "ad": 1e6}
    lines = [r"\begin{tabular}{l" + "c" * 7 + "}", r"\toprule",
             "Setting & " + " & ".join(C.MLABEL[m] for m in C.METRICS) + r" \\", r"\midrule"]
    for _, r in R.iterrows():
        lines.append(r.setting + " & " + " & ".join("{:.1f}".format(r["abs_" + m] * scale[m]) for m in C.METRICS)
                     + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_absolute_all.tex", lines)
    R = R.set_index("label")
    for tag, lab in [("AgeMean", "age-bin mean"), ("Kernel", "K"), ("Ppca", "P3 PPCA q=80"),
                     ("PpcaKnn", "P3 PPCA q=80 + kNN"), ("Default", "P3 PPCA + SIREN"),
                     ("Final", "D table blend (released default)"), ("RefFinal", "D reference table blend"),
                     ("TfFour", "P6 transformer (400 ep.)"), ("Unet", "P4 U-Net (deviations+PPCA)"),
                     ("PtwoSiren", "P2 SIREN xyz")]:
        mac("k" + tag + "Overall", f3(R.loc[lab, "k_overall"]))
        mac("k" + tag + "Whole", f3(R.loc[lab, "k_whole"]))
        mac("rw" + tag, f3(R.loc[lab, "real"]))
    return R


def table_cap():
    """The distance limit under the current protocol: SIREN (or kNN) residuals up to 2 or 4 mm, PPCA beyond, from
    the per-distance sums of the same cells (normalized squared errors pooled over age bins; mean over measures)."""
    parts = [C.read("v13/P3", s, "validation_by_distance.csv") for s in C.SEEDS]
    d = pd.concat(parts)
    d = d[d.metric != "all"]
    g = d.groupby(["setting", "pattern", "metric", "distance_mm"])[["nsse_paired_age", "nsse_age_mean"]].sum()
    out = []
    near = {"0": [], "2": ["0-2"], "4": ["0-2", "2-4"]}
    for loc, lst in [("SIREN", C.DEF), ("kNN", C.POP + " + knn k=20")]:
        for cap, bins in near.items():
            for p in FOUR:
                vals = []
                for m in C.METRICS:
                    a = g.loc[(lst, p, m)]
                    b = g.loc[(C.POP, p, m)]
                    num = sum(a.loc[x, "nsse_paired_age"] if x in bins else b.loc[x, "nsse_paired_age"]
                              for x in b.index)
                    den = b.nsse_age_mean.sum()
                    vals.append(np.sqrt(num / den))
                out.append(dict(local=loc, cap=cap, pattern=p, r=np.mean(vals)))
    R = pd.DataFrame(out).pivot_table(index=["local", "cap"], columns="pattern", values="r")[FOUR]
    R["overall"] = R.mean(axis=1)
    R.to_csv(C.CACHE + "/rev_cap.csv")
    lines = [r"\begin{tabular}{llccccc}", r"\toprule",
             r"Local method & Limit & Gap & End & Whole & Region & Overall \\", r"\midrule"]
    for (loc, cap), r in R.iterrows():
        lines.append(r"{} & {} & {} \\".format(loc if cap == "0" else "", "PPCA only" if cap == "0" else cap + " mm",
                                              " & ".join(f3(r[c]) for c in FOUR + ["overall"])))
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_cap.tex", lines)
    for loc in ("SIREN", "kNN"):
        for cap in ("2", "4"):
            for p, t in [("whole profile", "Whole"), ("region", "Region"), ("gap", "Gap"), ("overall", "All")]:
                mac("cap" + loc.replace("SIREN", "Siren").replace("kNN", "Knn") + ("Two" if cap == "2" else "Four") + t,
                    f3(R.loc[(loc, cap), p]))
    for p, t in [("whole profile", "Whole"), ("region", "Region"), ("gap", "Gap"), ("overall", "All")]:
        mac("capPpca" + t, f3(R.loc[("SIREN", "0"), p]))
    return R


def table_tracts():
    """Whole profiles per tract: the released default (dumps), weighted by the real rejection rate (E2 fallback, O6)."""
    T = pd.read_csv(C.CACHE + "/dump_bcp_tracts.csv")
    T = T[T.pattern == "whole profile"]
    rej = pd.read_csv(C.CACHE + "/desc_rejected_by_tract.csv", index_col=0).share
    prox = pd.read_csv(C.CACHE + "/desc_axis_proximity.csv", index_col=0).median_mm
    out = {}
    for lab in ["PPCA + SIREN", "transformer", "table (cross-fitted)"]:
        x = T[T.setting == lab].groupby(["tract", "metric"])[["e2", "r2"]].sum()
        r = np.sqrt(x.e2 / x.r2).groupby("tract").mean()
        out[lab] = r
    D = pd.DataFrame(out)
    D["rejection"] = rej
    D["proximity"] = prox
    D.to_csv(C.CACHE + "/rev_tracts.csv")
    w = D.rejection / D.rejection.sum()
    for lab, tag in [("PPCA + SIREN", "Default"), ("table (cross-fitted)", "Final")]:
        mac("trW" + tag, f3((D[lab] * w).sum()))
        mac("trU" + tag, f3(D[lab].mean()))
    rho, p = stats.spearmanr(D["table (cross-fitted)"], D.rejection)
    mac("trRhoRej", "{:.2f}".format(rho))
    mac("trRhoRejP", "{:.2f}".format(p))
    rho, p = stats.spearmanr(D["table (cross-fitted)"], D.proximity)
    mac("trRhoProx", "{:.2f}".format(rho))
    mac("trRhoProxP", C.fmt_p(p))
    x = D["table (cross-fitted)"].sort_values()
    mac("trBest", f3(x.iloc[0]))
    mac("trBestName", x.index[0].replace("_", r"\_"))
    mac("trWorst", f3(x.iloc[-1]))
    mac("trWorstName", x.index[-1].replace("_", r"\_"))
    mac("trAboveOne", str(int((x > 1).sum())))
    mac("trAboveEight", str(int((x > 0.8).sum())))
    rho, p = stats.spearmanr(rej.reindex(prox.index), prox)
    mac("rejProxRho", "{:.2f}".format(rho))
    mac("rejProxP", "{:.2f}".format(p))
    return D


def table_load():
    L = pd.read_csv(C.CACHE + "/dump_bcp_load.csv")
    L["grp"] = pd.cut(L["load"], [0, 5, 10, 15, 20, 70], labels=["1-5", "6-10", "11-15", "16-20", ">20"])
    out = {}
    for lab in ["PPCA + SIREN", "transformer", "table (cross-fitted)"]:
        x = L[L.setting == lab].groupby(["grp", "metric", "age_bin"], observed=True)[["e2", "r2", "n"]].sum()
        r = np.sqrt(x.e2 / x.r2).groupby("grp", observed=True).mean()
        out[lab] = r
        out["n"] = x.n.groupby("grp", observed=True).sum()
    R = pd.DataFrame(out)
    R.to_csv(C.CACHE + "/rev_load.csv")
    for g, t in [("1-5", "A"), ("6-10", "B"), ("11-15", "C"), ("16-20", "D"), (">20", "E")]:
        if g in R.index:
            mac("loadFinal" + t, f3(R.loc[g, "table (cross-fitted)"]))
            mac("loadDefault" + t, f3(R.loc[g, "PPCA + SIREN"]))
    return R


def table_calib():
    K = pd.read_csv(C.CACHE + "/dump_bcp_calib.csv")
    bandlab = ["0-0.5", "0.5-1", "1-2", "2-3", "3-4", "4-6", "6-10", "10-20", ">20", "none"]
    sets = [("PPCA + SIREN", "PPCA + SIREN"), ("Transformer (400)", "transformer"),
            ("Released default (table)", "table (cross-fitted)"), ("Table, shipped weights", "table (shipped)"),
            ("HBCD-reference table blend", "reference table (cross-fitted)")]
    rows = []
    for name, lab in sets:
        x = K[K.setting == lab]
        for p in FOUR + ["whole measure"]:
            y = x[x.pattern == p].groupby("metric")[["n", "z2", "within"]].sum()
            rows.append(dict(setting=name, group=p, rms=np.mean(np.sqrt(y.z2 / y.n)), cov=np.mean(y.within / y.n)))
        for b in range(10):
            y = x[(x.band == b) & x.pattern.isin(FOUR + ["whole measure"])].groupby("metric")[["n", "z2", "within"]].sum()
            if y.n.sum() > 0:
                rows.append(dict(setting=name, group="band " + bandlab[b], rms=np.mean(np.sqrt(y.z2 / y.n)),
                                 cov=np.mean(y.within / y.n)))
    R = pd.DataFrame(rows)
    R.to_csv(C.CACHE + "/rev_calib.csv", index=False)
    groups = FOUR + ["whole measure"]
    lines = [r"\begin{tabular}{l" + "c" * 5 + "}", r"\toprule",
             r"Setting & Gap & End & Whole & Region & Family \\", r"\midrule"]
    for name, _ in sets:
        cells = []
        for g in groups:
            r = R[(R.setting == name) & (R.group == g)].iloc[0]
            cells.append("{:.2f} / {:.0f}\\%".format(r.rms, 100 * r["cov"]))
        lines.append(name + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_calib.tex", lines)
    lines = [r"\begin{tabular}{l" + "c" * 10 + "}", r"\toprule",
             r"Setting & " + " & ".join(b.replace(">", "$>$") for b in bandlab) + r" \\", r"\midrule"]
    for name, _ in sets[:3] + sets[4:]:
        cells = []
        for b in bandlab:
            r = R[(R.setting == name) & (R.group == "band " + b)]
            cells.append("--" if r.empty else "{:.2f}".format(r.iloc[0].rms))
        lines.append(name + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_calib_band.tex", lines)
    rr = R.set_index(["setting", "group"])
    for g, t in [("gap", "Gap"), ("end gap", "End"), ("whole profile", "Whole"), ("region", "Region"),
                 ("whole measure", "Family"), ("band 0-0.5", "Near"), ("band 4-6", "Far")]:
        mac("calFinal" + t + "Rms", "{:.2f}".format(rr.loc[("Released default (table)", g), "rms"]))
        mac("calFinal" + t + "Cov", "{:.0f}".format(100 * rr.loc[("Released default (table)", g), "cov"]))
        mac("calRef" + t + "Rms", "{:.2f}".format(rr.loc[("HBCD-reference table blend", g), "rms"]))
    return R


def table_baselines():
    f = C.CACHE + "/baselines_bcp_results.csv"
    if not os.path.isfile(f) or pd.read_csv(f).seed.nunique() < 3:
        print("baselines not available yet")
        for k in ["blOffMeasure", "blOffMeasureWhole", "blOffNear", "blOffNearWhole", "blKnnBest", "blKnnBestName",
                  "blKnnBestWhole", "blSvdBest", "blSvdBestName", "blSvdBestWhole", "blSvdBestWdti", "blMice",
                  "blMiceWhole", "blMiceWdti", "blMiceWnoddi"] + ["bl" + t + "PairWhole" + c for t in
                                                                  ("Svd", "Off", "Knn", "Mice") for c in ("", "Ci")]:
            mac(k, r"\pending{}")
        write("rev_baselines.tex", [r"\begin{tabular}{l}", r"\pending{baselines running} \\", r"\end{tabular}"])
        return None
    B = pd.read_csv(f)
    m = B.groupby("setting").mean(numeric_only=True)
    sd = B.groupby("setting").overall.std()
    order = ["offset (measure)", "offset (5 tracts)"] + ["kNN across scans, k={}".format(k) for k in (5, 10, 20, 50)] + \
        ["iterative SVD, rank {}".format(r) for r in (10, 40, 80, 160)] + ["MICE (tract means)"]
    refs = [("PPCA alone", "P3 PPCA q=80"), ("PPCA + kNN", "P3 PPCA q=80 + kNN"), ("PPCA + SIREN", "P3 PPCA + SIREN")]
    cols = ["overall", "gap", "end gap", "whole profile", "region", "whole dti", "whole noddi"]
    lines = [r"\begin{tabular}{lcccccccc}", r"\toprule",
             r"Setting & Overall (SD) & Gap & End & Whole & Region & Tensor & NODDI & Whole: paired vs PPCA \\",
             r"\midrule"]
    ppca_whole = scans("P3 PPCA q=80", "whole profile")
    for s in order:
        if s not in m.index:
            continue
        r = m.loc[s]
        p = C.paired(ppca_whole, scans("B " + s, "whole profile"))
        lines.append(r"{} & {:.3f} ({:.3f}) & {} & {:.3f} [{:.3f}, {:.3f}] \\".format(
            s, r.overall, sd[s], " & ".join(f3(r[c]) for c in cols[1:]), p["ratio"], p["blo"], p["bhi"]))
    lines.append(r"\midrule")
    for name, lab in refs:
        r = C.summary(lab).mean(numeric_only=True)
        sdv = C.summary(lab).overall.std()
        lines.append(r"{} & {:.3f} ({:.3f}) & {} & -- \\".format(name, r.overall, sdv,
                                                                " & ".join(f3(r[c]) for c in cols[1:])))
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_baselines.tex", lines)
    best_knn = m.loc[[s for s in m.index if s.startswith("kNN")]].overall.idxmin()
    best_svd = m.loc[[s for s in m.index if s.startswith("iterative")]].overall.idxmin()
    mac("blOffMeasure", f3(m.loc["offset (measure)", "overall"]))
    mac("blOffMeasureWhole", f3(m.loc["offset (measure)", "whole profile"]))
    mac("blOffNear", f3(m.loc["offset (5 tracts)", "overall"]))
    mac("blOffNearWhole", f3(m.loc["offset (5 tracts)", "whole profile"]))
    mac("blKnnBest", f3(m.loc[best_knn, "overall"]))
    mac("blKnnBestName", best_knn.split("=")[1])
    mac("blKnnBestWhole", f3(m.loc[best_knn, "whole profile"]))
    mac("blSvdBest", f3(m.loc[best_svd, "overall"]))
    mac("blSvdBestName", best_svd.split("rank ")[1])
    mac("blSvdBestWhole", f3(m.loc[best_svd, "whole profile"]))
    mac("blSvdBestWdti", f3(m.loc[best_svd, "whole dti"]))
    pw = C.summary("P3 PPCA q=80")["whole profile"].mean()
    mac("blOffShare", "{:.0f}".format(100 * (1 - m.loc["offset (measure)", "whole profile"]) / (1 - pw)))
    mac("blMice", f3(m.loc["MICE (tract means)", "overall"]))
    mac("blMiceWhole", f3(m.loc["MICE (tract means)", "whole profile"]))
    mac("blMiceWdti", f3(m.loc["MICE (tract means)", "whole dti"]))
    mac("blMiceWnoddi", f3(m.loc["MICE (tract means)", "whole noddi"]))
    for s, t in [(best_svd, "Svd"), ("offset (measure)", "Off"), (best_knn, "Knn"), ("MICE (tract means)", "Mice")]:
        p = C.paired(ppca_whole, scans("B " + s, "whole profile"))
        mac("bl" + t + "PairWhole", "{:.3f}".format(p["ratio"]))
        mac("bl" + t + "PairWholeCi", "{:.3f}--{:.3f}".format(p["blo"], p["bhi"]))
    return m


def table_pooling_bins():
    """E5 per age bin, from v15 (seeds 0-2): pooled vs BCP-only, pooled blend vs released default and reference
    blend, and the reference transformer vs the BCP transformer at equal epochs (200)."""
    comps = [("Pooled PPCA + SIREN vs BCP PPCA + SIREN", "P6 default (E check)", "P6 pooled: PPCA + SIREN"),
             ("Pooled fixed blend vs released default", "D released", "P6 pooled: blend 0.25/0.75"),
             ("Pooled fixed blend vs HBCD-reference fixed blend", "D ref fixed", "P6 pooled: blend 0.25/0.75"),
             ("HBCD-reference transformer vs BCP transformer (both 200 ep.)", "P6 transformer (200 ep.)",
              "D ref transformer"),
             ("HBCD-reference fixed blend vs BCP fixed blend (both 200 ep.)", "P6 transformer blend 0.25/0.75",
              "D ref fixed"),
             ("Mean of BCP and reference transformers vs BCP (fixed, 400 ep.)", "D fixed", "D mean transformers")]
    groups = {}
    g = C.scan_scores("P3 PPCA + SIREN")[["scan", "seed", "group"]]
    rows = []
    for desc, a, b in comps:
        A, B = scans(a)[["scan", "seed", "r"]], scans(b)[["scan", "seed", "r"]]
        A = A.merge(g, on=["scan", "seed"], how="left")
        for bn in ["all"] + C.BINS:
            Ab = A if bn == "all" else A[A.group == bn]
            r = C.paired(Ab[["scan", "seed", "r"]], B)
            rows.append(dict(contrast=desc, bin=bn, **r))
    R = pd.DataFrame(rows)
    R.to_csv(C.CACHE + "/rev_pool_bins.csv", index=False)
    lines = [r"\begin{tabular}{lcccc}", r"\toprule",
             r"Contrast (compared vs reference) & All & 0--3 mo & 4--9 mo & 10--60 mo \\", r"\midrule"]
    for desc, _, _ in comps:
        cells = []
        for bn in ["all"] + C.BINS:
            r = R[(R.contrast == desc) & (R.bin == bn)].iloc[0]
            cells.append("{:.3f} [{:.3f}, {:.3f}]".format(r.ratio, r.blo, r.bhi))
        lines.append(desc + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_pool_bins.tex", lines)
    for i, (desc, _, _) in enumerate(comps):
        for bn, t in zip(["all"] + C.BINS, ["All", "A", "B", "C"]):
            r = R[(R.contrast == desc) & (R.bin == bn)].iloc[0]
            mac("pb" + "ABCDEF"[i] + t, "{:.3f}".format(r.ratio))
            mac("pb" + "ABCDEF"[i] + t + "Ci", "{:.3f}--{:.3f}".format(r.blo, r.bhi))
    mac("rMeanTransformers", f3(summ("D mean transformers").overall))
    # batch correction check
    f = C.CACHE + "/batch_check.csv"
    if os.path.isfile(f):
        Bc = pd.read_csv(f)
        piv = Bc.pivot_table(index="window", columns="metric", values="median_dz")
        piv = piv[[m for m in C.METRICS if m in piv.columns]]
        lines = [r"\begin{tabular}{lcc" + "c" * len(piv.columns) + "}", r"\toprule",
                 r"Age window (mo) & $n$ BCP / HBCD & mean age BCP / HBCD & " + " & ".join(
                     C.MLABEL[m] for m in piv.columns) + r" \\", r"\midrule"]
        for wdw in Bc.window.unique():
            x = Bc[Bc.window == wdw].iloc[0]
            lines.append(r"{} & {} / {} & {:.1f} / {:.1f} & {} \\".format(
                wdw, x.n_bcp, x.n_hbcd, x.age_bcp, x.age_hbcd, " & ".join("{:+.2f}".format(v) for v in piv.loc[wdw])))
        lines += [r"\bottomrule", r"\end{tabular}"]
        write("rev_batch_check.tex", lines)
        mac("bcMaxAbs", "{:.2f}".format(np.nanmax(np.abs(piv.to_numpy()))))
    f = C.CACHE + "/batch_age_composition.csv"
    if os.path.isfile(f):
        A = pd.read_csv(f).set_index(["cohort", "bin"])
        for coh in ("BCP", "HBCD"):
            for b, t in zip(C.BINS, "ABC"):
                mac("ageMed" + coh.capitalize() + t, "{:.1f}".format(A.loc[(coh, b), "median"]))
    return R


# ----------------------------------------------------------------------------------------------------------------
# supplementary tables for claims that rested on the documentation

def table_confetti():
    runs = [("CONFETTI configuration: fiber graph, 64 features", "v11/A", "graph-unet L4 h64 x1"),
            ("Fiber graph, 128 features", "v11/A", "graph-unet L4 h128 x1"),
            ("Axis graph, 128 features", "v11/D", "graph-unet L4 h128 x1"),
            ("Axis graph, 256 features", "v11/D", "graph-unet L4 h256 x1"),
            ("Hybrid (corrects PPCA), axis graph, 128 features", "v11/F", "graph-unet on population q=80 L4 h128 x1"),
            ("Hybrid, axis graph, 256 features, 2 convolutions", "v11/E", "graph-unet on population q=80 L4 h256 x2"),
            ("PPCA alone (same run)", "v11/F", C.POP), ("PPCA + SIREN (same run)", "v11/F", C.DEF)]
    lines = [r"\begin{tabular}{lcccccc}", r"\toprule",
             r"Setting (seed 0, 54 scans, 11 measures) & Overall & Gap & End & Whole & Region & Family \\",
             r"\midrule"]
    out = []
    for name, run, st in runs:
        C.S["X11 " + name] = (run, st, None)
        q = C.cell_ratios("X11 " + name, 0)
        q4 = q[q.pattern.isin(FOUR)]
        r = {p: q[q.pattern == p].r.mean() for p in FOUR + ["whole measure"]}
        r["overall"] = q4.r.mean()
        out.append(dict(setting=name, **r))
        lines.append(r"{} & {} \\".format(name, " & ".join(f3(r[c]) for c in ["overall"] + FOUR + ["whole measure"])))
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_confetti.tex", lines)
    R = pd.DataFrame(out).set_index("setting")
    mac("cfOrig", f3(R.iloc[0].overall))
    mac("cfPpca", f3(R.loc["PPCA alone (same run)", "overall"]))
    mac("cfHybrid", f3(R.iloc[4].overall))
    return R


def table_fw():
    """The 11-measure phase-4 runs (v11/H, 3 seeds): per measure, including the free-water tensor measures."""
    rows = []
    for name, st in [("PPCA alone", C.POP), ("PPCA + SIREN", C.DEF),
                     ("PPCA + SIREN, U-Net beyond", C.DEF + ", graph-unet on population q=80 L4 h128 x1 beyond")]:
        C.S["H11 " + name] = ("v11/H", st, None)
        pm = C.per_metric("H11 " + name)
        rows.append(pm.rename(name))
    R = pd.DataFrame(rows)
    order = ["fa", "md", "rd", "ad", "FWFA", "FWMD", "FWRD", "FWAD", "FWF", "NDI", "ODI"]
    order = [m for m in order if m in R.columns]
    lab = {**C.MLABEL, "FWFA": "FW-FA", "FWMD": "FW-MD", "FWRD": "FW-RD", "FWAD": "FW-AD"}
    lines = [r"\begin{tabular}{l" + "c" * len(order) + "}", r"\toprule",
             "Setting & " + " & ".join(lab[m] for m in order) + r" \\", r"\midrule"]
    for name, r in R.iterrows():
        lines.append(name + " & " + " & ".join(f3(r[m]) for m in order) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_fw.tex", lines)
    o = C.summary("H11 PPCA + SIREN").overall.mean()
    mac("fwElevenDefault", f3(o))
    return R


def table_noise():
    d = pd.read_csv(C.REPO + "/docs/_static/impute_validation/phase3/grid_caps_long.csv")
    d = d[d.cap == 4]
    rows = []
    for q in (5, 10, 20, 40, 80):
        r = {"q": q}
        for noise in ("isotropic", "metric", "diagonal"):
            for suf, tag in (("", "alone"), (" + siren xyz omega0=10", "siren")):
                x = d[d.setting == "population q={} {}{}".format(q, noise, suf)]
                r[noise + " " + tag] = x.groupby("pattern").ratio.mean().reindex(FOUR).mean() if len(x) else np.nan
        rows.append(r)
    R = pd.DataFrame(rows)
    lines = [r"\begin{tabular}{rcccccc}", r"\toprule",
             r" & \multicolumn{2}{c}{Isotropic} & \multicolumn{2}{c}{Per measure} & \multicolumn{2}{c}{Per cell} \\",
             r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}",
             r"$q$ & alone & + SIREN & alone & + SIREN & alone & + SIREN \\", r"\midrule"]
    for _, r in R.iterrows():
        lines.append(r"{} & {} \\".format(int(r.q), " & ".join(f3(r[n + " " + t]) for n in ("isotropic", "metric",
                                                                                          "diagonal")
                                                              for t in ("alone", "siren"))))
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_noise.tex", lines)
    return R


def table_blend_learners():
    allr = []
    for s in C.SEEDS:
        R = pickle.load(open("{}/v15/cross_s{}.pkl".format(C.ROOT, s), "rb"))
        allr.append(R.drop(columns="_ps").assign(seed=s))
    A = pd.concat(allr)
    A = A[A.combo.isin(["A model", "B model"])]
    m = A.groupby(["combo", "blend"])[["overall"] + FOUR + ["whole dti", "whole noddi"]].mean()
    names = {"A model": "BCP transformer (400 ep.)", "B model": "HBCD-reference transformer (200 ep.)"}
    order = ["base alone", "model alone", "fixed 0.25/0.75", "learned per metric x distance", "calibrated precision",
             "gbm weight"]
    lab = {"base alone": "PPCA + SIREN", "model alone": "transformer alone", "fixed 0.25/0.75": "fixed 0.25/0.75",
           "learned per metric x distance": "weights per measure x distance (finer bands)",
           "calibrated precision": "calibrated precision weights", "gbm weight": "gradient-boosted weight per cell"}
    lines = [r"\begin{tabular}{llccccccc}", r"\toprule",
             r"Transformer & Blend & Overall & Gap & End & Whole & Region & Tensor & NODDI \\", r"\midrule"]
    for combo in ["A model", "B model"]:
        for i, b in enumerate(order):
            r = m.loc[(combo, b)]
            lines.append(r"{} & {} & {} \\".format(names[combo] if i == 0 else "", lab[b],
                                                    " & ".join(f3(v) for v in r)))
        if combo == "A model":
            lines.append(r"\addlinespace[2pt]")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_blend_learners.tex", lines)
    return m


def table_budget():
    """Configurations and GPU time per model family, from the logs (training lines end with '(N s)')."""
    pat = re.compile(r"^\s+(transformer|graph-unet|functa|vae)\b.*\((\d+) s\)\s*$")
    res = re.compile(r"^RESULT (\S+).*\((\d+) s\)")
    fam = {"tfm": "transformer", "unet": "graph-unet", "functa": "functa", "vae": "vae", "ppca": "ppca",
           "ppca_age": "ppca_age"}
    budget = {}
    for f in sorted(glob.glob(C.ROOT + "/v1[1-5]/*.log")):
        screen = "/v14/" in f
        for line in open(f, errors="ignore"):
            m = res.match(line) if screen else pat.match(line)
            if not m:
                continue
            k = fam.get(m.group(1).split(",")[0], m.group(1)) if screen else m.group(1)
            b = budget.setdefault(k, {"screen_runs": 0, "screen_s": 0, "val_trainings": 0, "val_s": 0})
            if screen:
                b["screen_runs"] += 1
                b["screen_s"] += int(m.group(2))
            else:
                b["val_trainings"] += 1
                b["val_s"] += int(m.group(2))
    R = pd.DataFrame(budget).T
    R.to_csv(C.CACHE + "/rev_budget.csv")
    name = {"transformer": "Transformer", "graph-unet": "Graph U-Net", "functa": "Functa", "vae": "Partial VAE",
            "ppca": "PPCA (screen reference)", "ppca_age": "Age-dependent PPCA"}
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r"Family & Screen runs & Screen GPU h & Validation trainings & Validation GPU h \\", r"\midrule"]
    for k in ["functa", "vae", "ppca_age", "graph-unet", "transformer"]:
        if k in R.index:
            r = R.loc[k]
            lines.append(r"{} & {} & {:.1f} & {} & {:.1f} \\".format(name[k], int(r.screen_runs), r.screen_s / 3600,
                                                                      int(r.val_trainings), r.val_s / 3600))
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_budget.tex", lines)
    return R


def table_acq():
    a = pd.read_csv(C.CACHE + "/desc_ages_BCP.csv")
    a["acq"] = a.scan.str.extract(r"_acq-([^_]+)")[0]
    a["bin"] = pd.cut(a.age, [-1, 3.5, 9.5, 100], labels=["0--3 mo", "4--9 mo", "10--60 mo"])
    t = pd.crosstab(a.acq, a.bin)
    off = []
    for s in C.SEEDS:
        off.append(pd.read_csv("{}/v15/Q_s{}_report/validation/acquisition_correction.csv".format(C.ROOT, s)))
    O = pd.concat(off)
    O = O[O.acquisition == "shells06select"].groupby("metric").shift_sd.mean().reindex(C.METRICS)
    lines = [r"\begin{tabular}{lccc}", r"\toprule", r"Acquisition & " + " & ".join(t.columns) + r" \\", r"\midrule"]
    for acq, r in t.iterrows():
        lines.append(r"\texttt{" + acq + "} & " + " & ".join(str(v) for v in r) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    write("rev_acq.tex", lines)
    for m in C.METRICS:
        mac("acqOff" + C.MLABEL[m], "{:+.2f}".format(O[m]))
    return t, O


def main():
    w = real_weights()
    table_patterns()
    table_main_rev(w)
    table_cap()
    table_tracts()
    table_load()
    table_calib()
    table_baselines()
    table_pooling_bins()
    table_confetti()
    table_fw()
    table_noise()
    table_blend_learners()
    table_budget()
    table_acq()
    count_settings()
    with open(C.TABLES + "/macros_rev.tex", "w") as fh:
        fh.write("% generated by scripts/revision_tables.py; do not edit\n")
        fh.writelines(MAC)
    print("".join(MAC))



def count_settings():
    """Distinct settings scored in the 3-seed protocol (v12, v13, v15; the same setting in several runs counted
    once, runs with a changed pipeline (acquisition correction, pooling) counted separately) and in the screens."""
    runs = {"v12/S0": "", "v13/P12_s0": "", "v13/P3_s0": "", "v15/E_s0": "", "v15/T_s0": "", "v15/R3_s0": "400 ",
            "v15/Q_s0": "acq ", "v15/P_s0": "pooled ", "v15/R1_s0": "", "v15/R2_s0": ""}
    seen = set()
    for run, tag in runs.items():
        d = pd.read_csv("{}/{}_report/validation/validation_summary.csv".format(C.ROOT, run))
        for st in d.setting.unique():
            if st == "cohort mean (reference)":
                continue
            if tag == "400 " and "transformer" not in st:
                tag2 = ""
            else:
                tag2 = tag
            seen.add(tag2 + st)
    mac("nSettingsValidated", str(len(seen)))
    import json
    M = pd.read_csv(C.CACHE + "/desc_missing_BCP.csv")
    names = pd.read_csv(C.CACHE + "/desc_ages_BCP.csv").scan.tolist()
    with_missing = {names[i] for i in M.scan.unique()}
    val = set()
    for sd in C.SEEDS:
        val |= set(json.load(open("{}/v15/R3_s{}_report/validation/validation_settings.json".format(C.ROOT, sd)))["scans"])
    mac("nValidatedWithMissing", str(len(val & with_missing)))
    a = pd.read_csv(C.CACHE + "/desc_ages_BCP.csv")
    ss = a.scan.str.extract(r"^(sub-[^_]+_ses-[^_]+)")[0]
    g = ss.value_counts()
    mac("bcpSessions", str(len(g)))
    mac("bcpSessionsBoth", str(int((g > 1).sum())))
    mac("nSettingsDump", "4")  # weight tables (shipped, cross-fitted) x 2 transformers: scored offline
    return len(seen)


if __name__ == "__main__":
    main()
