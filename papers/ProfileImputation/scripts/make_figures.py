"""All figures of the paper (figures/*.pdf). Run make_tables.py first (it writes the caches used here).
Usage: python make_figures.py [name ...]   (default: all)"""
import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

import common as C  # noqa: E402

plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5, "legend.fontsize": 6.5,
                     "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.linewidth": 0.6, "xtick.major.width": 0.6,
                     "ytick.major.width": 0.6, "lines.linewidth": 1.2, "pdf.fonttype": 42,
                     "font.family": "DejaVu Sans", "axes.grid": False, "savefig.dpi": 300})
FULL, HALF = 7.0, 3.4
GRID = dict(color="#d9d9d9", lw=0.4, zorder=0)


def save(fig, name):
    fig.savefig(os.path.join(C.FIGURES, name + ".pdf"), bbox_inches="tight")
    fig.savefig(os.path.join(C.FIGURES, name + ".png"), bbox_inches="tight", dpi=200)
    plt.close(fig)
    print("wrote", name)


def load_cohort():
    sys.path.insert(0, C.REPO)
    from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip
    tables = ip.read_tables(C.BCP_DIR)
    c = ip.Cohort(tables, ip.read_axes(C.AXIS_DIR, sorted({t.tract for t in tables})))
    return ip, c


# ----------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------
def metric_pattern(label):
    """metric x pattern ratio matrix (mean over age bins and seeds), with the whole-measure column."""
    sys.path.insert(0, os.path.dirname(__file__))
    import make_tables as T
    if label in T.DUMP_LABEL:
        d = T.DUMP_DIST[T.DUMP_DIST.setting == T.DUMP_LABEL[label]]
        a = d.groupby(["seed", "pattern", "metric", "age_bin"])[["e2", "r2"]].sum()
        q = np.sqrt(a.e2 / a.r2).rename("r").reset_index()
    else:
        q = pd.concat([C.cell_ratios(label, s).assign(seed=s) for s in C.SEEDS])
    m = q.groupby(["seed", "pattern", "metric"]).r.mean().groupby(["pattern", "metric"]).mean().unstack(0)
    cols = C.PATS + ["whole measure"]
    return m.reindex(index=C.METRICS, columns=cols)


def fig_metric_heat():
    sets = [("(a) P2: SIREN, deviations", "P2 SIREN xyz"), ("(b) P3: PPCA + SIREN", "P3 PPCA + SIREN"),
            ("(c) Transformer (400 ep.)", "D transformer 400 (dump)"),
            ("(d) Released default", "D table blend (released default)")]
    fig, axs = plt.subplots(1, 4, figsize=(FULL, 2.3), sharey=True, gridspec_kw=dict(wspace=0.08))
    cmap = plt.get_cmap("cividis_r")
    for ax, (title, lab) in zip(axs, sets):
        m = metric_pattern(lab)
        im = ax.imshow(m.to_numpy(), cmap=cmap, vmin=0.25, vmax=1.0, aspect="auto")
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m.iat[i, j]
                ax.text(j, i, "{:.2f}".format(v), ha="center", va="center", fontsize=5.6,
                        color="white" if v > 0.62 else "black")
        ax.set_xticks(range(m.shape[1]))
        ax.set_xticklabels(["Gap", "End", "Whole", "Region", "Family"], rotation=45, ha="right")
        ax.set_yticks(range(m.shape[0]))
        ax.set_yticklabels([C.MLABEL[x] for x in m.index])
        ax.set_title(title, fontsize=7)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(length=0)
    cb = fig.colorbar(im, ax=axs, fraction=0.02, pad=0.01)
    cb.set_label("RMSE / RMSE of the age-bin mean")
    cb.outline.set_linewidth(0.4)
    save(fig, "fig_metric_heat")


# ----------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------
def fig_paired():
    P = pd.read_csv(C.CACHE + "/paired.csv")
    lab = {}
    for _, r in P.iterrows():
        lab[r.contrast] = re.sub(r"\$|\\,", "", r.contrast).replace("\\leq", "≤").replace("q=", "q = ")
    fig, ax = plt.subplots(figsize=(HALF + 1.6, 4.2))
    y = np.arange(len(P))[::-1]
    fams = list(dict.fromkeys(P.family))
    fam_col = dict(zip(fams, [C.OI["orange"], C.OI["green"], C.OI["red"], C.OI["blue"], C.OI["grey"],
                              C.OI["pink"]]))
    for i, r in P.iterrows():
        ax.plot([r.blo, r.bhi], [y[i], y[i]], color="#9a9a9a", lw=2.6, solid_capstyle="butt", zorder=1)
        ax.plot([r.lo, r.hi], [y[i], y[i]], color=fam_col[r.family], lw=1.0, zorder=2)
        ax.scatter(r.ratio, y[i], s=12, color=fam_col[r.family], zorder=3)
    ax.axvline(1.0, color="#505050", lw=0.6, ls="--")
    ax.set_xscale("log")
    ticks = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t) for t in ticks])
    ax.minorticks_off()
    ax.set_yticks(y)
    ax.set_yticklabels([lab[c] for c in P.contrast])
    ax.set_xlabel("Geometric mean ratio of per-scan errors\n(compared / reference; < 1: compared is better)")
    ax.grid(axis="x", **GRID)
    for k, f in enumerate(fams):
        ax.scatter([], [], color=fam_col[f], s=12, label=f)
    ax.plot([], [], color="#9a9a9a", lw=2.6, label="95% CI, subject bootstrap")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=5.8)
    save(fig, "fig_paired")


