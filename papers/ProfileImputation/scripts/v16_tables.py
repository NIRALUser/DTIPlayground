"""Tables and numbers of the review-round-1 GPU runs (testProfiles/ImputeValidation/v16):
  E1   untouched subjects (seeds 3-5, subjects of seeds 0-2 excluded)
  E2   the "real mask" pattern (4th pass in every v16 run)
  E3   HBCD alone (seeds 0-2; transformer 200 epochs)
  E5   pooling decomposition (E5i: pooled norm, BCP PPCA; E5ii: BCP norm, pooled PPCA; E5iii: both pooled, age bins
       and kernel norm), BCP scans, compared with the BCP-alone runs v15/E_s* (same scans and hidden values)
Every macro is written; a result that does not exist yet is \\pending{...}. Re-run when runs finish.
Writes tables/v16_*.tex and tables/macros_v16.tex."""
import os

import numpy as np
import pandas as pd

import common as C

MAC = []
FOUR = C.PATS
PENDING = r"\pending{}"
TF = C.TF
SIR = "population q=80 isotropic + siren xyz omega0=10"
KNN = "population q=80 isotropic + knn k=20"


def mac(name, value):
    MAC.append(C.macro(name, value))


def f3(x):
    return PENDING if x is None or not np.isfinite(x) else "{:.3f}".format(x)


def exists(run, seed):
    return os.path.isfile(os.path.join(C.run_path(run, seed), "validation_by_scan.csv"))


SETTINGS = {
    "age-bin mean": "prior-mean",
    "PPCA alone": C.POP,
    "PPCA + kNN": KNN,
    "PPCA + SIREN": SIR,
    "Transformer alone": TF,
    "Fixed blend (SIREN base)": "graph near 0.25 beyond 0.75: {}, {}".format(SIR, TF),
    "Fixed blend (kNN base)": "graph near 0.25 beyond 0.75: {}, {}".format(KNN, TF),
    "Precision blend": "precision: {}, {}".format(SIR, TF),
    "Shipped table (SIREN base; released default)": "table: {}, {}".format(SIR, TF),
    "Shipped table (kNN base)": "table: {}, {}".format(KNN, TF),
}


def register(prefix, run, refrun=None):
    for name, st in SETTINGS.items():
        C.S["{} {}".format(prefix, name)] = (run, st, refrun)


def summary(label, seeds):
    seeds = [s for s in seeds if exists(C.S[label][0], s)]
    if not seeds:
        return None
    rows = []
    for s in seeds:
        try:
            q = C.cell_ratios(label, s)
        except KeyError:
            return None
        q4 = q[q.pattern.isin(FOUR)]
        r = {"seed": s, "overall": q4.r.mean()}
        for p in FOUR + ["real mask"]:
            r[p] = q[q.pattern == p].r.mean() if (q.pattern == p).any() else np.nan
        r.update(q4.groupby("age_bin").r.mean().to_dict())
        wm = q[q.pattern == "whole measure"]
        r["whole dti"] = wm[wm.metric.isin(C.FAM["dti"])].r.mean()
        r["whole noddi"] = wm[wm.metric.isin(C.FAM["noddi"])].r.mean()
        rows.append(r)
    return pd.DataFrame(rows)


def run_table(prefix, seeds, fname, tag):
    cols = ["gap", "end gap", "whole profile", "region", "whole dti", "whole noddi", "real mask"]
    lines = [r"\begin{tabular}{lcccccccc}", r"\toprule",
             r"Setting & Overall (SD) & Gap & End & Whole & Region & Tensor & NODDI & Real mask \\", r"\midrule"]
    out = {}
    for name in SETTINGS:
        d = summary("{} {}".format(prefix, name), seeds)
        if d is None:
            lines.append(r"{} & \multicolumn{{8}}{{c}}{{{}}} \\".format(name, PENDING))
            continue
        m = d.mean(numeric_only=True)
        out[name] = m
        lines.append(r"{} & {} ({:.3f}) & {} \\".format(name, f3(m.overall), d.overall.std() if len(d) > 1 else 0,
                                                         " & ".join(f3(m.get(c, np.nan)) for c in cols)))
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex(fname, "\n".join(lines) + "\n")
    keys = {"PPCA alone": "Ppca", "PPCA + kNN": "Knn", "PPCA + SIREN": "Def", "Transformer alone": "Tf",
            "Fixed blend (SIREN base)": "Fixed", "Shipped table (SIREN base; released default)": "Final",
            "Shipped table (kNN base)": "FinalKnn", "Precision blend": "Prec"}
    for name, k in keys.items():
        m = out.get(name)
        for col, t in [("overall", ""), ("whole profile", "Whole"), ("region", "Region"), ("gap", "Gap"),
                       ("end gap", "End"), ("whole dti", "Wdti"), ("whole noddi", "Wnoddi"), ("real mask", "Real"),
                       ("4-9m", "BinB"), ("10-60m", "BinC")]:
            mac(tag + k + t, f3(np.nan if m is None else m.get(col, np.nan)))
        mac(tag + k + "OverallBC", f3(np.nan if m is None else np.nanmean([m.get("4-9m", np.nan),
                                                                            m.get("10-60m", np.nan)])))
    return out


