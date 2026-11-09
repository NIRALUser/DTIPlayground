"""All tables of the paper and the macros of the numbers quoted in the text (tables/*.tex, tables/macros.tex).

Inputs: the validation result folders under testProfiles/ImputeValidation (v10, v12, v13, v14, v15) and the caches of
dump_analysis.py (run it first). Usage: python make_tables.py
"""
import glob
import re

import numpy as np
import pandas as pd

import common as C

MAC = []


def mac(name, value):
    MAC.append(C.macro(name, value))


def f3(x):
    return "--" if not np.isfinite(x) else "{:.3f}".format(x)


# ----------------------------------------------------------------------------------------------------------------
# dump-based settings (cross-fitted blends, reference-trained transformer)

DUMP = pd.read_csv(C.CACHE + "/dump_bcp_results.csv")
DUMP_SCANS = pd.read_csv(C.CACHE + "/dump_bcp_scans.csv")
DUMP_SCANS = DUMP_SCANS[DUMP_SCANS.group == "4pat"]
DUMP_DIST = pd.read_csv(C.CACHE + "/dump_bcp_cells.csv")
DUMP_DIST["metric"] = [C.METRICS[int(m)] for m in DUMP_DIST.metric]  # the dumps index the metrics 0-6
DUMP_LABEL = {"D table blend (released default)": "table (cross-fitted)",
              "D fixed blend 400 (dump)": "fixed 0.25/0.75",
              "D default (dump)": "PPCA + SIREN",
              "D transformer 400 (dump)": "transformer",
              "D reference transformer": "reference transformer",
              "D reference fixed blend": "reference fixed 0.25/0.75",
              "D reference table blend": "reference table (cross-fitted)"}


def summary(label):
    if label in DUMP_LABEL:
        d = DUMP[DUMP.setting == DUMP_LABEL[label]].copy()
        d["setting"] = label
        return d
    return C.summary(label)


def scan_scores(label, patterns=C.PATS):
    if label in DUMP_LABEL:
        assert patterns == C.PATS
        d = DUMP_SCANS[DUMP_SCANS.setting == DUMP_LABEL[label]]
        return d[["scan", "seed", "r"]].copy()
    return C.scan_scores(label, patterns=patterns)


def per_metric(label, patterns=C.PATS):
    if label in DUMP_LABEL:
        d = DUMP_DIST[(DUMP_DIST.setting == DUMP_LABEL[label]) & DUMP_DIST.pattern.isin(patterns)]
        a = d.groupby(["seed", "pattern", "metric", "age_bin"])[["e2", "r2"]].sum()
        r = np.sqrt(a.e2 / a.r2).rename("r").reset_index()
        return r.groupby(["seed", "metric"]).r.mean().groupby("metric").mean()
    return C.per_metric(label, patterns=patterns)


# ----------------------------------------------------------------------------------------------------------------
# Table: phase-wise progression on the common protocol

MAIN = [
    ("Reference", [("Age-bin mean", "age-bin mean", False)]),
    ("A. Same-scan interpolation (the scan's own values)", [
        ("Arc-linear, constant ends", "P1 arc-linear, constant ends", True),
        ("Linear (3-D Delaunay)", "P1 linear (3-D)", True),
        ("kNN, $k=20$", "P1 kNN k=20", True),
        ("SIREN, xyz", "P1 SIREN xyz", True),
        ("SIREN, xyz+tract", "P1 SIREN xyz+tract", True)]),
    ("B. Norm-referenced local methods (deviations from the age-bin norm)", [
        ("Arc-linear, constant ends", "P2 arc-linear, constant ends", True),
        ("Linear (3-D Delaunay)", "P2 linear (3-D)", True),
        ("kNN, $k=20$", "P2 kNN k=20", True),
        ("kNN, $k=50$", "P2 kNN k=50", True),
        ("SIREN, xyz+arc", "P2 SIREN xyz+arc", True),
        ("SIREN, xyz", "P2 SIREN xyz", True)]),
    ("C. Linear population model (PPCA, $q=80$)", [
        ("PPCA alone", "P3 PPCA q=80", False),
        ("PPCA + kNN on residuals ($\\leq$4\\,mm)", "P3 PPCA q=80 + kNN", False),
        ("PPCA + SIREN on residuals ($\\leq$4\\,mm)", "P3 PPCA + SIREN", False)]),
    ("E. Amortized networks and F. blends: graph U-Net (hybrid)", [
        ("U-Net alone", "P4 U-Net (deviations+PPCA)", False),
        ("U-Net + SIREN on residuals", "P4 U-Net + SIREN", False),
        ("PPCA + SIREN, U-Net beyond 4\\,mm", "P4 PPCA + SIREN, U-Net beyond", False)]),
    ("E/F. Transformer (hybrid) and blends", [
        ("Transformer alone, 200 epochs", "P6 transformer (200 ep.)", False),
        ("Transformer alone, 400 epochs", "P6 transformer (400 ep.)", False),
        ("PPCA + SIREN, transformer beyond 4\\,mm", "P6 PPCA + SIREN, transformer beyond", False),
        ("Blend with U-Net, fixed 0.25/0.75", "P6 U-Net blend 0.25/0.75", False),
        ("Blend with transformer (200), fixed 0.25/0.75", "P6 transformer blend 0.25/0.75", False),
        ("Blend with transformer (400), fixed 0.25/0.75", "P6 transformer 400 blend 0.25/0.75", False),
        ("Blend with transformer (400), weight table$^{\\ast}$", "D table blend (released default)", False)]),
    ("E/F. Transformer (200 epochs) trained with the HBCD reference cohort", [
        ("Reference transformer alone", "D reference transformer", False),
        ("Blend, fixed 0.25/0.75", "D reference fixed blend", False),
        ("Blend, weight table$^{\\ast}$", "D reference table blend", False)]),
]