# ----------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------
def fig_screens():
    R = pd.read_csv(C.CACHE + "/screens.csv")
    groups = [("Age-dep. PPCA", "ppca_age", "population"), ("Partial VAE\n(deviations)", "vae", "deviations"),
              ("Partial VAE\n(hybrid)", "vae", "hybrid"), ("Functa\n(deviations)", "functa", "deviations"),
              ("Functa\n(hybrid)", "functa", "hybrid"), ("Transformer\n(deviations)", "tfm", "deviations"),
              ("Transformer\n(hybrid)", "tfm", "hybrid")]
    fig, ax = plt.subplots(figsize=(FULL * 0.72, 2.3))
    rng = np.random.default_rng(0)
    for i, (name, fam, tgt) in enumerate(groups):
        x = R[(R.family == fam) & (R.target == tgt)].overall
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(x)), x, s=7, color=C.OI["blue"], alpha=0.6, lw=0)
        ax.scatter(i, x.min(), marker="_", s=120, color="black", lw=1.0)
    ppca = R[R.family == "ppca"].overall.iloc[0]
    unet = R[R.family == "unet"].overall.iloc[0]
    ax.axhline(ppca, color=C.OI["orange"], lw=0.9, ls="--", label="PPCA alone ({:.3f})".format(ppca))
    ax.axhline(unet, color=C.OI["green"], lw=0.9, ls="--", label="Hybrid graph U-Net ({:.3f})".format(unet))
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([g[0] for g in groups], fontsize=6)
    ax.set_ylabel("Overall RMSE / age-bin mean\n(held-out screen)")
    ax.legend(frameon=False, loc="upper right", fontsize=6)
    ax.grid(axis="y", **GRID)
    save(fig, "fig_screens")


# ----------------------------------------------------------------------------------------------------------------
def fig_siren_grid():
    d = pd.read_csv(C.REPO + "/docs/_static/impute_validation/phase2/stratified_overall.csv")
    rx = re.compile(r"siren (\S+) omega0=(\d+) \(z\) e=(\d+)")
    rows = []
    for _, r in d.iterrows():
        m = rx.match(r.key)
        if m:
            rows.append(dict(inputs=m.group(1), omega=int(m.group(2)), epochs=int(m.group(3)),
                             **{p: r[p] for p in C.PATS}))
    G = pd.DataFrame(rows)
    fig, axs = plt.subplots(3, 4, figsize=(FULL, 4.2), sharex=True, gridspec_kw=dict(hspace=0.35, wspace=0.3))
    oc = {5: C.OI["sky"], 10: C.OI["blue"], 20: C.OI["orange"], 30: C.OI["red"]}
    for i, inp in enumerate(["xyz", "xyz+arc", "xyz+tract"]):
        for j, p in enumerate(C.PATS):
            ax = axs[i, j]
            for om in (5, 10, 20, 30):
                x = G[(G.inputs == inp) & (G.omega == om)].sort_values("epochs")
                ax.plot(x.epochs, x[p], color=oc[om], marker="o", ms=2.5, label="$\\omega_0$ = {}".format(om))
            ax.set_xscale("log")
            ax.set_xticks([100, 200, 500, 1000])
            ax.set_xticklabels(["100", "200", "500", "1000"])
            ax.minorticks_off()
            ax.grid(axis="y", **GRID)
            if i == 0:
                ax.set_title(C.PAT_LABEL[p])
            if j == 0:
                ax.set_ylabel("{}\nRMSE / age-bin mean".format(inp))
            if i == 2:
                ax.set_xlabel("Epochs")
    axs[0, 0].legend(frameon=False, fontsize=5.6)
    save(fig, "fig_siren_grid")