def paired_block(prefix, seeds, tag):
    pairs = [("FinalVsDef", "PPCA + SIREN", "Shipped table (SIREN base; released default)", None),
             ("FinalVsDefWhole", "PPCA + SIREN", "Shipped table (SIREN base; released default)", "whole profile"),
             ("FinalVsDefReal", "PPCA + SIREN", "Shipped table (SIREN base; released default)", "real mask"),
             ("KnnVsDefWhole", "PPCA + SIREN", "PPCA + kNN", "whole profile"),
             ("KnnVsDefReal", "PPCA + SIREN", "PPCA + kNN", "real mask"),
             ("KnnVsDefGap", "PPCA + SIREN", "PPCA + kNN", "gap"),
             ("FinalVsKnnReal", "PPCA + kNN", "Shipped table (SIREN base; released default)", "real mask"),
             ("FinalKnnVsKnn", "PPCA + kNN", "Shipped table (kNN base)", None),
             ("FinalKnnVsKnnReal", "PPCA + kNN", "Shipped table (kNN base)", "real mask"),
             ("FinalVsFixed", "Fixed blend (SIREN base)", "Shipped table (SIREN base; released default)", None),
             ("PpcaVsDefReal", "PPCA + SIREN", "PPCA alone", "real mask")]
    rows = []
    for key, a, b, pat in pairs:
        la, lb = "{} {}".format(prefix, a), "{} {}".format(prefix, b)
        ss = [s for s in seeds if exists(C.S[la][0], s)]
        res = None
        if ss:
            try:
                pats = C.PATS if pat is None else [pat]
                A = C.scan_scores(la, seeds=ss, patterns=pats)
                B = C.scan_scores(lb, seeds=ss, patterns=pats)
                if len(A) and len(B):
                    res = C.paired(A, B)
            except KeyError:
                res = None
        if res is None:
            for suf in ("", "Ci", "Better"):
                mac(tag + key + suf, PENDING)
            if key == "FinalVsDef":
                mac(tag + "Pairs", PENDING)
                mac(tag + "Subjects", PENDING)
            continue
        if key == "FinalVsDef":
            mac(tag + "Pairs", str(int(res["n"])))
            mac(tag + "Subjects", str(int(res["n_subj"])))
        mac(tag + key, "{:.3f}".format(res["ratio"]))
        mac(tag + key + "Ci", "{:.3f}--{:.3f}".format(res["blo"], res["bhi"]))
        mac(tag + key + "Better", "{:.0f}".format(100 * res["better"]))
        rows.append(dict(contrast=key, pattern=pat or "4pat", **res))
    pd.DataFrame(rows).to_csv("{}/v16_{}_paired.csv".format(C.CACHE, tag), index=False)


def e1():
    register("E1", "v16/E1")
    seeds = (3, 4, 5)
    run_table("E1", seeds, "v16_e1.tex", "eOne")
    paired_block("E1", seeds, "eOne")
    # scans per bin and overlap with seeds 0-2 (subjects are excluded by construction)
    n = []
    for s in seeds:
        if exists("v16/E1", s):
            d = pd.read_csv(os.path.join(C.run_path("v16/E1", s), "validation_by_scan.csv"))
            n.append(d.groupby("group").scan.nunique())
    if n:
        N = pd.concat(n, axis=1).fillna(0)
        for b, t in zip(C.BINS, "ABC"):
            mac("eOneScansBin" + t, "{:g}".format(N.loc[b].iloc[0]) if b in N.index else "0")
        mac("eOneSeedsDone", str(len(n)))
    else:
        for t in "ABC":
            mac("eOneScansBin" + t, PENDING)
        mac("eOneSeedsDone", "0")


