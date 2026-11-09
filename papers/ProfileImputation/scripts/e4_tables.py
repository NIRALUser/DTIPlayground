"""E4 summary: table, figure and macros from cache/e4_<scenario>.csv (e4_downstream.py). Scenarios:
  main      delta 0.3 SD, mask donors = all BCP scans (about half carry a mask, as in BCP)
  d01       delta 0.1 SD, same donors
  d01miss   delta 0.1 SD, donors only among the scans with missing values (every scan carries a mask)
  diff03    differential missingness (round-2 review, N3): delta 0.3 SD planted in group 1, every group-1 scan
            masked (donors with missing values) and no group-0 scan
  diff01    the same with delta 0.1 SD
"Deviation" is the mean absolute difference between the trajectory and the complete-data trajectory (SD of the tract
mean); under random masks it is sampling deviation, not bias. "Est. - full" is the mean difference between the group
estimate and the complete-data estimate in units of the between-scan SD (planted tracts).
Missing scenario files give \\pending{} macros."""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402

MAC = []
PENDING = r"\pending{}"
ORDER = ["complete case", "available case", "age-bin mean", "PPCA", "PPCA + kNN", "blend (table)",
         "multiple imputation (PPCA)"]
TAG = {"complete case": "Cc", "available case": "Ac", "age-bin mean": "Mean", "PPCA": "Ppca", "PPCA + kNN": "Knn",
       "blend (table)": "Blend", "multiple imputation (PPCA)": "Mi"}
SCEN = {"main": "Main", "d01": "Small", "d01miss": "SmallMiss", "diff03": "Diff", "diff01": "DiffSmall"}


def mac(name, value):
    MAC.append(C.macro(name, value))


def summarise(d):
    d = d.copy()
    d["rel_true"] = d.delta / d.true_shift.where(d.true_shift > 0)
    d["rel_full"] = d.delta / d.delta_full.where(d.planted)
    d["se_ratio"] = d.se / d.se_full
    d["diff_sd"] = (d.delta - d.delta_full) / (d.true_shift / d.delta_planted).where(d.planted)
    tr = d[~d.planted].groupby("imputer").agg(bias=("bias", "mean"), ci=("ci_ratio", "mean"),
                                            coverage=("coverage", "mean"), typeI=("reject", "mean"),
                                            n=("n", "mean"))
    pl = d[d.planted].groupby("imputer").agg(rel_true=("rel_true", "mean"), rel_full=("rel_full", "mean"),
                                           se_ratio=("se_ratio", "mean"), power=("reject", "mean"),
                                           diff_sd=("diff_sd", "mean"))
    full_power = d[d.planted & (d.imputer == "PPCA")].assign(r=lambda x: np.abs(x.delta_full / x.se_full) > 1.96)
    out = tr.join(pl)
    out.attrs["full_power"] = float(full_power.r.mean()) if len(full_power) else np.nan
    out.attrs["reps"] = int(d.rep.nunique())
    out.attrs["miss"] = float(d[d.planted & (d.imputer == "PPCA")].missing_share.mean())
    return out.reindex(ORDER)