def fig_cap():
    d = pd.read_csv(C.REPO + "/docs/_static/impute_validation/phase3/grid_caps_long.csv")
    fig, axs = plt.subplots(1, 4, figsize=(FULL, 1.9), sharey=False, gridspec_kw=dict(wspace=0.32))
    caps = [2, 4, 6, 10, 15, 20, 25, np.inf]
    for ax, p in zip(axs, C.PATS):
        for st, name, col in [("population q=80 isotropic + siren xyz omega0=10", "PPCA + SIREN", C.OI["blue"]),
                              ("population q=80 isotropic + knn k=20", "PPCA + kNN", C.OI["green"]),
                              ("knn k=20 distance (z)", "kNN on deviations", C.OI["orange"])]:
            x = d[(d.setting == st) & (d.pattern == p)].set_index("cap").ratio.reindex(caps)
            ax.plot(range(len(caps)), x, color=col, marker="o", ms=2.5, label=name)
        ax.set_xticks(range(len(caps)))
        ax.set_xticklabels(["2", "4", "6", "10", "15", "20", "25", "none"], rotation=45)
        ax.set_title(C.PAT_LABEL[p])
        ax.set_xlabel("Distance limit (mm)")
        ax.grid(axis="y", **GRID)
    axs[0].set_ylabel("RMSE / age-bin mean")
    axs[0].legend(frameon=False, fontsize=5.6)
    save(fig, "fig_cap")


def fig_patterns():
    """(a, b) one validation round of hidden patterns on a BCP scan, (c) the evaluation protocol."""
    import copy
    ip, c = load_cohort()
    s = c.scans.index(next(x for x in c.scans if "ses-012m" in x))
    Y = c.scan(s)
    # the first draw whose region hides the median number of tracts of a region in the validation (13 of 69)
    for k in range(100):
        rng = np.random.default_rng(k)
        hid = ip.hide(c, Y, rng, 0.2, (3.0, 15.0), 0.1, 0.2, (1.0, 8.0))
        r2 = copy.deepcopy(rng)
        reg = ip.hide_region(c, Y, rng, (10.0, 25.0), 1)
        if len(np.unique(c.tract_of[list(reg)])) == 13:
            break
    # the sphere of that draw (replays hide_region's draws)
    observed = (~np.isnan(Y) & c.valid).any(axis=1) & c.has_point
    obs = np.flatnonzero(observed)
    n_tracts = len(np.unique(c.tract_of[obs]))
    for _ in range(10):
        center = c.points[r2.choice(obs)]
        radius = r2.uniform(10.0, 25.0)
        inside = observed & (np.linalg.norm(c.points - center, axis=1) <= radius)
        if len(np.unique(c.tract_of[inside])) <= ip.REGION_MAX_SHARE * n_tracts:
            break
    lab = np.full(c.n_positions, "observed", dtype=object)
    for k, v in hid.items():
        lab[k] = v
    region = np.full(c.n_positions, False)
    region[list(reg)] = True
    P = c.points
    fig = plt.figure(figsize=(FULL, 3.0))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.55], wspace=0.22)
    # atlas space: +x right, +y anterior, +z superior (left tracts at smaller x, the genu at larger y)
    views = [((0, 1), ("L", "R", "P", "A"), "pass 1"), ((1, 2), ("P", "A", "I", "S"), "pass 2")]
    for i, ((a, b), (xl, xr, yb, yt), which) in enumerate(views):
        ax = fig.add_subplot(gs[i])
        obsp = c.has_point
        ax.scatter(P[obsp, a], P[obsp, b], s=0.4, c="#c8c8c8", lw=0, rasterized=True)
        if which == "pass 1":
            for pat in ["whole profile", "gap", "end gap"]:
                m = (lab == pat) & obsp
                ax.scatter(P[m, a], P[m, b], s=2.0, c=C.PAT_COLOR[pat], lw=0, label=C.PAT_LABEL[pat],
                           rasterized=True)
            ax.set_title("(a) Pass 1, axial view", loc="left", pad=12)
        else:
            ax.scatter(P[region & obsp, a], P[region & obsp, b], s=2.0, c=C.PAT_COLOR["region"], lw=0,
                       label="Region ({} tracts)\nin a sphere, r = {:.0f} mm".format(
                           len(np.unique(c.tract_of[list(reg)])), radius), rasterized=True)
            ax.add_patch(plt.Circle((center[a], center[b]), radius, fill=False, ls="--", lw=0.7, ec="#404040"))
            ax.set_title("(b) Pass 2, sagittal view", loc="left", pad=12)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        x0, x1 = np.nanmin(P[:, a]), np.nanmax(P[:, a])
        y0, y1 = np.nanmin(P[:, b]), np.nanmax(P[:, b])
        ym = (y0 + y1) / 2
        xm = (x0 + x1) / 2
        ax.text(x0 - 6, ym, xl, ha="right", va="center", fontsize=7, fontweight="bold")
        ax.text(x1 + 6, ym, xr, ha="left", va="center", fontsize=7, fontweight="bold")
        ax.text(xm, y1 + 4, yt, ha="center", va="bottom", fontsize=7, fontweight="bold")
        ax.text(xm, y0 - 4, yb, ha="center", va="top", fontsize=7, fontweight="bold")
        ax.plot([x1 - 20, x1], [y0 - 2, y0 - 2], color="black", lw=1.2)
        ax.text(x1 - 10, y0 - 4, "20 mm", ha="center", va="top", fontsize=5.5)
        ax.legend(loc="upper left", frameon=False, markerscale=3, handletextpad=0.2, borderaxespad=0,
                  bbox_to_anchor=(0.0, -0.02), fontsize=6)
    ax = fig.add_subplot(gs[2])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("(c) Evaluation protocol", loc="left")
    boxes = [(0.2, 8.3, 9.6, 1.3, "BCP: 423 scans, 208 subjects\n69 tracts, 5,388 locations, 7 measures"),
             (0.2, 6.35, 4.6, 1.55, "Sample per seed:\n20 scans per age bin\n(at most half a bin)"),
             (5.2, 6.35, 4.6, 1.55, "5 folds by subject:\nnorm and models fitted\nwithout the subject"),
             (0.2, 3.85, 9.6, 2.1, "3 rounds per scan, passes per round:\n"
                                    "1: whole profiles (10% of tracts), gaps (20%,\n3-15 mm), end gaps (20%, 1-8 mm)\n"
                                    "2: all tracts through a sphere (r 10-25 mm)\n3: one measure family; 4: a real mask"),
             (0.2, 1.95, 9.6, 1.5, "Impute with every setting\n(same hidden values for all settings)"),
             (0.2, 0.05, 9.6, 1.5, "RMSE / RMSE of the age-bin mean per\npattern, measure, age bin; paired per scan")]
    for x, y, w, h, t in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.25", fc="#f2f2f2",
                                    ec="#7f7f7f", lw=0.6))
        ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=5.8, linespacing=1.2)
    for (x0, y0, x1, y1) in [(2.5, 8.3, 2.5, 7.9), (7.5, 8.3, 7.5, 7.9), (2.5, 6.35, 2.5, 5.95), (7.5, 6.35, 7.5, 5.95),
                             (5, 3.85, 5, 3.45), (5, 1.95, 5, 1.55)]:
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", lw=0.6, color="#505050"))
    save(fig, "fig_patterns")