def e3():
    register("E3", "v16/E3")
    run_table("E3", (0, 1, 2), "v16_e3.tex", "eThree")
    paired_block("E3", (0, 1, 2), "eThree")
    f = C.CACHE + "/dump_e3_results.csv"
    if os.path.isfile(f):
        d = pd.read_csv(f).groupby("setting").mean(numeric_only=True)
        mac("eThreeRefit", f3(d.loc["table (cross-fitted)", "overall"]) if "table (cross-fitted)" in d.index
            else PENDING)
        mac("eThreeShippedDump", f3(d.loc["table (shipped)", "overall"]) if "table (shipped)" in d.index else PENDING)
        for k, st in (("eThreeRefitReal", "table (cross-fitted)"), ("eThreeShippedReal", "table (shipped)")):
            mac(k, f3(d.loc[st, "real mask"]) if st in d.index and "real mask" in d.columns else PENDING)
    else:
        mac("eThreeRefit", PENDING)
        mac("eThreeShippedDump", PENDING)
        mac("eThreeRefitReal", PENDING)
        mac("eThreeShippedReal", PENDING)


KEYS = {"E5i": "A", "E5ii": "B", "E5iii": "C", "E5iiik": "CK", "E5iv": "D"}


def e5():
    """Pooling decomposition, BCP scans, 4 patterns against the BCP-alone age-bin mean of v15/E."""
    variants = [("E5i", "v16/E5i", SIR, "Pooled norm, BCP PPCA"),
                ("E5ii", "v16/E5ii", SIR, "BCP norm, pooled PPCA"),
                ("E5iii", "v16/E5iii", SIR, "Both pooled, age bins"),
                ("E5iiik", "v16/E5iii", "population q=80 isotropic [kernel cv] + siren xyz omega0=10",
                 "Both pooled, kernel age norm"),
                ("E5iv", "v15/P", SIR, "Both pooled, age bins (v15)")]
    base = C.scan_scores("P6 default (E check)")
    lines = [r"\begin{tabular}{lccccc}", r"\toprule",
             r"PPCA + SIREN with & Overall & All (paired) & 0--3 mo & 4--9 mo & 10--60 mo \\", r"\midrule"]
    for key, run, st, name in variants:
        C.S["X5 " + key] = (run, st, "v15/E")
        ok = all(exists(run, s) for s in C.SEEDS)
        cells = []
        if ok:
            try:
                o = C.summary("X5 " + key).overall.mean()
                B = C.scan_scores("X5 " + key)
                res = {}
                for bn in ["all"] + C.BINS:
                    A = base if bn == "all" else base[base.group == bn]
                    res[bn] = C.paired(A[["scan", "seed", "r"]], B)
                cells = [f3(o)] + ["{:.3f} [{:.3f}, {:.3f}]".format(res[b]["ratio"], res[b]["blo"], res[b]["bhi"])
                                   for b in ["all"] + C.BINS]
                mac("eFive" + KEYS[key], "{:.3f}".format(res["all"]["ratio"]))
                for bn, t in zip(C.BINS, "ABC"):
                    mac("eFive" + KEYS[key] + "Bin" + t, "{:.3f}".format(res[bn]["ratio"]))
            except KeyError:
                ok = False
        if not ok:
            cells = [PENDING] * 5
            k = KEYS[key]
            mac("eFive" + k, PENDING)
            for t in "ABC":
                mac("eFive" + k + "Bin" + t, PENDING)
        lines.append(name + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("v16_e5.tex", "\n".join(lines) + "\n")


def real_mask_summary():
    """E2: the real-mask pattern across the v16 runs (BCP: E1 and the E5 runs; HBCD: E3)."""
    lines = [r"\begin{tabular}{lccc}", r"\toprule",
             r"Setting & BCP, untouched subjects (E1) & BCP, seeds 0--2 (E5i) & HBCD (E3) \\", r"\midrule"]
    C.S["X5r PPCA + SIREN"] = ("v16/E5i", SIR, None)
    C.S["X5r PPCA + kNN"] = ("v16/E5i", KNN, None)
    C.S["X5r PPCA alone"] = ("v16/E5i", C.POP, None)
    # real masks: pooling the PPCA (E5ii) or both (E5iii) against the BCP PPCA of E5i, same reference (E5i)
    for key, run in (("B", "v16/E5ii"), ("C", "v16/E5iii")):
        if all(exists(run, sd) for sd in C.SEEDS) and all(exists("v16/E5i", sd) for sd in C.SEEDS):
            C.S["X5rr " + key] = (run, SIR, "v16/E5i")
            C.S["X5rr A"] = ("v16/E5i", SIR, "v16/E5i")
            r = C.paired(C.scan_scores("X5rr A", patterns=["real mask"]), C.scan_scores("X5rr " + key,
                                                                                        patterns=["real mask"]))
            mac("eFiveReal" + key, "{:.3f}".format(r["ratio"]))
            mac("eFiveReal" + key + "Ci", "{:.3f}--{:.3f}".format(r["blo"], r["bhi"]))
        else:
            mac("eFiveReal" + key, PENDING)
            mac("eFiveReal" + key + "Ci", PENDING)
    for name in SETTINGS:
        cells = []
        for prefix, seeds in (("E1", (3, 4, 5)), ("X5r", C.SEEDS), ("E3", C.SEEDS)):
            lab = "{} {}".format(prefix, name)
            if lab not in C.S:
                cells.append("--")
                continue
            d = summary(lab, seeds)
            cells.append(f3(np.nan if d is None else d["real mask"].mean()))
        lines.append(name + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("v16_real.tex", "\n".join(lines) + "\n")


def o5():
    """Equal-budget graph U-Net (200 epochs, v16/U200_s*) against v15/E (60 epochs) and the 200-epoch transformer
    (v15/T), on the same scans and hidden values."""
    GU = C.GU
    C.S["U200 alone"] = ("v16/U200", GU, None)
    C.S["U200 fixed"] = ("v16/U200", "graph near 0.25 beyond 0.75: {}, {}".format(SIR, GU), None)
    ok = all(exists("v16/U200", s) for s in C.SEEDS)
    if not ok:
        for k in ("oFiveUnet", "oFiveUnetWdti", "oFiveBlend", "oFiveVsSixty", "oFiveVsSixtyCi", "oFiveVsTf",
                  "oFiveVsTfCi"):
            mac(k, PENDING)
        return
    a = C.summary("U200 alone").mean(numeric_only=True)
    b = C.summary("U200 fixed").mean(numeric_only=True)
    mac("oFiveUnet", f3(a.overall))
    mac("oFiveUnetWdti", f3(a["whole dti"]))
    mac("oFiveBlend", f3(b.overall))
    U = C.scan_scores("U200 alone")
    for key, ref in (("oFiveVsSixty", "P4 U-Net (deviations+PPCA)"), ("oFiveVsTf", "P6 transformer (200 ep.)")):
        r = C.paired(C.scan_scores(ref), U)
        mac(key, "{:.3f}".format(r["ratio"]))
        mac(key + "Ci", "{:.3f}--{:.3f}".format(r["blo"], r["bhi"]))


def e1_dumps():
    """E1 from the cell dumps: the kernel-norm reference (E6) and the calibration of the shipped blend (E7)."""
    keys = [("eOneKFinal", "table (shipped)", "overall_k"), ("eOneKFinalWhole", "table (shipped)", "whole profile_k"),
            ("eOneKDef", "PPCA + SIREN", "overall_k"), ("eOneKDefWhole", "PPCA + SIREN", "whole profile_k"),
            ("eOneKKnnWhole", "PPCA + kNN", "whole profile_k"), ("eOneKernelAlone", "kernel norm", "overall"),
            ("eOneKernelAloneWhole", "kernel norm", "whole profile"),
            ("eOneShippedDump", "table (shipped)", "overall"), ("eOneRefitDump", "table (cross-fitted)", "overall")]
    f = C.CACHE + "/dump_e1_results.csv"
    R = pd.read_csv(f).groupby("setting").mean(numeric_only=True) if os.path.isfile(f) else None
    for k, st, col in keys:
        v = R.loc[st, col] if R is not None and st in R.index and col in R.columns else np.nan
        mac(k, f3(v))
    f = C.CACHE + "/dump_e1_calib.csv"
    K = pd.read_csv(f) if os.path.isfile(f) else None
    for t, pats in [("Whole", ["whole profile"]), ("Real", ["real mask"]), ("Region", ["region"])]:
        if K is None:
            mac("eOneCal" + t, PENDING)
            continue
        y = K[(K.setting == "table (shipped)") & K.pattern.isin(pats)].groupby("metric")[["n", "z2", "within"]].sum()
        mac("eOneCal" + t, "{:.2f}".format(np.mean(np.sqrt(y.z2 / y.n))) if len(y) else PENDING)
        mac("eOneCal" + t + "Cov", "{:.0f}".format(100 * np.mean(y.within / y.n)) if len(y) else PENDING)


def main():
    e1_dumps()
    o5()
    e1()
    e3()
    e5()
    real_mask_summary()
    with open(C.TABLES + "/macros_v16.tex", "w") as fh:
        fh.write("% generated by scripts/v16_tables.py; \\pending{} marks results not available yet\n")
        fh.writelines(MAC)
    print("".join(MAC))


if __name__ == "__main__":
    main()
