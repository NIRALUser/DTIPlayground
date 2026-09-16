#
#   fiberprofile/analysis/impute.py  (from FiberProfileAnalysis/impute_profiles.py)
#
#   Impute missing values in along-tract profile tables (the output of gather) with a per-dataset SIREN implicit neural
#   representation (INR).
#
#   For each dataset (one column identifier, e.g. <subject>_<session>_<prefix>) all of its profiles -- every tract and
#   metric -- are imputed jointly by one SIREN trained only on that dataset's own observed samples (no population
#   information). The network maps the 4-D coordinate (x, y, z, arc_length) of a sampled location to the vector of metric
#   values there (one output per metric); missing entries are masked out of the loss. Tracts are distinguished by their
#   3-D position, taken from the tract axis (<axis-dir>/<tract>_axis.vtk from compute-axis, point data
#   SamplingDistance2Origin = arc length) interpolated at each profile arc length.
#
#   Output mirrors the input layout in a new folder in the same CSV format: observed cells are copied verbatim, only
#   blank cells are filled.
#

import glob
import logging
import os
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd

log = logging.getLogger("impute")

METRIC_ORDER = ["fa", "md", "rd", "ad", "NDI", "ODI", "FWF", "FW_FA", "FW_MD", "FW_RD", "FW_AD"]


def load_axis(path):
    """(points n x 3, arc lengths n) of a tract axis file."""
    from dtiplayground.dmri.fiberprofile.analysis.fiber_axis import read_axis
    return read_axis(path)


def axis_coords_for(arc_lengths, pts, dist):
    """Axis (x, y, z) interpolated at each profile arc length -> (M, 4) coordinates (x, y, z, arc length)."""
    order = np.argsort(dist)
    d = dist[order]
    x = np.interp(arc_lengths, d, pts[order, 0])
    y = np.interp(arc_lengths, d, pts[order, 1])
    z = np.interp(arc_lengths, d, pts[order, 2])
    return np.column_stack([x, y, z, arc_lengths]).astype(np.float32)


### SIREN (multi-output)

def build_siren(in_features, hidden, hidden_layers, out_features, omega_0):
    import torch
    from torch import nn

    class SineLayer(nn.Module):
        def __init__(self, in_f, out_f, is_first=False):
            super().__init__()
            self.omega_0 = omega_0
            self.linear = nn.Linear(in_f, out_f)
            with torch.no_grad():
                if is_first:
                    self.linear.weight.uniform_(-1.0 / in_f, 1.0 / in_f)
                else:
                    b = np.sqrt(6.0 / in_f) / omega_0
                    self.linear.weight.uniform_(-b, b)

        def forward(self, x):
            return torch.sin(self.omega_0 * self.linear(x))

    layers = [SineLayer(in_features, hidden, is_first=True)]
    for _ in range(hidden_layers):
        layers.append(SineLayer(hidden, hidden))
    final = nn.Linear(hidden, out_features)
    with torch.no_grad():
        b = np.sqrt(6.0 / hidden) / omega_0
        final.weight.uniform_(-b, b)
    layers.append(final)
    return nn.Sequential(*layers)


def pick_device(choice="auto"):
    import torch
    if choice != "auto":
        return choice
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def fit_joint(X, Y_norm, cfg, device):
    """Train a multi-output SIREN on (coordinates -> metric vector), masking NaN targets."""
    import torch
    mask = (~np.isnan(Y_norm)).astype(np.float32)
    Yf = np.nan_to_num(Y_norm, nan=0.0).astype(np.float32)
    Xt = torch.from_numpy(X).to(device)
    Yt = torch.from_numpy(Yf).to(device)
    Mt = torch.from_numpy(mask).to(device)
    denom = Mt.sum().clamp_min(1.0)
    model = build_siren(X.shape[1], cfg["hidden"], cfg["hidden_layers"], Y_norm.shape[1], cfg["omega0"]).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=cfg["lr"])
    model.train()
    for _ in range(cfg["epochs"]):
        opt.zero_grad()
        pred = model(Xt)
        loss = (((pred - Yt) ** 2) * Mt).sum() / denom
        loss.backward()
        opt.step()
    model.eval()
    return model


### format-preserving CSV write (only blank cells are filled)