# ----------------------------------------------------------------------------------------------------------------
def fig_data():
    from scipy import stats
    b = pd.read_csv(C.CACHE + "/desc_ages_BCP.csv")
    h = pd.read_csv(C.CACHE + "/desc_ages_HBCD.csv")
    rej = pd.read_csv(C.CACHE + "/desc_rejected_by_tract.csv", index_col=0).share
    prox = pd.read_csv(C.CACHE + "/desc_axis_proximity.csv", index_col=0).median_mm
    M = pd.read_csv(C.CACHE + "/desc_missing_BCP.csv")
    per_scan = M[M.kind == "whole"].groupby(["scan", "tract"]).size().groupby("scan").size()
    n_scans = len(b)
    fig, axs = plt.subplots(1, 3, figsize=(FULL, 2.1), gridspec_kw=dict(width_ratios=[1.25, 1, 1], wspace=0.38))
    ax = axs[0]
    edges = np.arange(-2, 67, 1.0)
    ax.hist(h.age.dropna(), bins=edges, color=C.OI["orange"], alpha=0.85, label="HBCD (n = {:,})".format(len(h)))
    ax.hist(b.age.dropna(), bins=edges, color=C.OI["blue"], alpha=0.85, label="BCP (n = {:,})".format(len(b)))
    ax.set_yscale("log")
    for x in (3.5, 9.5):
        ax.axvline(x, color="#505050", lw=0.6, ls="--")
    tr = ax.get_xaxis_transform()
    ax.text(1.5, 1.0, "0-3", ha="center", fontsize=5.5, transform=tr)
    ax.text(6.5, 0.92, "4-9", ha="center", fontsize=5.5, transform=tr)
    ax.text(30, 1.0, "10-60 months", ha="center", fontsize=5.5, transform=tr)
    ax.set_xlabel("Age at scan (months)")
    ax.set_ylabel("Scans per month of age (log)")
    ax.legend(frameon=False, loc="center right")
    ax.set_title("(a) Ages and age bins", loc="left", pad=10)
    ax = axs[1]
    counts = per_scan.value_counts().sort_index()
    zero = n_scans - len(per_scan)
    ks = np.arange(0, 21)
    v = [zero] + [int(counts.get(k, 0)) for k in ks[1:]]
    ax.bar(ks, v, color=C.OI["blue"], width=0.8)
    more = int(per_scan[per_scan > 20].count())
    ax.text(20, max(v) * 0.15, "+{} scans\nwith > 20".format(more), ha="right", fontsize=5.5)
    ax.set_yscale("log")
    ax.set_xlabel("Rejected tracts per scan")
    ax.set_ylabel("BCP scans (log)")
    ax.set_title("(b) Real missingness per scan", loc="left")
    ax = axs[2]
    rho, p = stats.spearmanr(prox.reindex(rej.index), rej)
    ax.scatter(prox.reindex(rej.index), 100 * rej, s=8, color=C.OI["blue"], lw=0)
    ax.set_xlabel("Median distance of a tract's axis\nto the nearest other tract (mm)")
    ax.set_ylabel("Scans with the tract rejected (%)")
    ax.set_title("(c) Rejection rate per tract", loc="left")
    ax.text(0.97, 0.6, "Spearman {:.2f}\n(p = {:.2f})".format(rho, p), transform=ax.transAxes, ha="right",
            va="top", fontsize=5.8)
    t = rej.idxmax()
    ax.annotate(t.replace("_", " "), (prox[t], 100 * rej[t]), fontsize=5.5, xytext=(4, 0),
                textcoords="offset points", va="center")
    ax.grid(axis="y", **GRID)
    save(fig, "fig_data")