def table_main():
    cols = ["gap", "end gap", "whole profile", "region", "whole dti", "whole noddi"]
    lines = [r"\begin{tabular}{l@{\hspace{4pt}}c@{\hspace{6pt}}cccc@{\hspace{6pt}}cc}", r"\toprule",
             r" & & \multicolumn{4}{c}{Pattern} & \multicolumn{2}{c}{Whole family missing} \\",
             r"\cmidrule(lr){3-6}\cmidrule(lr){7-8}",
             r"Setting & Overall (SD) & Gap & End & Whole & Region & Tensor & NODDI \\", r"\midrule"]
    allrows = []
    for gi, (group, rows) in enumerate(MAIN):
        if gi:
            lines.append(r"\addlinespace[2pt]")
        lines.append(r"\multicolumn{8}{l}{\textit{" + group + r"}} \\")
        for name, label, leaves in rows:
            d = summary(label)
            m = d[["overall"] + cols].mean()
            sd = d.overall.std()
            allrows.append(dict(group=group, setting=name, label=label, sd=sd, **m.to_dict()))
            mark = r"$^{\dagger}$" if leaves else ""
            lines.append(r"\quad {}{} & {} ({:.3f}) & {} \\".format(
                name, mark, f3(m.overall), 0 if not np.isfinite(sd) else sd,
                " & ".join(f3(m[c]) for c in cols)))
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_main.tex", "\n".join(lines) + "\n")
    R = pd.DataFrame(allrows)
    R.to_csv(C.CACHE + "/main_table.csv", index=False)
    return R


# ----------------------------------------------------------------------------------------------------------------
# paired per-scan comparisons

CONTRASTS = [
    # (family, description, a (reference), b (compared))
    ("Population model", "PPCA + SIREN vs PPCA alone", "P3 PPCA q=80", "P3 PPCA + SIREN"),
    ("Population model", "PPCA + kNN vs PPCA + SIREN", "P3 PPCA + SIREN", "P3 PPCA q=80 + kNN"),
    ("Population model", "$q=40$ vs $q=80$ (+ SIREN)", "P3 PPCA + SIREN", "P3 PPCA q=40 + SIREN"),
    ("Population model", "$q=120$ vs $q=80$ (+ SIREN)", "P3 PPCA + SIREN", "P3 PPCA q=120 + SIREN"),
    ("Graph U-Net", "U-Net alone vs PPCA + SIREN", "P3 PPCA + SIREN", "P4 U-Net (deviations+PPCA)"),
    ("Graph U-Net", "U-Net beyond 4\\,mm vs PPCA beyond", "P3 PPCA + SIREN", "P4 PPCA + SIREN, U-Net beyond"),
    ("Graph U-Net", "U-Net blend 0.25/0.75 vs PPCA + SIREN", "P3 PPCA + SIREN", "P6 U-Net blend 0.25/0.75"),
    ("Transformer", "Transformer alone vs PPCA + SIREN", "P3 PPCA + SIREN", "P6 transformer (200 ep.)"),
    ("Transformer", "Transformer alone vs U-Net alone", "P4 U-Net (deviations+PPCA)", "P6 transformer (200 ep.)"),
    ("Transformer", "Transformer blend 0.25/0.75 vs PPCA + SIREN", "P3 PPCA + SIREN",
     "P6 transformer blend 0.25/0.75"),
    ("Transformer", "Transformer blend vs U-Net blend (0.25/0.75)", "P6 U-Net blend 0.25/0.75",
     "P6 transformer blend 0.25/0.75"),
    ("Blending", "Precision weights vs fixed 0.25/0.75", "P6 transformer blend 0.25/0.75",
     "P6 transformer precision blend"),
    ("Blending", "400 vs 200 epochs (fixed blend)", "P6 transformer blend 0.25/0.75",
     "P6 transformer 400 blend 0.25/0.75"),
    ("Blending", "Weight table vs fixed (400 epochs)", "D fixed blend 400 (dump)", "D table blend (released default)"),
    ("Blending", "Released default vs PPCA + SIREN", "P3 PPCA + SIREN", "D table blend (released default)"),
    ("Not helpful", "Acquisition correction vs none", "P6 default (E check)", "P6 acq. correction: default"),
    ("Second cohort", "Pooled PPCA + SIREN vs BCP alone", "P6 default (E check)", "P6 pooled: PPCA + SIREN"),
    ("Second cohort", "Reference transformer vs BCP transformer (alone)", "D transformer 400 (dump)",
     "D reference transformer"),
    ("Second cohort", "Reference vs BCP transformer (table blend)", "D table blend (released default)",
     "D reference table blend"),
]