def write_filled(in_path, out_path, filled, value_fmt):
    """Copy in_path to out_path, substituting imputed values into blank cells.
    filled: {data_row_index: {value_col_index: value}}; other cells are preserved byte for byte."""
    with open(in_path) as fh:
        lines = fh.read().splitlines()
    out = [lines[0]]
    for r, line in enumerate(lines[1:]):
        row_fill = filled.get(r)
        if row_fill:
            parts = line.split(",")
            for j, val in row_fill.items():
                parts[j + 1] = value_fmt % val  # +1: column 0 is Arc_Length
            line = ",".join(parts)
        out.append(line)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        fh.write("\n".join(out) + "\n")


def impute_profiles(profiles_dir, axis_dir, out_dir, epochs=200, omega0=10.0, hidden_layers=3, hidden_width=256, lr=1e-4,
                    device="auto", value_format="%.8g", seed=0):
    """Impute the blank cells of every <tract>/<tract>_<metric>.csv under profiles_dir into out_dir.
    Returns (number of datasets imputed, number of cells filled)."""
    import torch
    if not os.path.isdir(profiles_dir):
        raise FileNotFoundError("profiles dir not found: {}".format(profiles_dir))
    if not os.path.isdir(axis_dir):
        raise FileNotFoundError("axis dir not found: {}".format(axis_dir))
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = pick_device(device)
    log.info("Torch device: %s", device)
    cfg = {"epochs": epochs, "omega0": omega0, "hidden": hidden_width, "hidden_layers": hidden_layers, "lr": lr}
    log.info("SIREN: %d epochs, omega_0=%g, %d hidden layers x %d, Adam lr=%g (joint per dataset)",
             epochs, omega0, hidden_layers, hidden_width, lr)

    # preload every profile table, grouped by tract
    tables = sorted(f for f in glob.glob(os.path.join(profiles_dir, "**", "*.csv"), recursive=True)
                    if not f.endswith("_agebinstats.csv"))
    log.info("Found %d profile tables", len(tables))
    tract_frames = defaultdict(dict)  # tract -> {metric: DataFrame}
    tract_paths = defaultdict(dict)   # tract -> {metric: csv path}
    for f in tables:
        tract = os.path.basename(os.path.dirname(f))
        metric = os.path.basename(f)[: -len(".csv")].rsplit("_", 1)[1]
        tract_frames[tract][metric] = pd.read_csv(f, index_col=0)
        tract_paths[tract][metric] = f

    metrics = [m for m in METRIC_ORDER if any(m in fr for fr in tract_frames.values())]
    metrics += sorted({m for fr in tract_frames.values() for m in fr} - set(metrics))
    log.info("Metrics (output channels): %s", metrics)

    # tract coordinates + global normalisation
    tract_arc, tract_coords_raw = {}, {}
    for tract, frames in tract_frames.items():
        axis_path = os.path.join(axis_dir, "{}_axis.vtk".format(tract))
        if not os.path.isfile(axis_path):
            log.warning("no axis file for tract '%s'; its blanks cannot be imputed", tract)
            continue
        arc = next(iter(frames.values())).index.to_numpy(dtype=float)
        tract_arc[tract] = arc
        tract_coords_raw[tract] = axis_coords_for(arc, *load_axis(axis_path))
    if not tract_coords_raw:
        raise ValueError("no axis files in {} match the profile tracts".format(axis_dir))
    all_coords = np.vstack(list(tract_coords_raw.values()))
    lo = all_coords.min(axis=0, keepdims=True)
    hi = all_coords.max(axis=0, keepdims=True)
    span = np.where(hi - lo > 0, hi - lo, 1.0)
    tract_coords_norm = {t: ((c - lo) / span * 2.0 - 1.0).astype(np.float32) for t, c in tract_coords_raw.items()}

    # datasets with missing cells
    ident_missing = defaultdict(int)
    for tract, frames in tract_frames.items():
        for m, df in frames.items():
            na = df.isna().sum()
            for ident in df.columns:
                if na[ident] > 0:
                    ident_missing[ident] += int(na[ident])
    datasets = sorted(i for i, c in ident_missing.items() if c > 0)
    log.info("%d datasets need imputation", len(datasets))

    # per-dataset joint fit + fill
    fills = defaultdict(lambda: defaultdict(dict))  # csv path -> {row -> {col index -> value}}
    imputable_tracts = [t for t in tract_frames if t in tract_coords_norm]
    n_cells = 0
    for di, ident in enumerate(datasets, 1):
        present = [t for t in imputable_tracts if ident in next(iter(tract_frames[t].values())).columns]
        if not present:
            continue
        Xparts, Yparts = [], []
        for t in present:
            idx = tract_arc[t]
            cols = []
            for m in metrics:
                df = tract_frames[t].get(m)
                if df is not None and ident in df.columns:
                    cols.append(df[ident].reindex(idx).to_numpy(dtype=float))
                else:
                    cols.append(np.full(len(idx), np.nan))
            Xparts.append(tract_coords_norm[t])
            Yparts.append(np.column_stack(cols))
        X = np.vstack(Xparts).astype(np.float32)
        Y = np.vstack(Yparts)

        # per-metric standardisation from this dataset's own values
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            mu = np.nanmean(Y, axis=0)
            sd = np.nanstd(Y, axis=0)
        has_obs = np.sum(~np.isnan(Y), axis=0) > 0
        sd_safe = np.where((sd < 1e-12) | ~np.isfinite(sd), 1.0, sd)
        mu_safe = np.where(np.isfinite(mu), mu, 0.0)
        Y_norm = (Y - mu_safe) / sd_safe

        model = fit_joint(X, Y_norm.astype(np.float32), cfg, device)
        with torch.no_grad():
            for t in present:
                pred = model(torch.from_numpy(tract_coords_norm[t]).to(device)).cpu().numpy() * sd_safe + mu_safe
                for mi, m in enumerate(metrics):
                    if not has_obs[mi]:
                        continue  # metric never observed for this dataset -> can't impute without population data
                    df = tract_frames[t].get(m)
                    if df is None or ident not in df.columns:
                        continue
                    col = df[ident].to_numpy(dtype=float)
                    miss = np.where(np.isnan(col))[0]
                    if miss.size == 0:
                        continue
                    j = df.columns.get_loc(ident)
                    for r in miss:
                        fills[tract_paths[t][m]][int(r)][int(j)] = float(pred[r, mi])
                        n_cells += 1
        if di % 25 == 0:
            log.info("  ... %d/%d datasets fit (%d cells filled)", di, len(datasets), n_cells)

    for f in tables:
        write_filled(f, os.path.join(out_dir, os.path.relpath(f, profiles_dir)), fills.get(f, {}), value_format)
    log.info("Done. Wrote %d tables to %s/; imputed %d datasets (%d cells).", len(tables), out_dir, len(datasets), n_cells)
    return len(datasets), n_cells