# ----------------------------------------------------------------------------------------------------------------
PROG = [("Age-bin mean", "age-bin mean"),
        ("Own values: arc-linear, constant ends", "P1 arc-linear, constant ends"),
        ("Own values: SIREN (xyz)", "P1 SIREN xyz"),
        ("Deviations: kNN, k = 50", "P2 kNN k=50"),
        ("Deviations: SIREN (xyz)", "P2 SIREN xyz"),
        ("PPCA alone", "P3 PPCA q=80"),
        ("PPCA + kNN on residuals", "P3 PPCA q=80 + kNN"),
        ("PPCA + SIREN on residuals", "P3 PPCA + SIREN"),
        ("Graph U-Net alone (hybrid)", "P4 U-Net (deviations+PPCA)"),
        ("Transformer alone (hybrid)", "P6 transformer (400 ep.)"),
        ("Blend with U-Net, fixed weights", "P6 U-Net blend 0.25/0.75"),
        ("Blend with transformer, fixed", "P6 transformer 400 blend 0.25/0.75"),
        ("Blend, weight table (released)", "D table blend (released default)"),
        ("Blend, HBCD-trained transformer", "D reference table blend")]
PROG_GROUPS = [1, 3, 5, 8, 10]  # rows after which a family boundary is drawn


def fig_progression():
    M = pd.read_csv(C.CACHE + "/main_table.csv").set_index("label")
    fig, axs = plt.subplots(1, 2, figsize=(FULL, 3.4), sharey=True,
                            gridspec_kw=dict(width_ratios=[2.2, 1], wspace=0.06))
    y = np.arange(len(PROG))[::-1]
    for ax, pats, title in [(axs[0], C.PATS, "(a) Four patterns"),
                            (axs[1], ["whole dti", "whole noddi"], "(b) Whole measure family")]:
        for i, (name, lab) in enumerate(PROG):
            r = M.loc[lab]
            if ax is axs[0]:
                ax.scatter(r["overall"], y[i], marker="|", s=90, color="black", lw=1.4, zorder=4,
                           label="Overall (mean of 4 patterns)" if i == 0 else None)
            for p in pats:
                v = r[p]
                if np.isfinite(v):
                    ax.scatter(v, y[i], marker=C.PAT_MARKER[p], s=18, color=C.PAT_COLOR[p], zorder=3,
                               edgecolor="white", lw=0.4, label=C.PAT_LABEL[p] if i == 0 else None)
        ax.axvline(1.0, color="#505050", lw=0.6, ls="--", zorder=2)
        ax.set_title(title, loc="left")
        ax.grid(axis="x", **GRID)
        ax.set_xlabel("RMSE relative to the age-bin mean")
    axs[0].set_xlim(0, 2.45)
    axs[1].set_xlim(0, 1.05)
    axs[0].set_yticks(y)
    axs[0].set_yticklabels([p[0] for p in PROG])
    axs[0].legend(frameon=False, loc="lower right", ncol=1)
    axs[1].legend(frameon=False, loc="upper left", bbox_to_anchor=(0.0, 0.97))
    for ax in axs:
        for g in PROG_GROUPS:
            ax.axhline(y[g - 1] - 0.5, color="#a0a0a0", lw=0.4)
    save(fig, "fig_progression")


# ----------------------------------------------------------------------------------------------------------------
DIST_SETTINGS = [("Deviations: SIREN", "v13/P12", "siren xyz omega0=10 (z)", C.OI["sky"], ":"),
                 ("PPCA alone", "v13/P3", C.POP, C.OI["orange"], "-"),
                 ("PPCA + kNN", "v13/P3", C.POP + " + knn k=20", C.OI["yellow"], "-"),
                 ("PPCA + SIREN", "v13/P3", C.DEF, C.OI["blue"], "-"),
                 ("Graph U-Net alone", "v12/S", C.GU, C.OI["green"], "--"),
                 ("Transformer alone", "v15/R3", C.TF, C.OI["red"], "--"),
                 ("Blend, fixed 0.25/0.75", "v15/R3", C.blend_name(0.25, 0.75), C.OI["black"], "-")]
DIST_ORDER = ["0-2", "2-4", "4-6", "6-10", "10-15", "15-20", "20-25", ">25"]