def main():
    res = {}
    for scen, tag in SCEN.items():
        f = "{}/e4_{}.csv".format(C.CACHE, scen)
        if os.path.isfile(f):
            res[scen] = summarise(pd.read_csv(f))
        for imp, t in TAG.items():
            for col in ("bias", "ci", "coverage", "typeI", "rel_true", "rel_full", "se_ratio", "power", "n",
                        "diff_sd"):
                v = res[scen].loc[imp, col] if scen in res else np.nan
                fmt = "{:.0f}" if col == "n" else ("{:.1f}" if col == "typeI" else
                                                  ("{:.0f}" if col in ("coverage", "power") else "{:.3f}"))
                val = (PENDING if scen not in res else "--") if not np.isfinite(v) else (fmt.format(100 * v) if col in ("coverage", "typeI", "power")
                                                         else fmt.format(v))
                mac("ef" + tag + t + col.replace("_", "").capitalize(), val)
        mac("ef" + tag + "MissShare", "{:.1f}".format(100 * res[scen].attrs["miss"]) if scen in res else PENDING)
        mac("ef" + tag + "Reps", str(res[scen].attrs["reps"]) if scen in res else PENDING)
        mac("ef" + tag + "FullPower", "{:.0f}".format(100 * res[scen].attrs["full_power"]) if scen in res else PENDING)
    # table
    lines = [r"\begin{tabular}{llcccccccc}", r"\toprule",
             r" & & \multicolumn{3}{c}{Trajectories (no effect planted)} & & \multicolumn{4}{c}{Planted group effect} \\",
             r"\cmidrule(lr){3-5}\cmidrule(lr){7-10}",
             r"Scenario & Imputer & Deviation (SD) & CI width & Coverage & Type I & Est.\,$-$\,full (SD) & Est.\,/\,full & SE / full & Power \\",
             r"\midrule"]
    names = {"main": r"$\delta=0.3$, prevalence", "d01": r"$\delta=0.1$, prevalence",
             "d01miss": r"$\delta=0.1$, all masked", "diff03": r"$\delta=0.3$, group 1 masked",
             "diff01": r"$\delta=0.1$, group 1 masked"}
    for si, scen in enumerate(SCEN):
        if si:
            lines.append(r"\addlinespace[2pt]")
        if scen not in res:
            lines.append(r"{} & \multicolumn{{9}}{{c}}{{{}}} \\".format(names[scen], PENDING))
            continue
        R = res[scen]
        for k, imp in enumerate(ORDER):
            r = R.loc[imp]
            if not np.isfinite(r.bias):
                lines.append(r"{} & {} & \multicolumn{{8}}{{c}}{{every scan excluded}} \\".format(
                    names[scen] if k == 0 else "", imp))
                continue
            def f(v, fmt, scale=1.0, pct=False):
                return "--" if not np.isfinite(v) else fmt.format(scale * v) + ("\\%" if pct else "")
            lines.append(" & ".join([names[scen] if k == 0 else "", imp, f(r.bias, "{:.3f}"), f(r.ci, "{:.2f}"),
                                     f(r.coverage, "{:.0f}", 100, True), f(r.typeI, "{:.1f}", 100, True),
                                     f(r.diff_sd, "{:+.3f}"), f(r.rel_full, "{:.3f}"), f(r.se_ratio, "{:.2f}"),
                                     f(r.power, "{:.0f}", 100, True)]) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    C.write_tex("e4.tex", "\n".join(lines) + "\n")
    with open(C.TABLES + "/macros_e4.tex", "w") as fh:
        fh.write("% generated by scripts/e4_tables.py\n")
        fh.writelines(MAC)
    # figure
    if res:
        plt.rcParams.update({"font.size": 7, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "font.family": "DejaVu Sans",
                             "pdf.fonttype": 42})
        fig, axs = plt.subplots(1, 3, figsize=(7.0, 3.0), sharey=True, gridspec_kw=dict(wspace=0.12))
        cols = [C.OI["grey"], C.OI["sky"], C.OI["orange"], C.OI["green"], C.OI["blue"], C.OI["black"], C.OI["pink"]]
        for ax, col, lab in [(axs[0], "bias", "Trajectory deviation (SD of tract mean)"),
                             (axs[1], "diff_sd", "Group effect: estimate - full data (SD)"),
                             (axs[2], "power", "Power (alpha 0.05)")]:
            for si, scen in enumerate(res):
                R = res[scen]
                for k, imp in enumerate(ORDER):
                    ax.scatter(R.loc[imp, col], si + (k - 3) * 0.1, color=cols[k], s=12,
                               label=imp if (si == 0 and ax is axs[0]) else None)
            ax.set_yticks(range(len(res)))
            ax.set_yticklabels([{"main": "delta 0.3", "d01": "delta 0.1", "d01miss": "delta 0.1,\nall masked",
                                "diff03": "delta 0.3,\ngroup 1 masked", "diff01": "delta 0.1,\ngroup 1 masked"}[s] for s in res], fontsize=6)
            ax.set_xlabel(lab, fontsize=6.5)
            if col == "diff_sd":
                ax.axvline(0.0, color="#505050", lw=0.6, ls="--")
            elif col == "bias":
                ax.set_xlim(0, None)
            else:
                ax.set_xlim(0, 1.02)
            ax.grid(axis="x", color="0.9")
        fig.legend(frameon=False, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.25), fontsize=6)
        fig.savefig(C.FIGURES + "/fig_e4.pdf", bbox_inches="tight")
        fig.savefig(C.FIGURES + "/fig_e4.png", bbox_inches="tight", dpi=200)
    print("".join(MAC))


if __name__ == "__main__":
    main()