### command line

def add_parser(subparsers):
    p = subparsers.add_parser("impute", help="Impute missing profile values (per-dataset SIREN)",
                              description="Impute missing values in gathered profile tables (<tract>/<tract>_<metric>.csv) "
                                          "with a per-dataset SIREN on (x, y, z, arc length) from the tract axes. "
                                          "Output mirrors the input; only blank cells are filled.")
    p.add_argument("--profiles-dir", default="Profiles", help="Root with <tract>/<tract>_<metric>.csv tables")
    p.add_argument("--axis-dir", default="FiberAxis", help="Folder of <tract>_axis.vtk files (compute-axis)")
    p.add_argument("--out-dir", default="Profiles_Imputed", help="Output root (mirrors the input layout)")
    p.add_argument("--epochs", type=int, default=200, help="SIREN training epochs (default: 200)")
    p.add_argument("--omega0", type=float, default=10.0, help="SIREN omega_0 (default: 10)")
    p.add_argument("--hidden-layers", type=int, default=3, help="SIREN hidden sine layers (default: 3)")
    p.add_argument("--hidden-width", type=int, default=256, help="SIREN layer width (default: 256)")
    p.add_argument("--lr", type=float, default=1e-4, help="Adam learning rate (default: 1e-4)")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"], help="Torch device (default: auto)")
    p.add_argument("--value-format", default="%.8g", help="printf format for imputed values (default: %%.8g)")
    p.add_argument("--seed", type=int, default=0, help="Random seed (default: 0)")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.set_defaults(func=run)


def run(args):
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)
    impute_profiles(args.profiles_dir, args.axis_dir, args.out_dir, args.epochs, args.omega0, args.hidden_layers,
                    args.hidden_width, args.lr, args.device, args.value_format, args.seed)
    return 0