def by_distance(run, st):
    parts = [C.read(run, s, "validation_by_distance.csv") for s in C.SEEDS]
    d = pd.concat(parts)
    d = d[(d.setting == st) & (d.metric != "all")]
    a = d.groupby(["pattern", "metric", "distance_mm"])[["nsse_paired_age", "nsse_age_mean", "n_hidden"]].sum()
    a["r"] = np.sqrt(a.nsse_paired_age / a.nsse_age_mean)
    out = a.groupby(["pattern", "distance_mm"]).agg(r=("r", "mean"), n=("n_hidden", "sum"))
    return out


def fig_distance():
    order = DIST_ORDER
    fig, axs = plt.subplots(1, 5, figsize=(FULL, 2.3), sharey=False, gridspec_kw=dict(wspace=0.38))
    tabs = {name: by_distance(run, st) for name, run, st, _, _ in DIST_SETTINGS}
    titles = {"gap": "(a) Interior gaps", "end gap": "(b) End gaps", "whole profile": "(c) Whole profiles",
              "region": "(d) Regions"}
    for ax, pat in zip(axs[:4], C.PATS):
        for name, run, st, col, ls in DIST_SETTINGS:
            t = tabs[name].loc[pat]
            t = t.reindex([o for o in order if o in t.index])
            t = t[t.n >= 200 * 3]
            x = [order.index(o) for o in t.index]
            ax.plot(x, t.r, color=col, ls=ls, marker="o", ms=2.3, label=name,
                    mec="#606060" if col == C.OI["yellow"] else col, mew=0.3)
        ax.axhline(1.0, color="#505050", lw=0.6, ls=":")
        ax.axvline(1.5, color="#a0a0a0", lw=0.5)
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels(order, rotation=60, ha="right", fontsize=5.8)
        ax.set_title(titles[pat], loc="left")
        ax.grid(axis="y", **GRID)
        ax.set_xlim(-0.4, 7.4)
    axs[0].set_ylabel("RMSE / RMSE of the age-bin mean")
    fig.text(0.42, -0.08, "Distance from the hidden value to the nearest observed value of the same measure (mm)",
             ha="center", fontsize=7)
    h, l = axs[2].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, loc="lower center", ncol=7, bbox_to_anchor=(0.45, -0.2), fontsize=6)
    ax = axs[4]
    t = tabs["PPCA + SIREN"]
    w = 0.2
    for k, pat in enumerate(C.PATS):
        s = t.loc[pat].reindex(order).n.fillna(0)
        ax.bar(np.arange(len(order)) + (k - 1.5) * w, 100 * s / s.sum(), width=w, color=C.PAT_COLOR[pat],
               label=C.PAT_LABEL[pat])
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order, rotation=60, ha="right", fontsize=5.8)
    ax.set_ylabel("Share of hidden values (%)")
    ax.set_title("(e) Distances", loc="left")
    ax.legend(frameon=False, fontsize=5.4)
    save(fig, "fig_distance")


# ----------------------------------------------------------------------------------------------------------------
def fig_weights():
    W = pd.read_csv(C.CACHE + "/dump_bcp_weights.csv")
    D = pd.read_csv(C.CACHE + "/dump_bcp_cells.csv")
    bands = ["0-0.5", "0.5-1", "1-2", "2-3", "3-4", "4-6", "6-10", "10-20", ">20", "none"]
    cols = dict(zip(C.METRICS, [C.OI["blue"], C.OI["sky"], C.OI["green"], C.OI["yellow"], C.OI["orange"],
                                C.OI["red"], C.OI["pink"]]))
    marks = dict(zip(C.METRICS, ["o", "s", "D", "^", "v", "P", "X"]))
    fig, axs = plt.subplots(1, 3, figsize=(FULL, 2.3), gridspec_kw=dict(wspace=0.45, width_ratios=[1, 1, 1.1]))
    for ax, t, title in [(axs[0], "cohort", "(a) Transformer trained on BCP"),
                         (axs[1], "reference", "(b) Transformer trained on BCP+HBCD")]:
        for m in C.METRICS:
            x = W[(W.table == t) & (W.metric == m)].set_index("band").weight.reindex(bands)
            ax.plot(range(len(bands)), x, color=cols[m], marker=marks[m], ms=3, lw=0.9, label=C.MLABEL[m],
                    mec="#404040" if m == "ad" else cols[m], mew=0.3)
        ax.axvline(4.5, color="#a0a0a0", lw=0.5)
        ax.axvline(8.5, color="#a0a0a0", lw=0.5)
        ax.text(2, 1.03, "SIREN cells", ha="center", fontsize=6)
        ax.text(6.5, 1.03, "fallback cells", ha="center", fontsize=6)
        ax.set_ylim(0, 1.08)
        ax.set_xticks(range(len(bands)))
        ax.set_xticklabels(bands, rotation=45, ha="right")
        ax.set_xlabel("Distance (mm)")
        ax.set_title(title, loc="left", fontsize=7)
        ax.grid(axis="y", **GRID)
    axs[0].set_ylabel("Transformer weight $w$")
    axs[0].legend(frameon=False, ncol=2, loc="lower right", fontsize=5.6)
    ax = axs[2]
    for lab, name, col, ls in [("PPCA + SIREN", "PPCA + SIREN", C.OI["blue"], "-"),
                               ("transformer", "Transformer (BCP)", C.OI["red"], "--"),
                               ("table (cross-fitted)", "Table blend (released)", C.OI["black"], "-"),
                               ("reference table (cross-fitted)", "Table blend (HBCD ref.)", C.OI["green"], "-")]:
        d = D[(D.setting == lab) & D.pattern.isin(C.PATS) & (D.dbin >= 0)]
        a = d.groupby(["metric", "dbin"])[["e2", "r2", "n"]].sum()
        a["r"] = np.sqrt(a.e2 / a.r2)
        g = a.groupby("dbin").agg(r=("r", "mean"), n=("n", "sum"))
        g = g[g.n >= 2000]
        ax.plot(g.index, g.r, color=col, ls=ls, marker="o", ms=2.3, label=name)
    ax.axvline(1.5, color="#a0a0a0", lw=0.5)
    ax.set_xticks(range(len(DIST_ORDER)))
    ax.set_xticklabels(DIST_ORDER, rotation=45, ha="right")
    ax.set_xlabel("Distance (mm)")
    ax.set_ylabel("RMSE / RMSE of the age-bin mean")
    ax.set_title("(c) Error by distance (4 patterns)", loc="left", fontsize=7)
    ax.legend(frameon=False, fontsize=5.6, loc="lower right")
    ax.grid(axis="y", **GRID)
    save(fig, "fig_weights")