def table_paired():
    rows = []
    for fam, desc, a, b in CONTRASTS:
        r = C.paired(scan_scores(a), scan_scores(b))
        rows.append(dict(family=fam, contrast=desc, a=a, b=b, **r))
    R = pd.DataFrame(rows)
    R["p_holm"] = C.holm(R.p)
    R["p_subj_holm"] = C.holm(R.p_subj)
    R.to_csv(C.CACHE + "/paired.csv", index=False)
    lines = [r"\begin{tabular}{llcccc}", r"\toprule",
             r"Contrast (compared vs reference) & Ratio & 95\% CI (pairs) & 95\% CI (subjects) & $p_\mathrm{Holm}$ "
             r"(pairs / subjects) & Better \\", r"\midrule"]
    last = None
    for _, r in R.iterrows():
        if r.family != last:
            if last is not None:
                lines.append(r"\addlinespace[2pt]")
            lines.append(r"\multicolumn{6}{l}{\textit{" + r.family + r"}} \\")
            last = r.family
        lines.append(r"\quad {} & {:.3f} & {:.3f}--{:.3f} & {:.3f}--{:.3f} & {} / {} & {:.0f}\% \\".format(
            r.contrast, r.ratio, r.lo, r.hi, r.blo, r.bhi, C.fmt_p(r.p_holm), C.fmt_p(r.p_subj_holm),
            100 * r.better))
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_paired.tex", "\n".join(lines) + "\n")
    # whole-family contrasts (pattern "whole measure")
    wm = []
    for desc, a, b in [("U-Net vs PPCA", "P3 PPCA q=80", "P4 U-Net (deviations+PPCA)"),
                       ("Transformer (200) vs PPCA", "P3 PPCA q=80", "P6 transformer (200 ep.)"),
                       ("Transformer (400) vs PPCA", "P3 PPCA q=80", "P6 transformer (400 ep.)"),
                       ("Transformer (200) vs U-Net", "P4 U-Net (deviations+PPCA)", "P6 transformer (200 ep.)")]:
        r = C.paired(C.scan_scores(a, patterns=["whole measure"]), C.scan_scores(b, patterns=["whole measure"]))
        wm.append(dict(contrast=desc, **r))
    W = pd.DataFrame(wm)
    W.to_csv(C.CACHE + "/paired_whole_measure.csv", index=False)
    return R, W


def single_seed_screens():
    """R1 (context and distance inputs) and R2 (3 members), seed 0 only, against the plain transformer of R3_s0's
    protocol twin T_s0 (200 epochs, same hidden values)."""
    out = []
    base_tf = C.scan_scores("P6 transformer (200 ep.)", seeds=(0,))
    base_bl = C.scan_scores("P6 transformer blend 0.25/0.75", seeds=(0,))
    extra = {
        "dist": ("v15/R1", TFX(" +dist")), "age+acq": ("v15/R1", TFX(" +age+acq")), "3 members": ("v15/R2", TFX(" x3"))}
    for name, (run, st) in extra.items():
        C.S["X " + name] = (run, st, None)
        C.S["XB " + name] = (run, "graph near 0.25 beyond 0.75: {}, {}".format(C.DEF, st), None)
        s = C.summary("X " + name, seeds=(0,)).iloc[0]
        sb = C.summary("XB " + name, seeds=(0,)).iloc[0]
        p = C.paired(base_tf, C.scan_scores("X " + name, seeds=(0,)))
        pb = C.paired(base_bl, C.scan_scores("XB " + name, seeds=(0,)))
        out.append(dict(variant=name, alone=s.overall, blend=sb.overall, ratio_alone=p["ratio"], p_alone=p["p"],
                        ratio_blend=pb["ratio"], p_blend=pb["p"], better_blend=pb["better"],
                        lo_blend=pb["blo"], hi_blend=pb["bhi"]))
    t0 = C.summary("P6 transformer (200 ep.)", seeds=(0,)).iloc[0].overall
    b0 = C.summary("P6 transformer blend 0.25/0.75", seeds=(0,)).iloc[0].overall
    # the same transformer in R1_s0 (no extra inputs): checks that R1 reproduces T_s0
    C.S["X none"] = ("v15/R1", C.TF, None)
    t1 = C.summary("X none", seeds=(0,)).iloc[0].overall
    R = pd.DataFrame(out)
    R.to_csv(C.CACHE + "/single_seed.csv", index=False)
    return R, t0, b0, t1


def TFX(suffix):
    return C.TF + suffix


# ----------------------------------------------------------------------------------------------------------------
# per measure

METRIC_ROWS = [("Age-bin mean: absolute RMSE", None),
               ("Phase 2: SIREN on deviations", "P2 SIREN xyz"),
               ("PPCA alone", "P3 PPCA q=80"),
               ("PPCA + SIREN", "P3 PPCA + SIREN"),
               ("U-Net alone", "P4 U-Net (deviations+PPCA)"),
               ("Transformer alone (400)", "D transformer 400 (dump)"),
               ("Released default (table blend)", "D table blend (released default)"),
               ("With HBCD reference (table blend)", "D reference table blend")]