# ----------------------------------------------------------------------------------------------------------------
AGE_GROUPS = [(0, 2), (2, 4), (4, 7), (7, 10), (10, 15), (15, 24), (24, 36), (36, 70)]


def fig_age():
    """Released default and PPCA + SIREN against age, from the dumps (age groups, 95% bootstrap CI over scans)."""
    A = pd.read_csv(C.CACHE + "/dump_bcp_ages.csv")
    A = A[A.pattern.isin(C.PATS)]
    A["grp"] = pd.cut(A.age, [g[0] - 0.5 for g in AGE_GROUPS] + [AGE_GROUPS[-1][1]],
                      labels=["{}-{}".format(a, b - 1) for a, b in AGE_GROUPS])
    sc = pd.read_csv(C.CACHE + "/dump_bcp_scans.csv")
    fig, axs = plt.subplots(1, 3, figsize=(FULL, 2.3), gridspec_kw=dict(wspace=0.32, width_ratios=[1, 1, 1.1]))
    rng = np.random.default_rng(0)
    for ax, pats, title in [(axs[0], ["gap", "end gap"], "(a) Gaps and end gaps"),
                            (axs[1], ["whole profile", "region"], "(b) Whole profiles and regions")]:
        for k, (lab, name, col) in enumerate([("PPCA + SIREN", "PPCA + SIREN", C.OI["blue"]),
                                              ("transformer", "Transformer (400)", C.OI["red"]),
                                              ("table (cross-fitted)", "Released default", C.OI["black"])]):
            d = A[(A.setting == lab) & A.pattern.isin(pats)]
            a = d.groupby(["grp", "pattern", "metric"], observed=True)[["e2", "r2"]].sum()
            r = np.sqrt(a.e2 / a.r2).groupby("grp", observed=True).mean()
            # bootstrap over scans: per-scan scores of the patterns, grouped by the scan's age
            s = sc[(sc.setting == lab) & sc.group.isin(pats)].copy()
            s["age"] = s.scan.str.extract(r"ses-(\d+)m")[0].astype(float)
            s["grp"] = pd.cut(s.age, [g[0] - 0.5 for g in AGE_GROUPS] + [AGE_GROUPS[-1][1]], labels=r.index)
            lo, hi = [], []
            for g in r.index:
                v = s[s.grp == g].r.to_numpy()
                bs = [np.mean(rng.choice(v, len(v))) for _ in range(500)] if len(v) else [np.nan]
                lo.append(np.percentile(bs, 2.5) / np.mean(v) * r[g] if len(v) else np.nan)
                hi.append(np.percentile(bs, 97.5) / np.mean(v) * r[g] if len(v) else np.nan)
            x = np.arange(len(r)) + (k - 1) * 0.15
            ax.errorbar(x, r.values, yerr=[r.values - np.array(lo), np.array(hi) - r.values], color=col,
                        marker="o", ms=3, lw=1.0, capsize=1.5, label=name)
        n = s.groupby("grp", observed=False).scan.nunique() if False else None
        ax.set_xticks(range(len(AGE_GROUPS)))
        ax.set_xticklabels(["{}-{}".format(a, b - 1) for a, b in AGE_GROUPS], rotation=45, ha="right")
        ax.set_xlabel("Age at scan (months)")
        ax.set_title(title, loc="left")
        ax.grid(axis="y", **GRID)
    # number of validated scan x seed pairs per age group
    sc0 = sc[(sc.setting == "PPCA + SIREN") & (sc.group == "4pat")].copy()
    sc0["age"] = sc0.scan.str.extract(r"ses-(\d+)m")[0].astype(float)
    cnt = pd.cut(sc0.age, [g[0] - 0.5 for g in AGE_GROUPS] + [AGE_GROUPS[-1][1]]).value_counts(sort=False)
    for ax in axs[:2]:
        ax.set_xticklabels(["{}-{} ({})".format(a, b - 1, v) for (a, b), v in zip(AGE_GROUPS, cnt.values)],
                           rotation=50, ha="right", rotation_mode="anchor", fontsize=5.2)
        ax.set_xlabel("Age, months (scan x seed pairs)")
    axs[0].set_ylabel("RMSE / RMSE of the age-bin mean")
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=5.8, ncol=3, loc="lower center", bbox_to_anchor=(0.36, 0.98))
    # absolute RMSE of the age-bin mean and the released default per age bin, FA and MD
    Ab = pd.read_csv(C.CACHE + "/absolute.csv", index_col=[0, 1])
    ax = axs[2]
    x = np.arange(len(C.BINS))
    for k, (m, scale) in enumerate([("fa", 1e3), ("md", 1e6)]):
        for j, (lab, name, col) in enumerate([("age-bin mean", "age-bin mean", "#b0b0b0"),
                                              ("table (cross-fitted)", "released default", C.OI["blue"])]):
            v = [Ab.loc[(m, b), lab] * scale for b in C.BINS]
            ax.bar(x + k * 3.6 + (j - 0.5) * 0.38, v, width=0.38, color=col, label=name if k == 0 else None)
    ax.set_xticks(list(x) + list(x + 3.6))
    ax.set_xticklabels(["0-3", "4-9", "10-60"] * 2, fontsize=5.6, rotation=45, ha="right")
    ax.text(1, -0.24, "FA ($\\times10^{-3}$)", transform=ax.get_xaxis_transform(), ha="center", fontsize=6.2)
    ax.text(4.6, -0.24, "MD ($\\times10^{-6}$ mm$^2$/s)", transform=ax.get_xaxis_transform(), ha="center",
            fontsize=6.2)
    ax.set_ylabel("Absolute RMSE")
    ax.set_title("(c) Absolute error by age bin", loc="left")
    ax.set_ylim(0, ax.get_ylim()[1] * 1.22)
    ax.legend(frameon=False, fontsize=5.6, ncol=2, loc="upper left")
    ax.grid(axis="y", **GRID)
    save(fig, "fig_age")