def absolute_age_mean():
    """Absolute RMSE of the age-bin mean per metric (mean over patterns, age bins, seeds), from v13/P12."""
    vals = []
    for seed in C.SEEDS:
        d = C.read("v13/P12", seed, "validation_by_age_bin.csv")
        d = d[(d.setting == "prior-mean") & d.pattern.isin(C.PATS)]
        vals.append(d.groupby("metric").rmse.mean())
    return pd.concat(vals, axis=1).mean(axis=1)


def table_metric():
    absm = absolute_age_mean()
    scale = {"fa": 1e3, "NDI": 1e3, "ODI": 1e3, "FWF": 1e3, "md": 1e6, "rd": 1e6, "ad": 1e6}
    lines = [r"\begin{tabular}{l" + "c" * 7 + "}", r"\toprule",
             "Setting & " + " & ".join(C.MLABEL[m] for m in C.METRICS) + r" \\", r"\midrule"]
    rows = {}
    for name, label in METRIC_ROWS:
        if label is None:
            lines.append(name + "$^{\\ddagger}$ & " + " & ".join("{:.1f}".format(absm[m] * scale[m])
                                                                 for m in C.METRICS) + r" \\")
            lines.append(r"\midrule")
            continue
        pm = per_metric(label)
        rows[name] = pm
        lines.append(name + " & " + " & ".join(f3(pm[m]) for m in C.METRICS) + r" \\")
    lines.append(r"\midrule")
    lines.append(r"\multicolumn{8}{l}{\textit{Whole family missing (tensor: FA--AD; NODDI: NDI--FWF)}} \\")
    for name, label in [("PPCA alone", "P3 PPCA q=80"), ("U-Net alone", "P4 U-Net (deviations+PPCA)"),
                        ("Transformer alone (400)", "D transformer 400 (dump)"),
                        ("Released default (table blend)", "D table blend (released default)")]:
        pm = per_metric(label, patterns=["whole measure"])
        rows["WM " + name] = pm
        lines.append(name + " & " + " & ".join(f3(pm[m]) for m in C.METRICS) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_metric.tex", "\n".join(lines) + "\n")
    pd.DataFrame(rows).to_csv(C.CACHE + "/per_metric.csv")
    return pd.DataFrame(rows), absm


# ----------------------------------------------------------------------------------------------------------------
# absolute RMSE per measure and age bin (released default vs age-bin mean), from the dumps

def table_absolute():
    d = DUMP_DIST[DUMP_DIST.pattern.isin(C.PATS)]
    out = {}
    for lab in ("age-bin mean", "table (cross-fitted)", "reference table (cross-fitted)"):
        x = d[d.setting == lab].groupby(["seed", "pattern", "metric", "age_bin"])[["e2", "n"]].sum()
        rmse = np.sqrt(x.e2 / x.n).rename("rmse").reset_index()
        out[lab] = rmse.groupby(["seed", "metric", "age_bin"]).rmse.mean().groupby(["metric", "age_bin"]).mean()
    scale = {"fa": 1e3, "NDI": 1e3, "ODI": 1e3, "FWF": 1e3, "md": 1e6, "rd": 1e6, "ad": 1e6}
    lines = [r"\begin{tabular}{ll" + "c" * 7 + "}", r"\toprule",
             "Age bin & Setting & " + " & ".join(C.MLABEL[m] for m in C.METRICS) + r" \\", r"\midrule"]
    names = {"age-bin mean": "Age-bin mean", "table (cross-fitted)": "Released default",
             "reference table (cross-fitted)": "With HBCD reference"}
    for bi, b in enumerate(C.BINS):
        if bi:
            lines.append(r"\addlinespace[2pt]")
        for k, (lab, s) in enumerate(out.items()):
            first = C.BIN_LABEL[b] if k == 0 else ""
            lines.append("{} & {} & ".format(first, names[lab]) + " & ".join(
                "{:.1f}".format(s[(m, b)] * scale[m]) for m in C.METRICS) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_absolute.tex", "\n".join(lines) + "\n")
    pd.DataFrame(out).to_csv(C.CACHE + "/absolute.csv")
    return out


# ----------------------------------------------------------------------------------------------------------------
# quick screens (v14): functa, VAE, age-dependent PPCA, transformer variants

def parse_screens():
    rows = []
    pat = re.compile(r"^RESULT (\S+)(?: (tsteps=\d+))?\s+gap ([\d.]+) end gap ([\d.]+) whole profile ([\d.]+) region "
                     r"([\d.]+) whole dti ([\d.]+) whole noddi ([\d.]+) \| 4-pattern ([\d.]+)")
    for f in sorted(glob.glob(C.ROOT + "/v14/*.log")):
        for line in open(f):
            m = pat.match(line.strip())
            if not m:
                continue
            cfg = m.group(1)
            fam = cfg.split(",")[0]
            hyb = fam in ("ppca", "unet", "ppca_age") or "hyb=80" in cfg
            rows.append(dict(log=f.rsplit("/", 1)[1], config=cfg, tsteps=m.group(2) or "", family=fam,
                             target="hybrid" if hyb and fam not in ("ppca", "ppca_age") else
                             ("population" if fam in ("ppca", "ppca_age") else "deviations"),
                             gap=float(m.group(3)), end=float(m.group(4)), whole=float(m.group(5)),
                             region=float(m.group(6)), wdti=float(m.group(7)), wnoddi=float(m.group(8)),
                             overall=float(m.group(9))))
    R = pd.DataFrame(rows)
    R.to_csv(C.CACHE + "/screens.csv", index=False)
    return R


def table_screens(R):
    name = {"ppca": "PPCA ($q=80$)", "ppca_age": "Age-dependent PPCA", "unet": "Graph U-Net",
            "functa": "Functa", "vae": "Partial VAE", "tfm": "Transformer"}
    lines = [r"\begin{tabular}{llrcccccccc}", r"\toprule",
             r"Model & Target & Runs & Overall & Gap & End & Whole & Region & Tensor & NODDI \\", r"\midrule"]
    out = []
    for fam in ["ppca", "ppca_age", "vae", "functa", "unet", "tfm"]:
        for tgt in ["population", "deviations", "hybrid"]:
            x = R[(R.family == fam) & (R.target == tgt)]
            if x.empty:
                continue
            b = x.loc[x.overall.idxmin()]
            out.append(dict(family=fam, target=tgt, n=len(x), **b[["overall", "gap", "end", "whole", "region",
                                                                    "wdti", "wnoddi"]].to_dict()))
            lines.append(r"{} & {} & {} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} & {:.3f} \\".format(
                name[fam], {"population": "--", "deviations": "deviations", "hybrid": "PPCA correction"}[tgt],
                len(x), b.overall, b.gap, b.end, b.whole, b.region, b.wdti, b.wnoddi))
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_screens.tex", "\n".join(lines) + "\n")
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------------------------------------------
# pooling (v10, phase 3b protocol, 11 measures) and continuous age norms

V10 = [("BCP alone, age bins", "B2", C.DEF), ("BCP alone, kernel age norm", "B2",
                                               "population q=80 isotropic [kernel cv] + siren xyz omega0=10"),
       ("Pooled tensor+NODDI, age bins", "Q5", C.DEF),
       ("Pooled tensor+NODDI, kernel age norm", "Q5", "population q=80 isotropic [kernel cv] + siren xyz omega0=10"),
       ("Pooled all measures, age bins", "Q6", C.DEF),
       ("Pooled all measures, kernel age norm", "Q6", "population q=80 isotropic [kernel cv] + siren xyz omega0=10"),
       ("Age norm alone: age-bin mean", "B1", "prior-mean"),
       ("Age norm alone: kernel", "B1", "prior-mean [kernel cv]"),
       ("Age norm alone: spline (6/3 df)", "B1", "prior-mean [spline 6/3]")]


def v10_scores():
    res, scans = {}, {}
    for name, run, st in V10:
        C.S["V10 " + name] = ("v10/" + run, st, "v10/B1")
        d = C.summary("V10 " + name)
        res[name] = d
        scans[name] = C.scan_scores("V10 " + name)
    return res, scans


def table_pooling():
    res, scans = v10_scores()
    lines = [r"\begin{tabular}{lcccc}", r"\toprule",
             r"Setting (11 measures, phase-3b protocol) & Overall (SD) & 0--3 mo & 4--9 mo & 10--60 mo \\",
             r"\midrule"]
    rows = []
    for name, _, _ in V10:
        d = res[name]
        m = d[["overall"] + C.BINS].mean()
        rows.append(dict(setting=name, sd=d.overall.std(), **m.to_dict()))
        lines.append(r"{} & {:.3f} ({:.3f}) & {:.3f} & {:.3f} & {:.3f} \\".format(name, m.overall, d.overall.std(),
                                                                                  *[m[b] for b in C.BINS]))
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_pooling.tex", "\n".join(lines) + "\n")
    comps = [("pooled TN vs alone", "BCP alone, age bins", "Pooled tensor+NODDI, age bins"),
             ("pooled all vs alone", "BCP alone, age bins", "Pooled all measures, age bins"),
             ("kernel vs bins (full)", "BCP alone, age bins", "BCP alone, kernel age norm"),
             ("kernel vs bins (norm)", "Age norm alone: age-bin mean", "Age norm alone: kernel"),
             ("spline vs kernel (norm)", "Age norm alone: kernel", "Age norm alone: spline (6/3 df)")]
    P = {}
    for key, a, b in comps:
        P[key] = C.paired(scans[a], scans[b])
    pd.DataFrame(rows).to_csv(C.CACHE + "/pooling.csv", index=False)
    pd.DataFrame(P).T.to_csv(C.CACHE + "/pooling_paired.csv")
    return pd.DataFrame(rows).set_index("setting"), P


# ----------------------------------------------------------------------------------------------------------------
# calibration of the SDs

CAL = [("Age-bin mean (SD of the bin)", "v15/T", "prior-mean"),
       ("PPCA alone (calibrated)", "v15/T", C.POP),
       ("PPCA + SIREN", "v15/T", C.DEF),
       ("U-Net alone", "v15/E", C.GU),
       ("Transformer alone (400)", "v15/R3", C.TF),
       ("Fixed blend (400)", "v15/R3", C.blend_name(0.25, 0.75)),
       ("Precision blend (400)", "v15/R3", "precision: {}, {}".format(C.DEF, C.TF))]


def table_calibration():
    pats = C.PATS + ["whole measure"]
    lines = [r"\begin{tabular}{l" + "c" * len(pats) + "}", r"\toprule",
             "Setting & " + " & ".join(["Gap", "End", "Whole", "Region", "Family"]) + r" \\", r"\midrule"]
    out = []
    for name, run, st in CAL:
        cells = []
        for p in pats:
            parts = []
            for seed in C.SEEDS:
                d = C.read(run, seed, "validation_calibration.csv")
                x = d[(d.setting == st) & (d.pattern == p) & (d.age_bin == "all") & (d.metric != "all")]
                parts.append(x)
            x = pd.concat(parts)
            g = x.groupby("metric").apply(lambda t: pd.Series({
                "rms": np.sqrt((t.n * t.rms_z ** 2).sum() / t.n.sum()),
                "w": (t.n * t["within_1.96sd"]).sum() / t.n.sum()}), include_groups=False)
            rms, w = g.rms.mean(), g.w.mean()
            out.append(dict(setting=name, pattern=p, rms_z=rms, within=w))
            cells.append("{:.2f} / {:.0f}\\%".format(rms, 100 * w))
        lines.append(name + " & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_calibration.tex", "\n".join(lines) + "\n")
    R = pd.DataFrame(out)
    R.to_csv(C.CACHE + "/calibration.csv", index=False)
    return R


# ----------------------------------------------------------------------------------------------------------------
# blend weight tables (refit from the dumps) and comparison with the tables shipped in impute_profiles.py

def table_weights():
    import sys
    sys.path.insert(0, C.REPO)
    from dtiplayground.dmri.fiberprofile.analysis.impute_profiles import ENSEMBLE_TABLES
    W = pd.read_csv(C.CACHE + "/dump_bcp_weights.csv")
    bands = ["0-0.5", "0.5-1", "1-2", "2-3", "3-4", "4-6", "6-10", "10-20", ">20", "none"]
    maxdiff = 0.0
    lines = [r"\begin{tabular}{ll" + "c" * 10 + "}", r"\toprule",
             r" & & \multicolumn{5}{c}{SIREN cells (mm)} & \multicolumn{4}{c}{Fallback cells (mm)} & \\",
             r"\cmidrule(lr){3-7}\cmidrule(lr){8-11}",
             "Table & Measure & " + " & ".join(b.replace(">", "$>$") for b in bands[:-1]) + r" & Family \\",
             r"\midrule"]
    for ti, t in enumerate(["cohort", "reference"]):
        if ti:
            lines.append(r"\addlinespace[2pt]")
        for mi, m in enumerate(C.METRICS):
            x = W[(W.table == t) & (W.metric == m)].set_index("band").weight.reindex(bands)
            maxdiff = max(maxdiff, float(np.nanmax(np.abs(np.round(x.to_numpy(), 2) - np.array(ENSEMBLE_TABLES[t][m])))))
            lines.append("{} & {} & ".format({"cohort": "BCP", "reference": "BCP+HBCD"}[t] if mi == 0 else "",
                                             C.MLABEL[m]) + " & ".join("{:.2f}".format(v) for v in x) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("tab_weights.tex", "\n".join(lines) + "\n")
    return W, maxdiff


# ----------------------------------------------------------------------------------------------------------------

def main():
    M = table_main().set_index("label")
    for key, label in [("AgeMean", "age-bin mean"), ("PoneArc", "P1 arc-linear, constant ends"),
                       ("PoneSiren", "P1 SIREN xyz"), ("PoneLinear", "P1 linear (3-D)"),
                       ("PtwoSiren", "P2 SIREN xyz"), ("PtwoKnnFifty", "P2 kNN k=50"),
                       ("PtwoArc", "P2 arc-linear, constant ends"),
                       ("Ppca", "P3 PPCA q=80"), ("PpcaKnn", "P3 PPCA q=80 + kNN"), ("Default", "P3 PPCA + SIREN"),
                       ("Unet", "P4 U-Net (deviations+PPCA)"), ("UnetSiren", "P4 U-Net + SIREN"),
                       ("UnetBeyond", "P4 PPCA + SIREN, U-Net beyond"),
                       ("TfTwo", "P6 transformer (200 ep.)"), ("TfFour", "P6 transformer (400 ep.)"),
                       ("TfBeyond", "P6 PPCA + SIREN, transformer beyond"),
                       ("UnetBlend", "P6 U-Net blend 0.25/0.75"), ("TfBlend", "P6 transformer blend 0.25/0.75"),
                       ("TfBlendFour", "P6 transformer 400 blend 0.25/0.75"),
                       ("Final", "D table blend (released default)"), ("RefTf", "D reference transformer"),
                       ("RefFixed", "D reference fixed blend"), ("RefFinal", "D reference table blend")]:
        r = M.loc[label]
        for col, tag in [("overall", ""), ("gap", "Gap"), ("end gap", "End"), ("whole profile", "Whole"),
                         ("region", "Region"), ("whole dti", "Wdti"), ("whole noddi", "Wnoddi")]:
            mac("r" + key + tag, f3(r[col]))
        mac("r" + key + "Sd", "{:.3f}".format(r.sd))
    # other single numbers
    mac("rPpcaTwenty", f3(C.summary("P3 PPCA q=20").overall.mean()))
    mac("rPpcaForty", f3(C.summary("P3 PPCA q=40").overall.mean()))
    mac("rPpcaTwelve", f3(C.summary("P3 PPCA q=120").overall.mean()))
    mac("rPpcaTen", f3(C.summary("P3 PPCA q=10").overall.mean()))
    mac("rPrecisionBlend", f3(C.summary("P6 transformer precision blend").overall.mean()))
    mac("rUnetPrecision", f3(C.summary("P6 U-Net precision blend").overall.mean()))
    for k, lab in [("ZeroHalf", "P6 transformer blend 0/0.5"), ("ZeroThree", "P6 transformer blend 0/0.75"),
                   ("QuarterHalf", "P6 transformer blend 0.25/0.5"), ("HalfHalf", "P6 transformer blend 0.5/0.5")]:
        mac("rTfBlend" + k, f3(C.summary(lab).overall.mean()))
    mac("rAcq", f3(C.summary("P6 acq. correction: default").overall.mean()))
    mac("rPooledDefault", f3(C.summary("P6 pooled: PPCA + SIREN").overall.mean()))
    mac("rPooledDefaultRegion", f3(C.summary("P6 pooled: PPCA + SIREN")["region"].mean()))
    mac("rPooledDefaultWnoddi", f3(C.summary("P6 pooled: PPCA + SIREN")["whole noddi"].mean()))
    mac("rPooledBlend", f3(C.summary("P6 pooled: blend 0.25/0.75").overall.mean()))
    # dump consistency: default from the dumps equals the validation's own score
    mac("rDumpDefault", f3(summary("D default (dump)").overall.mean()))

    P, W = table_paired()
    for i, r in P.iterrows():
        tag = "c" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i]
        mac(tag + "Ratio", "{:.3f}".format(r.ratio))
        mac(tag + "Ci", "{:.3f}--{:.3f}".format(r.lo, r.hi))
        mac(tag + "Bci", "{:.3f}--{:.3f}".format(r.blo, r.bhi))
        mac(tag + "P", C.fmt_p(r.p))
        mac(tag + "Pholm", C.fmt_p(r.p_holm))
        mac(tag + "Psubj", C.fmt_p(r.p_subj_holm))
        mac(tag + "Better", "{:.0f}".format(100 * r.better))
    mac("nPairs", str(int(P.n.max())))
    mac("nSubjPairs", str(int(P.n_subj.max())))
    mac("nContrasts", str(len(P)))
    for i, r in W.iterrows():
        tag = "w" + "ABCD"[i]
        mac(tag + "Ratio", "{:.3f}".format(r.ratio))
        mac(tag + "Better", "{:.0f}".format(100 * r.better))
        mac(tag + "P", C.fmt_p(r.p))
    # distinct scans and subjects in the validation
    sc = C.scan_scores("P3 PPCA + SIREN")
    mac("nScansSeed", str(int(sc.groupby("seed").scan.nunique().iloc[0])))
    mac("nScansDistinct", str(sc.scan.nunique()))
    mac("nSubjDistinct", str(sc.scan.map(C.subject_of).nunique()))
    g = sc[sc.seed == 0].group.value_counts()
    for b, t in zip(C.BINS, "ABC"):
        mac("nScansBin" + t, str(int(g.get(b, 0))))

    S1, t0, b0, t1 = single_seed_screens()
    mac("rSeedZeroTf", f3(t0))
    mac("rSeedZeroBlend", f3(b0))
    mac("rSeedZeroTfRone", f3(t1))
    for _, r in S1.iterrows():
        tag = {"dist": "Dist", "age+acq": "Ctx", "3 members": "Members"}[r.variant]
        mac("x" + tag + "Alone", f3(r.alone))
        mac("x" + tag + "Blend", f3(r.blend))
        mac("x" + tag + "RatioBlend", "{:.3f}".format(r.ratio_blend))
        mac("x" + tag + "PBlend", C.fmt_p(r.p_blend))
        mac("x" + tag + "RatioAlone", "{:.3f}".format(r.ratio_alone))
        mac("x" + tag + "CiBlend", "{:.3f}--{:.3f}".format(r.lo_blend, r.hi_blend))

    PM, absm = table_metric()
    for m in C.METRICS:
        mac("m" + C.MLABEL[m] + "Final", f3(PM.loc[m, "Released default (table blend)"]))
        mac("m" + C.MLABEL[m] + "Default", f3(PM.loc[m, "PPCA + SIREN"]))
        mac("m" + C.MLABEL[m] + "WmPpca", f3(PM.loc[m, "WM PPCA alone"]))
        mac("m" + C.MLABEL[m] + "WmFinal", f3(PM.loc[m, "WM Released default (table blend)"]))
    table_absolute()

    R = parse_screens()
    B = table_screens(R).set_index(["family", "target"])
    mac("sPpca", f3(B.loc[("ppca", "population"), "overall"]))
    mac("sUnet", f3(B.loc[("unet", "hybrid"), "overall"]))
    mac("sFunctaHyb", f3(B.loc[("functa", "hybrid"), "overall"]))
    mac("sFunctaDev", f3(B.loc[("functa", "deviations"), "overall"]))
    mac("sVaeHyb", f3(B.loc[("vae", "hybrid"), "overall"]))
    mac("sVaeDev", f3(B.loc[("vae", "deviations"), "overall"]))
    mac("sAgePpca", f3(B.loc[("ppca_age", "population"), "overall"]))
    mac("sTfHyb", f3(B.loc[("tfm", "hybrid"), "overall"]))
    mac("sTfDev", f3(B.loc[("tfm", "deviations"), "overall"]))
    mac("nFunctaConfigs", str(int(B.loc[("functa", "hybrid"), "n"] + B.loc[("functa", "deviations"), "n"])))
    mac("nScreenResults", str(len(R)))
    ag = R[R.family == "ppca_age"]
    mac("sAgePpcaMax", f3(ag.overall.max()))

    PO, PP = table_pooling()
    for k, lab in [("Alone", "BCP alone, age bins"), ("Kernel", "BCP alone, kernel age norm"),
                   ("TN", "Pooled tensor+NODDI, age bins"), ("All", "Pooled all measures, age bins"),
                   ("NormBins", "Age norm alone: age-bin mean"), ("NormKernel", "Age norm alone: kernel"),
                   ("NormSpline", "Age norm alone: spline (6/3 df)"), ("TNKernel", "Pooled tensor+NODDI, kernel age norm")]:
        mac("v" + k, f3(PO.loc[lab, "overall"]))
        mac("v" + k + "Sd", "{:.3f}".format(PO.loc[lab, "sd"]))
        mac("v" + k + "A", f3(PO.loc[lab, "0-3m"]))
    for k, key in [("TN", "pooled TN vs alone"), ("All", "pooled all vs alone"), ("Kern", "kernel vs bins (full)"),
                   ("KernNorm", "kernel vs bins (norm)"), ("Spline", "spline vs kernel (norm)")]:
        r = PP[key]
        mac("vp" + k + "Ratio", "{:.3f}".format(r["ratio"]))
        mac("vp" + k + "Ci", "{:.3f}--{:.3f}".format(r["lo"], r["hi"]))
        mac("vp" + k + "P", C.fmt_p(r["p"]))

    CB = table_calibration().set_index(["setting", "pattern"])
    for k, lab in [("Ppca", "PPCA alone (calibrated)"), ("Def", "PPCA + SIREN"), ("Tf", "Transformer alone (400)"),
                   ("Blend", "Fixed blend (400)"), ("Unet", "U-Net alone")]:
        for p, t in [("gap", "Gap"), ("whole profile", "Whole"), ("whole measure", "Family"), ("region", "Region")]:
            mac("k" + k + t + "Rms", "{:.2f}".format(CB.loc[(lab, p), "rms_z"]))
            mac("k" + k + t + "In", "{:.0f}".format(100 * CB.loc[(lab, p), "within"]))

    Wt, maxdiff = table_weights()
    mac("weightTableMaxDiff", "{:.2f}".format(maxdiff))
    for t, tag in [("cohort", "C"), ("reference", "R")]:
        x = Wt[Wt.table == t]
        mac("wt" + tag + "NearMin", "{:.2f}".format(x[x.band == "0-0.5"].weight.min()))
        mac("wt" + tag + "NearMax", "{:.2f}".format(x[x.band == "0-0.5"].weight.max()))
        far = x[x.band.isin(["4-6", "6-10", "10-20"])]
        mac("wt" + tag + "FarMin", "{:.2f}".format(far.weight.min()))
        mac("wt" + tag + "FarMax", "{:.2f}".format(far.weight.max()))
        fam = x[x.band == "none"]
        mac("wt" + tag + "FamMin", "{:.2f}".format(fam.weight.min()))
        mac("wt" + tag + "FamMax", "{:.2f}".format(fam.weight.max()))

    # per age bin
    for k, lab in [("Default", "P3 PPCA + SIREN"), ("Ppca", "P3 PPCA q=80"), ("TfBlendFour", "P6 transformer 400 blend 0.25/0.75")]:
        m = C.summary(lab)[C.BINS].mean()
        for b, t in zip(C.BINS, "ABC"):
            mac("r" + k + "Bin" + t, f3(m[b]))
    # share of hidden values within 4 mm of an observed value, per pattern (all settings see the same cells)
    d = pd.concat([C.read("v13/P3", s, "validation_by_distance.csv") for s in C.SEEDS])
    d = d[(d.setting == C.DEF) & (d.metric != "all")].groupby(["pattern", "distance_mm"]).n_hidden.sum()
    for p, t in [("gap", "Gap"), ("end gap", "End"), ("whole profile", "Whole"), ("region", "Region")]:
        x = d.loc[p]
        mac("shareFour" + t, "{:.0f}".format(100 * x.reindex(["0-2", "2-4"]).sum() / x.sum()))
        mac("shareTen" + t, "{:.0f}".format(100 * (1 - x.reindex(["0-2", "2-4", "4-6", "6-10"]).fillna(0).sum() / x.sum())))

    with open(C.TABLES + "/macros.tex", "w") as fh:
        fh.write("% generated by scripts/make_tables.py; do not edit\n")
        fh.writelines(MAC)
    print("".join(MAC))


if __name__ == "__main__":
    main()