# ----------------------------------------------------------------------------------------------------------------
def fig_tracts():
    """O6: whole-profile error of the released default per tract against axis proximity and tract length."""
    from scipy import stats
    D = pd.read_csv(C.CACHE + "/rev_tracts.csv", index_col=0)
    ip, c = load_cohort()
    length = pd.Series({t: c.arcs[sl].max() - c.arcs[sl].min() for t, sl in c.slices.items()})
    fig, axs = plt.subplots(1, 2, figsize=(FULL * 0.8, 2.3), gridspec_kw=dict(wspace=0.3))
    y = D["table (cross-fitted)"]
    for ax, x, xl in [(axs[0], D.proximity, "Median distance to the nearest other tract (mm)"),
                      (axs[1], length.reindex(D.index), "Tract length (mm)")]:
        sz = 6 + 400 * D.rejection
        ax.scatter(x, y, s=sz, color=C.OI["blue"], alpha=0.7, lw=0)
        rho, p = stats.spearmanr(x, y)
        ax.text(0.97, 0.05, "Spearman {:.2f} (p = {:.2g})".format(rho, p), transform=ax.transAxes, ha="right",
                fontsize=5.8)
        ax.set_xlabel(xl)
        ax.grid(axis="y", **GRID)
    for t in y.sort_values().index[-3:]:
        axs[0].annotate(t.replace("_", " "), (D.proximity[t], y[t]), fontsize=5.3, xytext=(3, 0),
                        textcoords="offset points", va="center")
    axs[0].set_ylabel("Whole profiles: RMSE /\nRMSE of the age-bin mean")
    axs[0].set_title("(a) Released default per tract", loc="left")
    axs[1].set_title("(b) ... against tract length", loc="left")
    save(fig, "fig_tracts")



ALL = {"patterns": fig_patterns, "data": fig_data, "progression": fig_progression, "metric_heat": fig_metric_heat,
       "distance": fig_distance, "weights": fig_weights, "paired": fig_paired, "age": fig_age,
       "screens": fig_screens, "tracts": fig_tracts, "siren_grid": fig_siren_grid, "cap": fig_cap}

if __name__ == "__main__":
    for name in sys.argv[1:] or ALL:
        ALL[name]()
