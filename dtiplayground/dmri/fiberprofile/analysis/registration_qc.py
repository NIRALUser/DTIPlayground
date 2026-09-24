#
#   fiberprofile/analysis/registration_qc.py  (from FiberProfileAnalysis/registration_QC.py)
#   dmrifiberprofile qc-registration
#
#!/usr/bin/env python3
"""
QC for the deformable alignment of subject diffusion tensors/metrics to a prior
diffusion-MRI atlas.

Each subject session has tensor-derived metric maps warped into atlas space
(``.../AtlasReg/*_Deformed<METRIC>.nii.gz`` and ``*_DeformedDTI.nrrd``, or the
outputs of the dmriprep DTI_Register module ``<scan>_Registered_<METRIC>.nii.gz``
and ``<scan>_DTI_Registered.nrrd`` in any folder below the data folder).  The
atlas provides the same maps (``Atlas_*_<METRIC>.nii.gz`` + ``*_DTI.nrrd``).

The QC compares each subject to the atlas and (optionally) to an age-conditional
normative model, and flags registration outliers.

Metrics
-------
* Scalar maps (FA primary; MD/RD/AD optional) vs the atlas, within a brain mask:
  MAE, 3D-SSIM (+ map), NCC (zero-normalised cross-correlation).
* Tensor principal-direction **angular error** (deg) vs the atlas, over WM.
* **Contiguity of the disagreement** (``*BlobFrac`` / ``*BlobConc``): noise and
  age mismatch scatter bad voxels; a failed warp produces a few *contiguous*
  blobs.  Connected components of the extreme-voxel mask give the largest-blob
  volume fraction and the share of extreme voxels sitting in the top-k blobs.
  Three model-free/model-based cuts are reported: the subject's worst-SSIM
  percentile (``--ssim-blob-pct``), angular error above ``--ang-blob-deg``, and,
  where a normative model exists, |z| > ``--z-thresh``.
* **CSF sanity check** (``CSF_*``): a deep, high-MD / low-FA reference region
  (ventricles) is derived from the atlas.  A misregistration drops white matter
  into the ventricles, so subject MD there collapses (``CSF_MDratio`` << 1) and
  subject FA rises (``CSF_FAmean``).  Needs deformed MD maps; skip with
  ``--no-csf-check``.

Age handling
------------
Subjects are age-diverse but registered into one age-specific atlas, so raw
similarity is age-confounded.  With ``--normative-dir`` an age-conditional
normative model (per age bin) provides voxelwise expectations, turning each
comparison into a standardised deviation (z):

* scalars: ``z = (subject - mean_age) / std_age``
* angular: principal directions are **axial** data (sign-ambiguous) on RP^2, so
  the normative "mean direction" is the leading eigenvector of the per-voxel
  dyadic mean ``T = mean(v vᵀ)`` (the spherical analogue of the circular mean),
  and the dispersion is ``sigma = sqrt(1 - tau1)`` (RMS ``sin`` of the reference
  angles, ``tau1`` = leading eigenvalue of the normalised ``T``).  The subject
  deviation is standardised as ``z = sin(angle(v_subj, mu)) / sigma`` -- valid
  for both small and large angles, degenerating to the tangent-space z-score
  when the spread is small.

Without a normative model, raw subject-vs-atlas scores are used (age-confounded)
and the age itself is not needed.

The age of a scan is read from the session folder name (``ses-<N>m`` by default,
see ``--age-regex``).  Cohorts that name sessions by visit instead (HBCD's
``ses-V02``, say) supply the ages in a table with ``--age-csv`` (a BIDS
``participants.tsv`` / ``sessions.tsv`` works: the subject, session and age
columns are auto-detected -- an age column named after none of the usual
conventions is still found by a partial ``candidate_age`` match, or can be named
outright with ``--age-column``; use ``--age-units`` if the ages are not in
months).
Scans whose age stays unknown are still QC'd against the atlas -- only the
age-binned normative model needs an age, and those scans are skipped there with
a warning.

Outlier decision is **one combined flag per subject-session** (a bad warp hits
all metrics/the tensor together).  ``--combine`` picks the rule:

* ``robust-z`` (default): mean of the per-metric robust z-scores, itself
  robust-z'd and cut at ``--outlier-mad``.
* ``mahalanobis``: robust (MCD, ``--mahal-support``) Mahalanobis distance over
  the whole metric vector, cut at a chi-square quantile
  (``--outlier-chi2-p``).  This accounts for the strong correlation between
  MAE/SSIM/NCC on the same map -- which the plain mean triple-counts -- and does
  not let one severe failure be averaged away by passing dimensions.  Only
  *worse-than-typical* sessions are flagged.

``mahalanobis_d`` / ``mahalanobis_p`` / ``mahal_top_contrib`` (the metric
contributing most to the distance, i.e. *why* a session stands out) are written
whenever the cohort is large enough (n >= 5x features), regardless of the rule
in force, as are ``combined_score`` / ``combined_robust_z``.  Note that the
Mahalanobis distances of a real cohort are usually far heavier-tailed than
chi-square: the run log reports how many sessions the chi-square cut would flag,
so check that number before switching the rule.

Modes
-----
* ``--build-normative`` : compute the normative model from ``--reference-dir``
  into ``--normative-dir`` and exit.  Per age bin it writes the voxelwise
  ``<METRIC>_mean`` / ``_std`` / ``_count`` of every metric map found in the
  reference scans (``*_Deformed<METRIC>.nii.gz`` / ``*_Registered_<METRIC>.nii.gz``, e.g. FA, MD, RD, AD), the
  angular model, and the log-Euclidean mean tensor ``DTI_mean.nrrd``
  (+ ``DTI_count``) of the deformed tensors (in the atlas tensor frame).
* default (QC)          : score ``--data-dir`` subjects, write a table and outlier
  flags.  NIfTI disagreement maps + a per-subject preview PNG (atlas FA, DTI FA,
  FA diff, FA SSIM, angular error z, largest blobs) are written **only for
  flagged outliers**;
  ``--save-all-maps`` writes them for every session.

Usage
-----
    # build the age-conditional normative model from a reference cohort
    dmrifiberprofile qc-registration --build-normative --reference-dir RegistrationData \\
        --normative-dir RegNormative

    # QC (with normative if available, else raw)
    dmrifiberprofile qc-registration --data-dir RegistrationData --normative-dir RegNormative \\
        --out-dir RegistrationQC
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import math
import os
import re
import sys

import numpy as np
import nibabel as nib
import nrrd
from scipy import ndimage, stats

from dtiplayground.dmri.fiberprofile.analysis.detect_flip import candidate_corrections, correction_matrix
from dtiplayground.dmri.fiberprofile.analysis.flip_tensor import COMPONENTS, parse_correction, correction_name, tensor_axis

log = logging.getLogger("reg_qc")

AGE_RE = re.compile(r"ses-(\d+)m")
ALL_SCALARS = ["FA", "MD", "RD", "AD"]
# Tensor frame corrections (as detect-tensor-flip / DTI_Register tensorFlip): flips of x, y, z of the stored components,
# in the measurement frame of the header or in the frame of the voxel axes ('voxel', 'voxel,x', ...). Directions are
# compared in physical (LPS) space.


# ---------------------------------------------------------------------------
# Bins / discovery
# ---------------------------------------------------------------------------
def parse_bins(spec):
    bins = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        lo, hi = (int(x) for x in tok.split("-"))
        bins.append([lo, hi, f"{lo}-{hi}m"])
    bins.sort(key=lambda b: b[0])
    if bins:
        bins[-1][1] = 10**9  # oldest bin open-ended
    return [tuple(b) for b in bins]


## the age table is shared with the DTI_Register module of dmriprep (protocol ageCSV)
from dtiplayground.dmri.common.age_table import (  # noqa: E402  (kept importable from here)
    AGE_TABLE_AGE_COLS, AGE_TABLE_AGE_SUBSTRINGS, AGE_TABLE_SESSION_COLS, AGE_TABLE_SUBJECT_COLS,
    AGE_UNIT_TO_MONTHS, age_from_table, bids_key as _bids_key, load_age_table)


def age_for_session(subject, session, age_table, age_re):
    """Age in months from the table (session- then subject-level), else the session name."""
    age = age_from_table(subject, session, age_table)
    if age is not None:
        return age
    m = age_re.search(session)
    return int(m.group(1)) if m else None


def bin_label_for_age(age, bins):
    if age is None:
        return None
    for lo, hi, label in bins:
        if lo <= age <= hi:
            return label
    return None


def find_atlas(atlas_dir):
    """Return {metric: path} for scalar atlas maps and the atlas tensor path."""
    scalars = {}
    for m in ALL_SCALARS:
        hits = glob.glob(os.path.join(atlas_dir, f"*_{m}.nii.gz"))
        if hits:
            scalars[m] = sorted(hits)[0]
    tensor = sorted(glob.glob(os.path.join(atlas_dir, "*_DTI.nrrd")))
    return scalars, (tensor[0] if tensor else None)


DEFORMED_RE = re.compile(
    r"^(?P<sub>sub-[^_]+)_(?P<ses>ses-[^_]+)_(?P<mid>.+)_Deformed(?P<metric>[A-Za-z0-9]+)\.(?:nii\.gz|nrrd)$")
PREFIX_RE = re.compile(r"^(?P<prefix>.+?_dwi)(?:_.*)?$")


def parse_deformed(basename):
    """(subject, session, prefix, metric) from a Deformed<METRIC> filename, or None.

    The prefix is the pipeline identifier (up to and including ``_dwi``), so it
    matches the profile/prep column names and distinguishes multiple
    acquisitions within one session.
    """
    m = DEFORMED_RE.match(basename)
    if m is None:
        return None
    pm = PREFIX_RE.match(m.group("mid"))
    prefix = pm.group("prefix") if pm else m.group("mid")
    return m.group("sub"), m.group("ses"), prefix, m.group("metric")


## outputs of the dmriprep DTI_Register module: <scan>_DTI_Registered.nrrd (tensor) and
## <scan>_Registered_<metric>.nii.gz (metric maps next to the input DTI, e.g. FA, DTI_FA or tensor_fa)
REGISTERED_RE = re.compile(
    r"^(?P<mid>.+?)_(?:DTI_Registered\.nrrd|Registered_(?P<metric>[A-Za-z0-9_]+)\.nii\.gz)$")
SUBJECT_RE = re.compile(r"(?:^|_)(sub-[^_]+)")
SESSION_RE = re.compile(r"(?:^|_)(ses-[^_]+)")


def parse_registered(path):
    """(subject, session, prefix, metric) of a DTI_Register output, or None.

    The subject and session are read from the file name (``sub-<id>_ses-<id>_...``), else from the
    folder names of the path; the metric is ``DTI`` for the tensor, else the name after ``Registered_``
    without a ``DTI_`` / ``tensor_`` prefix, in upper case (``tensor_fa`` -> ``FA``).
    """
    m = REGISTERED_RE.match(os.path.basename(path))
    if m is None:
        return None
    mid = m.group("mid")
    parts = [mid] + list(reversed(os.path.dirname(os.path.abspath(path)).split(os.sep)))
    subject = next((s.group(1) for s in map(lambda x: SUBJECT_RE.search(x), parts) if s), None)
    session = next((s.group(1) for s in map(lambda x: SESSION_RE.search(x), parts) if s), None)
    if subject is None or session is None:
        return None
    rest = re.sub(r"^(?:_?(?:sub|ses)-[^_]+)+_?", "", mid) or mid
    pm = PREFIX_RE.match(rest)
    prefix = pm.group("prefix") if pm else rest
    metric = m.group("metric")
    if metric is None:
        metric = "DTI"
    else:
        metric = re.sub(r"^(?:DTI|tensor)_", "", metric, flags=re.IGNORECASE).upper()
    return subject, session, prefix, metric


def find_sessions(root, age_table=None, age_re=AGE_RE):
    """Discover scans (one per subject/session/prefix) with metric/tensor paths.

    Two layouts are recognised under *root*:

    * ``sub-*/ses-*/AtlasReg/*_Deformed<METRIC>.nii.gz`` and ``*_DeformedDTI.nrrd``
    * outputs of the dmriprep DTI_Register module in any folder below *root*:
      ``<scan>_Registered_<METRIC>.nii.gz`` and ``<scan>_DTI_Registered.nrrd``, the subject and session
      taken from the scan name (``sub-<id>_ses-<id>_...``) or else from the folder names

    Multiple acquisitions in the same session (different prefixes) become
    separate scan entries keyed by the full ``sub_ses_prefix`` identifier.

    ``age`` is None when neither *age_table* nor the session name supplies one;
    such scans are still returned (age is only *required* for the age-binned
    normative model -- the caller decides).
    """
    scans = {}  # (subject, session, prefix) -> entry
    no_age = []

    def add(subject_dir, session, subject, prefix, metric, f):
        key = (subject, session, prefix)
        if key not in scans:
            age = age_for_session(subject_dir, session, age_table, age_re)
            if age is None and os.path.join(subject, session) not in no_age:
                no_age.append(os.path.join(subject, session))
            scans[key] = {"id": f"{subject}_{session}_{prefix}", "subject": subject, "session": session,
                          "prefix": prefix, "age": age, "scalars": {}, "tensor": None}
        entry = scans[key]
        if metric == "DTI":
            if f.endswith(".nrrd"):
                if entry["tensor"] is None:
                    entry["tensor"] = f
                elif entry["tensor"] != f:
                    log.warning("%s: more than one registered tensor, using %s (not %s)", entry["id"], entry["tensor"], f)
        elif f.endswith(".nii.gz"):
            if metric not in entry["scalars"]:
                entry["scalars"][metric] = f
            elif entry["scalars"][metric] != f:
                log.warning("%s: more than one registered %s map, using %s (not %s)", entry["id"], metric,
                            entry["scalars"][metric], f)

    for reg in sorted(glob.glob(os.path.join(root, "sub-*", "ses-*", "AtlasReg"))):
        ses_dir = os.path.dirname(reg)
        session = os.path.basename(ses_dir)
        subject_dir = os.path.basename(os.path.dirname(ses_dir))
        for f in sorted(glob.glob(os.path.join(reg, "*_Deformed*.nii.gz"))
                        + glob.glob(os.path.join(reg, "*_DeformedDTI.nrrd"))):
            parsed = parse_deformed(os.path.basename(f))
            if parsed is None:
                continue
            subject, ses, prefix, metric = parsed
            add(subject_dir, session, subject, prefix, metric, f)
    for f in sorted(glob.glob(os.path.join(root, "**", "*_DTI_Registered.nrrd"), recursive=True)
                    + glob.glob(os.path.join(root, "**", "*_Registered_*.nii.gz"), recursive=True)):
        parsed = parse_registered(f)
        if parsed is None:
            continue
        subject, session, prefix, metric = parsed
        add(subject, session, subject, prefix, metric, f)
    ## metric maps that weren't written (e.g. DTI_Register of a tensor without maps next to it): computed from the tensor
    derived = [s["id"] for s in scans.values() if s["tensor"] and any(m not in s["scalars"] for m in ALL_SCALARS)]
    for s in scans.values():
        if s["tensor"]:
            for m in ALL_SCALARS:
                s["scalars"].setdefault(m, TensorMetric(s["tensor"], m))
    if derived:
        log.info("%d scan(s) without all of the %s maps (e.g. %s): the missing maps are computed from the registered tensor",
                 len(derived), "/".join(ALL_SCALARS), ", ".join(derived[:3]))
    if no_age:
        log.warning("no age information for %d session(s) (e.g. %s)%s", len(no_age),
                    ", ".join("/".join(d.split(os.sep)[-2:]) for d in no_age[:3]),
                    "" if len(no_age) < 4 else ", ...")
        log.warning("  the session name carries no age and no --age-csv entry matched; "
                    "raw QC still runs, but the age-binned normative model cannot be used")
    return [scans[k] for k in sorted(scans)]


# ---------------------------------------------------------------------------
# Tensor / directions
# ---------------------------------------------------------------------------
class TensorMetric(str):
    """A scalar map computed from a tensor NRRD (used when the metric map itself is missing): the path of the tensor,
    with the metric (FA, MD, AD or RD) in ``.metric``."""
    def __new__(cls, tensor_path, metric):
        obj = super().__new__(cls, tensor_path)
        obj.metric = metric
        return obj


_tensor_metric_cache = {}


def tensor_metrics(tensor_path):
    """{FA, MD, AD, RD: (X,Y,Z) float32} of a tensor NRRD (zeros where the tensor is zero or not finite), and the
    RAS affine of its grid."""
    if tensor_path in _tensor_metric_cache:
        return _tensor_metric_cache[tensor_path]
    comp, header = nrrd.read(tensor_path)
    axis, kind = tensor_axis(comp, header)
    comp = np.moveaxis(comp, axis, 0).astype(np.float64)
    valid = np.all(np.isfinite(comp), axis=0) & np.any(comp != 0, axis=0)
    D, idx, _ = _masked_tensors(tensor_path, valid)
    w = np.linalg.eigvalsh(D)[:, ::-1]  # descending
    md = w.mean(axis=1)
    norm = np.sqrt((w ** 2).sum(axis=1))
    fa = np.where(norm > 0, np.sqrt(1.5 * ((w - md[:, None]) ** 2).sum(axis=1)) / np.where(norm > 0, norm, 1), 0)
    values = {"FA": np.clip(fa, 0, 1), "MD": md, "AD": w[:, 0], "RD": w[:, 1:].mean(axis=1)}
    maps = {}
    for m, v in values.items():
        out = np.zeros(valid.shape, dtype=np.float32)
        out[idx] = v
        maps[m] = out
    ## voxel -> physical affine of the spatial axes, in RAS like NIfTI
    sd = np.array([np.asarray(d, dtype=np.float64) for d in header["space directions"]
                   if d is not None and np.all(np.isfinite(np.asarray(d, dtype=np.float64)))])
    affine = np.eye(4)
    affine[:3, :3] = sd.T
    affine[:3, 3] = np.asarray(header.get("space origin", np.zeros(3)), dtype=np.float64)
    if str(header.get("space", "")).lower() in ("left-posterior-superior", "lps"):
        affine = np.diag([-1.0, -1.0, 1.0, 1.0]) @ affine
    _tensor_metric_cache.clear()  # keep only the tensor being scored
    _tensor_metric_cache[tensor_path] = (maps, affine)
    return maps, affine


def load_scalar(path):
    if isinstance(path, TensorMetric):
        maps, affine = tensor_metrics(str(path))
        return maps[path.metric], affine
    img = nib.load(path)
    return np.asanyarray(img.dataobj, dtype=np.float32), img.affine


def _masked_tensors(tensor_path, mask):
    """(N,3,3) tensors of the voxels in *mask*, the mask indices, and the NRRD header."""
    comp, header = nrrd.read(tensor_path)
    axis, kind = tensor_axis(comp, header)
    comp = np.moveaxis(comp, axis, 0)
    idx = np.where(mask)
    c = comp[:, idx[0], idx[1], idx[2]].astype(np.float64)  # (components, N)
    D = np.zeros((c.shape[1], 3, 3), dtype=np.float64)
    for k, ij in enumerate(COMPONENTS[kind]):
        if ij is not None:
            D[:, ij[0], ij[1]] = c[k]
            if kind != "3d-matrix":
                D[:, ij[1], ij[0]] = c[k]
    return D, idx, header


def principal_directions(tensor_path, mask, correction="none"):
    """Leading eigenvector per masked voxel of a tensor NRRD, in physical (LPS) space.

    Returns (X,Y,Z,3) float32 (zeros outside the mask). The stored components are mapped to physical space by the
    measurement frame of the header, or by *correction* ('x', 'voxel', 'voxel,x', ... as detect-tensor-flip) to
    correct a tensor frame that doesn't match the header.
    """
    D, idx, header = _masked_tensors(tensor_path, mask)
    _, vecs = np.linalg.eigh(D)          # ascending eigenvalues
    pd = (vecs[:, :, -1] @ correction_matrix(header, correction).T).astype(np.float32)
    out = np.zeros(mask.shape + (3,), dtype=np.float32)
    out[idx] = pd
    return out


def _symmetric_matrices(comp):
    """(N, 3, 3) matrices from (6, N) components [xx, xy, xz, yy, yz, zz]."""
    c = np.asarray(comp, dtype=np.float64)
    return c[[0, 1, 2, 1, 3, 4, 2, 4, 5]].T.reshape(-1, 3, 3)


def _eigen_function(w, v, func):
    """(6, N) components of v diag(func(w)) vᵀ."""
    M = np.matmul(v * func(w)[:, None, :], v.transpose(0, 2, 1))
    return M.reshape(-1, 9)[:, [0, 1, 2, 4, 5, 8]].T


def matrix_function(comp, func):
    """func applied to the eigenvalues of symmetric 3x3 matrices given as (6, N) components [xx, xy, xz, yy, yz, zz].
    Returns (6, N); with func=np.log the eigenvalues must be positive."""
    w, v = np.linalg.eigh(_symmetric_matrices(comp))
    return _eigen_function(w, v, func)


def log_tensors(tensor_path, mask, correction="none", target_header=None):
    """Matrix logarithms (6, N) of the positive definite tensors within *mask*, and the (X,Y,Z) mask of those voxels.
    The tensors are corrected like principal_directions and expressed in the frame of *target_header* (the stored
    frame of the mean tensor), in physical (LPS) space without one: D -> M D M^T."""
    D, idx, header = _masked_tensors(tensor_path, mask)
    M = correction_matrix(header, correction)
    if target_header is not None:
        M = correction_matrix(target_header).T @ M  # physical -> stored frame of the target (orthonormal)
    D = np.einsum("ab,nbc,dc->nad", M, D, M)
    finite = np.all(np.isfinite(D.reshape(-1, 9)), axis=1)
    c = D.reshape(-1, 9)[:, [0, 1, 2, 4, 5, 8]].T[:, finite]
    w, v = np.linalg.eigh(_symmetric_matrices(c))
    positive = w[:, 0] > 0
    valid = np.zeros(mask.shape, dtype=bool)
    valid[tuple(i[finite][positive] for i in idx)] = True
    return _eigen_function(w[positive], v[positive], np.log), valid


def frame_scores(tensor_path, wm, atlas_pd):
    """Median angle (deg) to the atlas principal directions over *wm* of every distinct tensor frame correction of a
    tensor NRRD: {name: angle}, in the order of candidate_corrections (header frame first)."""
    D, idx, header = _masked_tensors(tensor_path, wm)
    _, vecs = np.linalg.eigh(D)
    e1 = vecs[:, :, -1]
    ref = atlas_pd[idx]
    scores = {}
    for name, E in candidate_corrections(header):
        dot = np.clip(np.abs(np.sum((e1 @ E.T) * ref, axis=-1)), 0, 1)
        scores[name] = float(np.median(np.degrees(np.arccos(dot))))
    return scores


def detect_tensor_flip(sessions, atlas_pd, atlas_fa, mask_thr, angular_fa_min, n_probe=3):
    """Detect the tensor frame correction aligning subject tensors to the atlas frame.

    Probes a few subjects; for each, picks the correction (flips in the header frame or in the voxel frame, see
    detect-tensor-flip) minimising the median core-WM angular error to the atlas; returns the majority choice
    (name, median error).
    """
    core_thr = max(angular_fa_min, 0.3)
    votes, medians, used = {}, {}, 0
    for s in sessions:
        if not s["tensor"] or "FA" not in s["scalars"]:
            continue
        sfa, _ = load_scalar(s["scalars"]["FA"])
        wm = (sfa > mask_thr) & (atlas_fa > core_thr)
        if wm.sum() < 1000:
            continue
        scores = frame_scores(s["tensor"], wm, atlas_pd)
        best = min(scores, key=scores.get)
        votes[best] = votes.get(best, 0) + 1
        medians.setdefault(best, []).append(scores[best])
        used += 1
        if used >= n_probe:
            break
    if not votes:
        return "none", np.nan
    choice = max(votes, key=votes.get)
    return choice, float(np.median(medians[choice]))


def subject_frame(tensor_path, wm, atlas_pd, applied, min_gain_deg=5.0):
    """Best tensor frame correction of one subject and how much it improves on the one applied to the dataset:
    (best name, best angle, applied angle, differs) with differs when the best is better by more than min_gain_deg."""
    scores = frame_scores(tensor_path, wm, atlas_pd)
    best = min(scores, key=scores.get)
    applied_name = correction_name(*parse_correction(applied))
    applied_angle = scores.get(applied_name)
    if applied_angle is None:  # the applied correction equals another candidate on this grid
        applied_angle = float(np.median(angular_error_deg(principal_directions(tensor_path, wm, applied), atlas_pd, wm)[wm]))
    return best, scores[best], applied_angle, (applied_angle - scores[best]) > min_gain_deg


def angular_error_deg(pd_a, pd_b, mask):
    """Undirected angle (deg) between two principal-direction fields, over mask."""
    dot = np.abs(np.sum(pd_a * pd_b, axis=-1))
    np.clip(dot, 0.0, 1.0, out=dot)
    ang = np.zeros(mask.shape, dtype=np.float32)
    ang[mask] = np.degrees(np.arccos(dot[mask]))
    return ang


# ---------------------------------------------------------------------------
# Similarity (masked)
# ---------------------------------------------------------------------------
def masked_mae(a, b, mask):
    return float(np.mean(np.abs(a[mask] - b[mask])))


def masked_ncc(a, b, mask):
    x, y = a[mask].astype(np.float64), b[mask].astype(np.float64)
    if x.std() < 1e-12 or y.std() < 1e-12:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def masked_ssim(a, b, mask, data_range):
    from skimage.metrics import structural_similarity

    _, smap = structural_similarity(
        a.astype(np.float64), b.astype(np.float64),
        data_range=data_range, gaussian_weights=True, sigma=1.5,
        use_sample_covariance=False, full=True,
    )
    return float(np.mean(smap[mask])), smap.astype(np.float32)


def brain_mask(subj_fa, atlas_fa, thr):
    return (subj_fa > thr) & (atlas_fa > thr)


# ---------------------------------------------------------------------------
# Contiguity of the disagreement (largest-blob metrics)
# ---------------------------------------------------------------------------
BLOB_STRUCT = ndimage.generate_binary_structure(3, 1)  # 6-connectivity


def blob_stats(extreme, valid, top_k=3, min_blob=10):
    """Connected-component summary of an extreme-voxel mask.

    Registration failures put the bad voxels in a few *contiguous* clumps, while
    noise and age mismatch scatter them; ``frac`` alone cannot tell these apart.

    Returns ``(stats, blobs)`` where *stats* has

    * ``frac``     : extreme voxels / valid voxels
    * ``maxfrac``  : largest connected component / valid voxels
    * ``conc``     : share of the extreme voxels living in the top-*k* blobs
                     (NaN when there are too few extreme voxels to be meaningful)
    * ``nblob``    : number of components of at least *min_blob* voxels

    and *blobs* is the top-*k* component mask (uint8, for saving/preview).
    """
    nvalid = int(valid.sum())
    empty = np.zeros(valid.shape, np.uint8)
    if nvalid == 0:
        return {"frac": np.nan, "maxfrac": np.nan, "conc": np.nan, "nblob": 0}, empty
    ex = extreme & valid
    n_ex = int(ex.sum())
    if n_ex == 0:
        return {"frac": 0.0, "maxfrac": 0.0, "conc": np.nan, "nblob": 0}, empty
    lab, _ = ndimage.label(ex, structure=BLOB_STRUCT)
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    order = np.argsort(sizes)[::-1][:top_k]
    keep = [int(i) for i in order if sizes[i] > 0]
    stats = {
        "frac": n_ex / nvalid,
        "maxfrac": float(sizes[keep[0]]) / nvalid,
        # concentration is meaningless on a handful of voxels
        "conc": float(sizes[keep].sum()) / n_ex if n_ex >= min_blob else np.nan,
        "nblob": int((sizes >= min_blob).sum()),
    }
    return stats, np.isin(lab, keep).astype(np.uint8)


def add_blob_row(row, prefix, stats):
    row[f"{prefix}BlobFrac"] = stats["maxfrac"]
    row[f"{prefix}BlobConc"] = stats["conc"]
    row[f"{prefix}BlobN"] = stats["nblob"]


# ---------------------------------------------------------------------------
# CSF / ventricle sanity check
# ---------------------------------------------------------------------------
def build_csf_roi(atlas_fa, atlas_md, mask_thr, md_pct=95.0, fa_max=0.15,
                  erode=8, top_k=3, min_size=50):
    """Deep high-MD / low-FA atlas region (~ventricles) for the CSF sanity check.

    No atlas parcellation is assumed: the ROI is the top ``md_pct`` percentile of
    atlas MD with atlas FA < *fa_max*, restricted to the interior of the brain
    (mask eroded by *erode* voxels) so sulcal CSF and partial-volume boundary
    voxels are excluded, keeping the *top_k* largest components.

    The threshold is a percentile, so the ROI is independent of the MD units.
    """
    brain = ndimage.binary_fill_holes(atlas_fa > mask_thr)
    if not brain.any():
        return np.zeros(atlas_fa.shape, bool)
    inner = ndimage.binary_erosion(brain, BLOB_STRUCT, int(erode))
    roi = (atlas_md > np.percentile(atlas_md[brain], md_pct)) & (atlas_fa < fa_max) & inner
    roi = ndimage.binary_opening(roi, BLOB_STRUCT, 1)
    lab, _ = ndimage.label(roi, structure=BLOB_STRUCT)
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    keep = [int(i) for i in np.argsort(sizes)[::-1][:top_k] if sizes[i] >= min_size]
    return np.isin(lab, keep) if keep else np.zeros(atlas_fa.shape, bool)


def csf_metrics(subj_fa, subj_md, atlas_md, roi):
    """MD ratio and FA in the ventricle ROI.

    A warp that drags white matter into the ventricles collapses MD there
    (``MDratio`` well below 1) and raises FA (``FAmean`` well above the ~0.05 of
    real CSF), independently of how well the maps agree elsewhere.
    """
    out = {"CSF_MDratio": np.nan, "CSF_FAmean": np.nan}
    if roi is None or not roi.any():
        return out
    a = float(np.mean(atlas_md[roi]))
    if subj_md is not None and abs(a) > 1e-12:
        out["CSF_MDratio"] = float(np.mean(subj_md[roi])) / a
    out["CSF_FAmean"] = float(np.mean(subj_fa[roi]))
    return out


# ---------------------------------------------------------------------------
# Normative model
# ---------------------------------------------------------------------------
def build_normative(sessions, atlas_scalars, atlas_fa, bins, scalar_metrics, do_angular,
                    mask_thr, angular_fa_min, min_count, normative_dir, flip_name="none", atlas_pd=None):
    """Compute and save the age-conditional normative model, per bin."""
    os.makedirs(normative_dir, exist_ok=True)
    ref_affine = nib.load(atlas_scalars["FA"]).affine
    shape = atlas_fa.shape
    atlas_wm = atlas_fa > angular_fa_min

    # mean images of every metric map of the reference scans (QC metrics first), not only the QC metrics
    found = sorted({m for s in sessions for m in s["scalars"]})
    mean_metrics = [m for m in scalar_metrics if m in found] + [m for m in ALL_SCALARS if m in found and m not in scalar_metrics] \
        + [m for m in found if m not in scalar_metrics and m not in ALL_SCALARS]
    do_tensor = any(s["tensor"] for s in sessions)
    tensor_header = nrrd.read_header(next(s["tensor"] for s in sessions if s["tensor"])) if do_tensor else None
    log.info("normative mean images: %s%s", ", ".join(mean_metrics), ", DTI (log-Euclidean)" if do_tensor else "")

    manifest = {"bins": [b[2] for b in bins], "scalar_metrics": mean_metrics,
                "angular": do_angular, "mask_threshold": mask_thr,
                "angular_fa_min": angular_fa_min, "min_count": min_count, "tensor_flip": flip_name,
                "tensor_mean": "logEuclidean" if do_tensor else None}

    for lo, hi, label in bins:
        subs = [s for s in sessions if lo <= s["age"] <= hi]
        if not subs:
            log.info("bin %s: no reference subjects", label)
            continue
        log.info("bin %s: %d reference subjects", label, len(subs))
        bin_dir = os.path.join(normative_dir, label)
        os.makedirs(bin_dir, exist_ok=True)

        # scalar accumulators
        acc = {m: {"sum": np.zeros(shape, np.float64), "sqsum": np.zeros(shape, np.float64),
                   "cnt": np.zeros(shape, np.float64)} for m in mean_metrics}
        # log-Euclidean tensor accumulator: sum of the matrix logarithms (6 comps) + count
        if do_tensor:
            L = np.zeros((6,) + shape, np.float64)
            Lcnt = np.zeros(shape, np.float64)
        # angular dyadic accumulator T = sum(v vᵀ): 6 unique comps + count
        if do_angular:
            T = np.zeros((6,) + shape, np.float64)
            Tcnt = np.zeros(shape, np.float64)

        for s in subs:
            sfa, _ = load_scalar(s["scalars"]["FA"])
            mask = brain_mask(sfa, atlas_fa, mask_thr)
            for m in mean_metrics:
                if m not in s["scalars"]:
                    continue
                v, _ = load_scalar(s["scalars"][m])
                acc[m]["sum"][mask] += v[mask]
                acc[m]["sqsum"][mask] += v[mask].astype(np.float64) ** 2
                acc[m]["cnt"][mask] += 1.0
            if do_angular and s["tensor"]:
                wm = mask & atlas_wm
                pd = principal_directions(s["tensor"], wm, flip_name)[wm]  # (N,3)
                if atlas_pd is not None:
                    best, best_deg, applied_deg, differs = subject_frame(s["tensor"], wm & (atlas_fa > max(angular_fa_min, 0.3)), atlas_pd, flip_name)
                    if differs:
                        log.warning("%s: tensor frame correction '%s' fits the atlas better than '%s' (%.1f vs %.1f deg); "
                                    "check its tensor orientation before using it in the normative model",
                                    s["id"], best, flip_name, best_deg, applied_deg)
                ii = np.where(wm)
                T[0][ii] += pd[:, 0] * pd[:, 0]; T[1][ii] += pd[:, 0] * pd[:, 1]
                T[2][ii] += pd[:, 0] * pd[:, 2]; T[3][ii] += pd[:, 1] * pd[:, 1]
                T[4][ii] += pd[:, 1] * pd[:, 2]; T[5][ii] += pd[:, 2] * pd[:, 2]
                Tcnt[ii] += 1.0
            if do_tensor and s["tensor"]:
                logs, valid = log_tensors(s["tensor"], mask, flip_name, tensor_header)
                ii = np.where(valid)
                L[:, ii[0], ii[1], ii[2]] += logs
                Lcnt[ii] += 1.0

        # scalar mean/std
        for m in mean_metrics:
            cnt = acc[m]["cnt"]
            ok = cnt >= min_count
            mean = np.full(shape, np.nan, np.float32)
            std = np.full(shape, np.nan, np.float32)
            mean[ok] = (acc[m]["sum"][ok] / cnt[ok]).astype(np.float32)
            var = acc[m]["sqsum"][ok] / cnt[ok] - (acc[m]["sum"][ok] / cnt[ok]) ** 2
            std[ok] = np.sqrt(np.clip(var * cnt[ok] / np.maximum(cnt[ok] - 1, 1), 0, None)).astype(np.float32)
            nib.save(nib.Nifti1Image(mean, ref_affine), os.path.join(bin_dir, f"{m}_mean.nii.gz"))
            nib.save(nib.Nifti1Image(std, ref_affine), os.path.join(bin_dir, f"{m}_std.nii.gz"))
            nib.save(nib.Nifti1Image(cnt.astype(np.float32), ref_affine),
                     os.path.join(bin_dir, f"{m}_count.nii.gz"))

        # angular mean axis (dyadic) + dispersion
        if do_angular:
            mu = np.zeros(shape + (3,), np.float32)
            sigma = np.full(shape, np.nan, np.float32)
            tau1 = np.full(shape, np.nan, np.float32)
            ok = np.where(Tcnt >= min_count)
            if ok[0].size:
                M = np.empty((ok[0].size, 3, 3), np.float64)
                for a, (r, cc) in enumerate([(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)]):
                    M[:, r, cc] = M[:, cc, r] = T[a][ok] / Tcnt[ok]
                w, v = np.linalg.eigh(M)  # ascending
                mu[ok] = v[:, :, -1].astype(np.float32)
                tau1[ok] = w[:, -1].astype(np.float32)
                sigma[ok] = np.sqrt(np.clip(1.0 - w[:, -1], 0, None)).astype(np.float32)
            nib.save(nib.Nifti1Image(mu, ref_affine), os.path.join(bin_dir, "angular_mu.nii.gz"))
            nib.save(nib.Nifti1Image(sigma, ref_affine), os.path.join(bin_dir, "angular_sigma.nii.gz"))
            nib.save(nib.Nifti1Image(tau1, ref_affine), os.path.join(bin_dir, "angular_coherence.nii.gz"))
            nib.save(nib.Nifti1Image(Tcnt.astype(np.float32), ref_affine),
                     os.path.join(bin_dir, "angular_count.nii.gz"))

        # log-Euclidean mean tensor: exp(mean(log D)), zero where fewer than min_count tensors
        if do_tensor:
            mean_tensor = np.zeros((6,) + shape, np.float32)
            ok = np.where(Lcnt >= min_count)
            if ok[0].size:
                mean_tensor[:, ok[0], ok[1], ok[2]] = matrix_function(L[:, ok[0], ok[1], ok[2]] / Lcnt[ok], np.exp)
            header = {k: tensor_header[k] for k in ("space", "space directions", "space origin", "kinds", "measurement frame")
                      if k in tensor_header}
            header["encoding"] = "gzip"
            nrrd.write(os.path.join(bin_dir, "DTI_mean.nrrd"), mean_tensor, header)
            nib.save(nib.Nifti1Image(Lcnt.astype(np.float32), ref_affine), os.path.join(bin_dir, "DTI_count.nii.gz"))

    with open(os.path.join(normative_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    log.info("Wrote normative model to %s/", normative_dir)


def load_normative_scalar(normative_dir, label, metric):
    base = os.path.join(normative_dir, label, metric)
    if not os.path.isfile(base + "_mean.nii.gz"):
        return None
    mean = np.asanyarray(nib.load(base + "_mean.nii.gz").dataobj, dtype=np.float32)
    std = np.asanyarray(nib.load(base + "_std.nii.gz").dataobj, dtype=np.float32)
    return mean, std


def check_normative_frame(normative_dir, bins, atlas_pd, atlas_fa, angular_fa_min, flip_name,
                          max_deg=30.0):
    """Verify the normative angular model lives in the atlas tensor frame.

    A model accumulated under a different axis reflection than the QC applies
    would silently corrupt every ``ANG_*Z``.  The manifest records the flip that
    was *requested* at build time, which can be stale or simply wrong, so check
    the model itself: ``angular_mu`` and the atlas principal directions describe
    the same anatomy, and must agree to within a few degrees over core WM.
    """
    core = atlas_fa > max(angular_fa_min, 0.3)
    meds = {}
    for _, _, label in bins:
        na = load_normative_angular(normative_dir, label)
        if na is None:
            continue
        mu, _ = na
        v = core & (np.linalg.norm(mu, axis=-1) > 0)
        if v.sum() < 1000:
            continue
        dot = np.clip(np.abs(np.sum(mu[v] * atlas_pd[v], axis=-1)), 0, 1)
        meds[label] = float(np.median(np.degrees(np.arccos(dot))))
    if not meds:
        return
    worst = max(meds.values())
    try:
        with open(os.path.join(normative_dir, "manifest.json")) as fh:
            nf = json.load(fh).get("tensor_flip", "none")
    except OSError:
        nf = None
    if worst > max_deg:
        log.warning("normative angular frame disagrees with the atlas (median mu-vs-atlas "
                    "angle %s); rebuild it with --tensor-flip %s or the ANG_*Z are meaningless",
                    ", ".join(f"{k} {v:.0f}deg" for k, v in meds.items()), flip_name)
    else:
        log.info("normative angular frame matches the atlas (median mu-vs-atlas angle %s)",
                 ", ".join(f"{k} {v:.0f}deg" for k, v in meds.items()))
        if nf is not None and nf != flip_name:
            log.info("  (manifest says tensor_flip='%s' and QC detected '%s', but the stored "
                     "directions are consistent -- the manifest label is stale)", nf, flip_name)


def check_normative_thresholds(normative_dir, mask_thr, angular_fa_min, do_angular):
    """FA thresholds in force vs the ones the normative model was built with.

    Both thresholds define the *voxel support* the model's per-voxel statistics
    were accumulated over, so a mismatch silently standardises the subject over
    a different set of voxels than the reference mean/std describe.  Returns the
    list of ``(flag, model_value, current_value)`` that disagree.
    """
    path = os.path.join(normative_dir, "manifest.json")
    try:
        with open(path) as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        log.warning("cannot read %s (%s); the model's FA thresholds were not verified", path, exc)
        return []

    checks = [("mask_threshold", "--mask-threshold", mask_thr)]
    if do_angular:
        checks.append(("angular_fa_min", "--angular-fa-min", angular_fa_min))
    bad, verified = [], []
    for key, flag, current in checks:
        ref = manifest.get(key)
        if ref is None:  # model predates the manifest entry
            log.warning("%s does not record '%s'; cannot verify that %s %g matches the model",
                        path, key, flag, current)
        elif not math.isclose(float(ref), float(current), rel_tol=1e-9, abs_tol=1e-12):
            bad.append((flag, float(ref), float(current)))
        else:
            verified.append(f"{flag} {current:g}")
    if verified and not bad:
        log.info("normative FA thresholds match the model (%s)", ", ".join(verified))
    return bad


def load_normative_angular(normative_dir, label):
    d = os.path.join(normative_dir, label)
    if not os.path.isfile(os.path.join(d, "angular_mu.nii.gz")):
        return None
    mu = np.asanyarray(nib.load(os.path.join(d, "angular_mu.nii.gz")).dataobj, dtype=np.float32)
    sigma = np.asanyarray(nib.load(os.path.join(d, "angular_sigma.nii.gz")).dataobj, dtype=np.float32)
    return mu, sigma


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------
def make_preview(sid, atlas_fa, subj_fa, maps, out_dir):
    """One PNG per subject: atlas FA, DTI FA, FA diff, FA SSIM, angular error z,
    and the largest contiguous disagreement blobs over the subject FA."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    k = int(np.argmax([(atlas_fa[:, :, z] > 0.2).sum() for z in range(atlas_fa.shape[2])]))  # most-WM slice
    sl = lambda a: np.rot90(a[:, :, k])
    panels = [("Atlas FA", sl(atlas_fa), "gray", (0, 1)),
              ("DTI FA", sl(subj_fa), "gray", (0, 1))]
    if "FA_diff" in maps:
        panels.append(("FA diff (subj−atlas)", sl(maps["FA_diff"]), "RdBu_r", (-0.4, 0.4)))
    if "FA_ssim" in maps:
        panels.append(("FA SSIM", sl(maps["FA_ssim"]), "viridis", (0, 1)))
    if "angular_z" in maps:
        panels.append(("Angular error z", sl(maps["angular_z"]), "inferno", (0, 3)))
    elif "angular_deg" in maps:
        panels.append(("Angular error (deg)", sl(maps["angular_deg"]), "hot", (0, 60)))
    blob_key = next((k for k in ("FA_z_blobs", "FA_ssim_blobs", "angular_z_blobs",
                                 "angular_deg_blobs") if k in maps), None)
    if blob_key is not None:
        panels.append((f"Largest blobs ({blob_key[:-6]})", sl(maps[blob_key]), None, (0, 1)))

    fig, axes = plt.subplots(1, len(panels), figsize=(4 * len(panels), 4.6))
    for ax, (title, img, cm, (vlo, vhi)) in zip(np.atleast_1d(axes), panels):
        if cm is None:  # blob overlay on the subject FA
            ax.imshow(sl(subj_fa), cmap="gray", vmin=0, vmax=1)
            ax.imshow(np.ma.masked_where(img == 0, img), cmap="autumn", vmin=0, vmax=1, alpha=0.65)
        else:
            im = ax.imshow(img, cmap=cm, vmin=vlo, vmax=vhi)
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
        ax.set_title(title, fontsize=11); ax.axis("off")
    fig.suptitle(f"Registration QC — {sid} (axial z={k})", fontsize=13)
    fig.tight_layout()
    prev_dir = os.path.join(out_dir, "previews")
    os.makedirs(prev_dir, exist_ok=True)
    fig.savefig(os.path.join(prev_dir, f"{sid}_preview.png"), dpi=110)
    plt.close(fig)


def qc_subject(s, atlas, bins, normative_dir, cfg, out_dir=None):
    """Score one session vs atlas (+ normative); return a row dict.

    When *out_dir* is given, also save the NIfTI disagreement maps and a preview
    PNG (used only for the subjects we choose to write out).
    """
    atlas_scalars, atlas_fa = atlas["scalars"], atlas["fa"]
    atlas_pd, atlas_wm, ref_affine = atlas["pd"], atlas["wm"], atlas["affine"]
    sfa, _ = load_scalar(s["scalars"]["FA"])
    mask = brain_mask(sfa, atlas_fa, cfg["mask_thr"])
    label = bin_label_for_age(s["age"], bins)
    row = {"id": s["id"], "subject": s["subject"], "session": s["session"],
           "prefix": s.get("prefix", ""), "age": s["age"], "bin": label}
    save_maps = out_dir is not None
    maps = {}  # name -> full-volume array (only populated when saving)

    # --- scalar metrics ---
    for m in cfg["scalar_metrics"]:
        if m not in s["scalars"]:
            continue
        v, _ = load_scalar(s["scalars"][m])
        dr = float(atlas_scalars[m][mask].max() - atlas_scalars[m][mask].min()) or 1.0
        row[f"{m}_MAE"] = masked_mae(v, atlas_scalars[m], mask)
        row[f"{m}_NCC"] = masked_ncc(v, atlas_scalars[m], mask)
        ssim_mean, ssim_map = masked_ssim(v, atlas_scalars[m], mask, dr)
        row[f"{m}_SSIM"] = ssim_mean

        # contiguity of the locally-dissimilar voxels (model-free, always available).
        # The cut is the subject's own worst-SSIM percentile: an absolute SSIM floor
        # saturates (every session merges into one brain-sized blob), whereas fixing
        # the *number* of extreme voxels isolates how clustered they are.
        ssim_cut = float(np.percentile(ssim_map[mask], cfg["ssim_blob_pct"])) if mask.any() else 0.0
        st, ssim_blobs = blob_stats(ssim_map < ssim_cut, mask, cfg["blob_top_k"])
        add_blob_row(row, f"{m}_ssim", st)

        znorm = load_normative_scalar(normative_dir, label, m) if (normative_dir and label) else None
        z, z_blobs = None, None
        if znorm is not None:
            mean, std = znorm
            valid = mask & np.isfinite(mean) & np.isfinite(std) & (std > 0)
            z = np.zeros(mask.shape, np.float32)
            z[valid] = (v[valid] - mean[valid]) / std[valid]
            row[f"{m}_meanAbsZ"] = float(np.mean(np.abs(z[valid]))) if valid.any() else np.nan
            row[f"{m}_fracZgt"] = float(np.mean(np.abs(z[valid]) > cfg["z_thresh"])) if valid.any() else np.nan
            st, z_blobs = blob_stats(np.abs(z) > cfg["z_thresh"], valid, cfg["blob_top_k"])
            add_blob_row(row, f"{m}_z", st)
        if save_maps and m == "FA":
            diff = np.zeros(mask.shape, np.float32); diff[mask] = v[mask] - atlas_scalars[m][mask]
            smap = np.zeros(mask.shape, np.float32); smap[mask] = ssim_map[mask]
            maps["FA_diff"] = diff
            maps["FA_ssim"] = smap
            maps["FA_ssim_blobs"] = ssim_blobs
            if z is not None:
                maps["FA_z"] = z
                maps["FA_z_blobs"] = z_blobs

    # --- angular ---
    if cfg["do_angular"] and s["tensor"] is not None and atlas_pd is not None:
        wm = mask & atlas_wm
        pd = principal_directions(s["tensor"], wm, cfg["flip"])
        core = wm & (atlas_fa > max(cfg["angular_fa_min"], 0.3))  # core white matter, as the dataset detection
        if core.sum() >= 1000:
            best, best_deg, applied_deg, differs = subject_frame(s["tensor"], core, atlas_pd, cfg["flip"])
            row["TENSOR_frame_best"] = best
            row["TENSOR_frame_gain_deg"] = applied_deg - best_deg
            if differs:
                log.warning("%s: tensor frame correction '%s' fits the atlas better than the applied '%s' "
                            "(%.1f vs %.1f deg): its tensor orientation differs from the other subjects",
                            s["id"], best, cfg["flip"], best_deg, applied_deg)
        ang = angular_error_deg(pd, atlas_pd, wm)
        row["ANG_meanDeg"] = float(np.mean(ang[wm])) if wm.any() else np.nan
        st, ang_blobs = blob_stats(ang > cfg["ang_blob_deg"], wm, cfg["blob_top_k"])
        add_blob_row(row, "ANG_deg", st)
        if save_maps:
            maps["angular_deg"] = ang
            maps["angular_deg_blobs"] = ang_blobs

        na = load_normative_angular(normative_dir, label) if (normative_dir and label) else None
        if na is not None:
            mu, sigma = na
            valid = wm & np.isfinite(sigma) & (np.linalg.norm(mu, axis=-1) > 0)
            zang = np.zeros(mask.shape, np.float32)
            if valid.any():
                dot = np.abs(np.sum(pd[valid] * mu[valid], axis=-1))
                np.clip(dot, 0.0, 1.0, out=dot)
                sin_d = np.sqrt(np.clip(1.0 - dot ** 2, 0, None))
                zang[valid] = sin_d / np.maximum(sigma[valid], cfg["angular_sigma_floor"])
            row["ANG_meanZ"] = float(np.mean(zang[valid])) if valid.any() else np.nan
            row["ANG_fracZgt"] = float(np.mean(zang[valid] > cfg["z_thresh"])) if valid.any() else np.nan
            st, zang_blobs = blob_stats(zang > cfg["z_thresh"], valid, cfg["blob_top_k"])
            add_blob_row(row, "ANG_z", st)
            if save_maps:
                maps["angular_z"] = zang
                maps["angular_z_blobs"] = zang_blobs

    # --- CSF / ventricle sanity check ---
    if atlas.get("csf_roi") is not None:
        smd = load_scalar(s["scalars"]["MD"])[0] if "MD" in s["scalars"] else None
        row.update(csf_metrics(sfa, smd, atlas["md"], atlas["csf_roi"]))

    # --- write maps + preview ---
    if save_maps and maps:
        sub_out = os.path.join(out_dir, "maps")
        os.makedirs(sub_out, exist_ok=True)
        for name, arr in maps.items():
            nib.save(nib.Nifti1Image(arr, ref_affine), os.path.join(sub_out, f"{s['id']}_{name}.nii.gz"))
        make_preview(s["id"], atlas_fa, sfa, maps, out_dir)
    return row


def robust_z(x):
    """MAD-based z-score (median/1.4826·MAD); 0 where scale is degenerate."""
    x = np.asarray(x, dtype=float)
    if x.size == 0 or not np.isfinite(x).any():  # empty cohort / metric never computed
        return np.zeros_like(x)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    scale = 1.4826 * mad
    if scale < 1e-12:
        return np.zeros_like(x)
    return (x - med) / scale


# ---------------------------------------------------------------------------
# Combined score
# ---------------------------------------------------------------------------
def worseness_features(df, scalar_metrics, do_angular):
    """(X, names): the metric vector per session, oriented so higher = worse.

    Left out on purpose: ``*BlobConc`` / ``*BlobN`` (concentration is NaN when
    few voxels are extreme, and the count is not a severity), and
    ``*ssimBlobFrac``, whose cut is a per-subject percentile -- it measures how
    *clustered* the worst voxels are, which is not monotone in badness (a
    globally bad warp spreads its worst 5% out again).  Both stay in the table
    as diagnostics.
    """
    cols, names = [], []

    def take(name, values):
        v = np.asarray(values, dtype=float)
        if np.isfinite(v).sum() >= max(3, 0.5 * len(v)):
            cols.append(v)
            names.append(name)

    for m in scalar_metrics:
        if f"{m}_MAE" in df:
            take(f"{m}_MAE", df[f"{m}_MAE"])
            take(f"{m}_1-SSIM", 1.0 - df[f"{m}_SSIM"])
            take(f"{m}_1-NCC", 1.0 - df[f"{m}_NCC"])
        for c in (f"{m}_meanAbsZ", f"{m}_fracZgt", f"{m}_zBlobFrac"):
            if c in df:
                take(c, df[c])
    if do_angular:
        for c in ("ANG_meanDeg", "ANG_meanZ", "ANG_fracZgt", "ANG_degBlobFrac", "ANG_zBlobFrac"):
            if c in df:
                take(c, df[c])
    if "CSF_MDratio" in df:
        take("CSF_1-MDratio", 1.0 - df["CSF_MDratio"])
    if "CSF_FAmean" in df:
        take("CSF_FAmean", df["CSF_FAmean"])
    if not cols:
        return np.zeros((len(df), 0)), []
    return np.column_stack(cols), names


def robust_mahalanobis(X, names, support=0.85, min_ratio=5.0, corr_max=0.995):
    """Robust (MCD) Mahalanobis distance over the metric vector.

    The metrics are heavily correlated (MAE/SSIM/NCC on the same map measure
    nearly the same thing), which a plain mean triple-counts; the Mahalanobis
    distance whitens that away and lets a single severe failure stand out
    instead of being averaged down.  The centre and covariance come from the
    cleanest *support* fraction of the cohort (Minimum Covariance Determinant),
    so the failures themselves cannot inflate the reference spread.

    Voxel-*fraction* features (``*fracZgt``, ``*BlobFrac``) sit near zero and
    span orders of magnitude; they are put on a log scale first, otherwise their
    tiny MAD makes them dominate the distance.

    Returns None when the cohort is too small (n < *min_ratio* x features),
    otherwise ``(d, contrib_names, bad_side, used_names)`` where *d* is the
    distance, *contrib_names* names the largest contributor to d^2 per session,
    and *bad_side* is True where the session deviates towards *worse* metrics.
    """
    n = X.shape[0]
    if X.shape[1] == 0 or n < 4:
        return None

    # robust standardisation (conditioning only; Mahalanobis is scale-invariant)
    Z, keep = [], []
    for j, name in enumerate(names):
        col = X[:, j].astype(float)
        finite = np.isfinite(col)
        if not finite.any():
            log.debug("mahalanobis: dropping all-NaN feature %s", name)
            continue
        col = np.where(finite, col, np.median(col[finite]))  # median-impute
        if "frac" in name.lower():  # voxel fractions -> log scale
            pos = col[col > 0]
            col = np.log10(col + (pos.min() / 2 if pos.size else 1e-9))
        med = np.median(col)
        scale = 1.4826 * np.median(np.abs(col - med))
        if not np.isfinite(scale) or scale < 1e-12:
            log.debug("mahalanobis: dropping degenerate feature %s", name)
            continue
        Z.append((col - med) / scale)
        keep.append(name)
    if not Z:
        return None
    Z = np.column_stack(Z)

    # drop near-duplicate features so the covariance stays invertible
    sel = []
    for j in range(Z.shape[1]):
        if all(abs(np.corrcoef(Z[:, j], Z[:, k])[0, 1]) <= corr_max for k in sel):
            sel.append(j)
        else:
            log.debug("mahalanobis: dropping collinear feature %s", keep[j])
    Z, used = Z[:, sel], [keep[j] for j in sel]

    p = Z.shape[1]
    if n < min_ratio * p:
        log.warning("mahalanobis needs n >= %.0f x features (%d < %.0f x %d)",
                    min_ratio, n, min_ratio, p)
        return None

    try:
        from sklearn.covariance import MinCovDet
        fit = MinCovDet(support_fraction=support, random_state=0).fit(Z)
        loc, cov = fit.location_, fit.covariance_
    except Exception as exc:  # sklearn missing, or MCD failed to converge
        log.warning("MCD unavailable/failed (%s); using the central %.0f%% for the covariance",
                    exc, 100 * support)
        d0 = np.linalg.norm(Z - np.median(Z, axis=0), axis=1)
        core = Z[d0 <= np.percentile(d0, 100 * support)]
        loc, cov = np.median(core, axis=0), np.cov(core, rowvar=False)
        cov = np.atleast_2d(cov)
    cov = cov + np.eye(p) * (1e-6 * max(np.trace(cov) / p, 1e-12))  # ridge
    inv = np.linalg.pinv(cov)

    dev = Z - loc
    # per-feature contributions sum exactly to d^2 (order-independent)
    contrib = dev * (dev @ inv)
    d2 = np.clip(contrib.sum(axis=1), 0.0, None)
    top = [used[j] for j in np.argmax(contrib, axis=1)]
    return np.sqrt(d2), top, dev.mean(axis=1) > 0, used


def _tensor_flip_arg(value):
    if str(value).strip().lower() == "auto":
        return "auto"
    try:
        return correction_name(*parse_correction(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def configure_parser(p):
    p.add_argument("--data-dir", default="RegistrationData", help="Root with sub-*/ses-*/AtlasReg (or DTI_Register outputs <scan>_Registered_<METRIC>.nii.gz, "
                        "<scan>_DTI_Registered.nrrd in any subfolder) + Atlas/")
    p.add_argument("--atlas-dir", default=None, help="Atlas folder (default: <data-dir>/Atlas)")
    p.add_argument("--out-dir", default="RegistrationQC", help="QC output folder")
    p.add_argument("--reference-dir", default=None, help="Reference cohort for --build-normative (default: --data-dir)")
    p.add_argument("--normative-dir", default=None, help="Age-conditional normative model folder (read or write)")
    p.add_argument("--build-normative", action="store_true",
                   help="Build the normative model (mean/std of all metric maps, angular model, mean tensor) and exit")
    p.add_argument("--bins", default="0-3,4-9,10-60", help="Age bins (months, inclusive; oldest open-ended)")
    p.add_argument("--age-csv", default=None,
                   help="CSV/TSV with per-subject (and optionally per-session) ages, for cohorts whose "
                        "session names carry a visit label instead of an age (e.g. ses-V02); columns "
                        "participant_id/session_id/age are auto-detected, as is any column "
                        "whose name contains 'candidate_age'")
    p.add_argument("--age-column", default=None, metavar="NAME",
                   help="Name of the --age-csv column holding the age (default: auto-detect)")
    p.add_argument("--age-units", default="months", choices=sorted(AGE_UNIT_TO_MONTHS),
                   help="Units of the --age-csv age column (default: months)")
    p.add_argument("--age-regex", default=AGE_RE.pattern,
                   help=f"Regex whose first group is the session-name age in months (default: {AGE_RE.pattern!r})")
    p.add_argument("--scalar-metrics", default="FA", help="Comma list of scalar metrics to QC (default: FA)")
    p.add_argument("--no-angular", action="store_true", help="Skip the tensor angular-error metric")
    p.add_argument("--mask-threshold", type=float, default=1e-3, help="FA threshold for the brain mask (default: 1e-3)")
    p.add_argument("--angular-fa-min", type=float, default=0.2, help="Atlas FA floor for WM angular region (default: 0.2)")
    p.add_argument("--tensor-flip", default="auto", type=_tensor_flip_arg,
                   help="Tensor frame correction of the subject tensors: auto (default: detected against the atlas), "
                        "none, axes to flip (x, y, z, e.g. x or x,z), or voxel for components in the frame of the voxel "
                        "axes (with flips e.g. voxel,x), as detect-tensor-flip; every subject is also checked on its own")
    p.add_argument("--angular-sigma-floor", type=float, default=0.035, help="Floor on angular dispersion (~sin 2°)")
    p.add_argument("--min-count", type=int, default=2, help="Min reference subjects per voxel for a valid normative")
    p.add_argument("--ignore-threshold-mismatch", action="store_true",
                   help="Downgrade the FA-threshold mismatch against the normative model from an "
                        "error to a warning (the z-scores are then not comparable to the model)")
    p.add_argument("--z-thresh", type=float, default=3.0, help="|z| threshold for extreme-voxel fractions (default: 3)")
    p.add_argument("--ssim-blob-pct", type=float, default=5.0,
                   help="Worst-SSIM percentile defining a dissimilar voxel for the blob metrics (default: 5)")
    p.add_argument("--ang-blob-deg", type=float, default=40.0,
                   help="Angular-error floor (deg) defining a bad voxel for the blob metrics (default: 40)")
    p.add_argument("--blob-top-k", type=int, default=3, help="Blobs summed for the concentration metric (default: 3)")
    p.add_argument("--no-csf-check", action="store_true", help="Skip the CSF/ventricle sanity check")
    p.add_argument("--csf-md-pct", type=float, default=95.0,
                   help="Atlas-MD percentile defining the CSF ROI (default: 95)")
    p.add_argument("--csf-fa-max", type=float, default=0.15, help="Atlas-FA ceiling for the CSF ROI (default: 0.15)")
    p.add_argument("--csf-erode", type=int, default=8,
                   help="Brain-mask erosion (voxels) keeping the CSF ROI deep (default: 8)")
    p.add_argument("--combine", default="robust-z", choices=["robust-z", "mahalanobis"],
                   help="Rule turning the metrics into the outlier flag (default: robust-z). The "
                        "Mahalanobis score is written to the table either way.")
    p.add_argument("--outlier-chi2-p", type=float, default=1e-3,
                   help="Chi-square tail probability for the Mahalanobis cutoff (default: 1e-3)")
    p.add_argument("--mahal-support", type=float, default=0.85,
                   help="Fraction of the cohort the MCD covariance is estimated from (default: 0.85)")
    p.add_argument("--outlier-mad", type=float, default=3.5, help="Robust-z cutoff on the combined score (default: 3.5)")
    p.add_argument("--save-all-maps", action="store_true",
                   help="Write disagreement maps + previews for every session (default: only flagged outliers)")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    return p


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    configure_parser(p)
    args = p.parse_args(argv)
    return run_args(args, p)


def run_args(args, p) -> int:
    from dtiplayground.dmri.fiberprofile.analysis import setup_logging
    setup_logging(args.verbose)

    atlas_dir = args.atlas_dir or os.path.join(args.data_dir, "Atlas")
    atlas_scalar_paths, atlas_tensor = find_atlas(atlas_dir)
    if "FA" not in atlas_scalar_paths:
        p.error(f"atlas FA not found in {atlas_dir}")
    scalar_metrics = [m.strip() for m in args.scalar_metrics.split(",") if m.strip()]
    scalar_metrics = [m for m in scalar_metrics if m in atlas_scalar_paths]
    do_angular = (not args.no_angular) and atlas_tensor is not None
    bins = parse_bins(args.bins)

    try:
        age_re = re.compile(args.age_regex)
    except re.error as exc:
        p.error(f"--age-regex is not a valid regex: {exc}")
    age_table = None
    if args.age_column and not args.age_csv:
        p.error("--age-column only applies to --age-csv")
    if args.age_csv:
        try:
            age_table = load_age_table(args.age_csv, args.age_units, args.age_column)
        except (OSError, ValueError) as exc:
            p.error(f"--age-csv: {exc}")

    atlas_fa, _ = load_scalar(atlas_scalar_paths["FA"])
    atlas_wm = atlas_fa > args.angular_fa_min
    atlas_pd = principal_directions(atlas_tensor, atlas_wm) if do_angular else None

    def resolve_flip(sessions):
        if not do_angular or atlas_pd is None:
            return "none"
        if args.tensor_flip != "auto":
            return correction_name(*parse_correction(args.tensor_flip))
        name, med = detect_tensor_flip(sessions, atlas_pd, atlas_fa,
                                       args.mask_threshold, args.angular_fa_min)
        log.info("Auto-detected tensor frame correction: '%s' (median core-WM angular error %.1f°)", name, med)
        if name != "none":
            log.info("  -> applying the tensor frame correction '%s' to the subject tensors", name)
        return name

    if args.build_normative:
        ref_dir = args.reference_dir or args.data_dir
        if not args.normative_dir:
            p.error("--build-normative requires --normative-dir")
        sessions = find_sessions(ref_dir, age_table, age_re)
        if not sessions:
            log.error("no reference sessions found under %s -- expected %s/sub-*/ses-*/AtlasReg/*_Deformed*.nii.gz "
                      "or DTI_Register outputs sub-<id>_ses-<id>_*_Registered_<METRIC>.nii.gz below it", ref_dir, ref_dir)
            return 1
        dated = [s for s in sessions if s["age"] is not None]
        if len(dated) < len(sessions):
            undated = [s["id"] for s in sessions if s["age"] is None]
            log.warning("skipping %d of %d reference session(s) without an age (%s%s): the "
                        "normative model is age-binned, so supply --age-csv (or --age-regex) "
                        "to include them", len(undated), len(sessions), ", ".join(undated[:3]),
                        ", ..." if len(undated) > 3 else "")
        if not dated:
            log.error("no reference session has an age, so no age bin can be filled; "
                      "supply --age-csv with the ages for %s", ref_dir)
            return 1
        sessions = dated
        log.info("Building normative from %d reference sessions in %s", len(sessions), ref_dir)
        flip_name = resolve_flip(sessions)
        build_normative(sessions, atlas_scalar_paths, atlas_fa, bins, scalar_metrics, do_angular,
                        args.mask_threshold, args.angular_fa_min, args.min_count, args.normative_dir,
                        flip_name, atlas_pd)
        return 0

    # --- QC mode ---
    os.makedirs(args.out_dir, exist_ok=True)
    # an atlas folder may ship its own model (<atlas-dir>/normativeModel/)
    cand = args.normative_dir or os.path.join(atlas_dir, "normativeModel")
    normative_dir = cand if os.path.isfile(os.path.join(cand, "manifest.json")) else None
    if normative_dir and not args.normative_dir:
        log.info("using the normative model shipped with the atlas: %s", normative_dir)
    log.info("Metrics: scalars=%s angular=%s | normative=%s",
             scalar_metrics, do_angular, normative_dir or "(none -> raw, age-confounded)")

    atlas_scalars = {m: load_scalar(atlas_scalar_paths[m])[0] for m in scalar_metrics}
    ref_affine = nib.load(atlas_scalar_paths["FA"]).affine
    atlas = {"scalars": atlas_scalars, "fa": atlas_fa, "pd": atlas_pd, "wm": atlas_wm,
             "affine": ref_affine, "md": None, "csf_roi": None}

    # CSF / ventricle ROI (needs the atlas MD map, which may not be a --scalar-metric)
    if not args.no_csf_check:
        if "MD" not in atlas_scalar_paths:
            log.warning("no atlas MD map in %s; skipping the CSF sanity check", atlas_dir)
        else:
            atlas["md"] = atlas_scalars.get("MD")
            if atlas["md"] is None:
                atlas["md"], _ = load_scalar(atlas_scalar_paths["MD"])
            roi = build_csf_roi(atlas_fa, atlas["md"], args.mask_threshold, args.csf_md_pct,
                                args.csf_fa_max, args.csf_erode, top_k=3)
            if not roi.any():
                log.warning("CSF ROI came out empty; skipping the CSF sanity check")
            else:
                atlas["csf_roi"] = roi
                nib.save(nib.Nifti1Image(roi.astype(np.uint8), ref_affine),
                         os.path.join(args.out_dir, "csf_roi.nii.gz"))
                log.info("CSF ROI: %d voxels (atlas FA %.3f, MD %.3g) -> %s/csf_roi.nii.gz",
                         int(roi.sum()), float(atlas_fa[roi].mean()), float(atlas["md"][roi].mean()),
                         args.out_dir)

    if normative_dir:
        bad = check_normative_thresholds(normative_dir, args.mask_threshold,
                                         args.angular_fa_min, do_angular)
        if bad:
            for flag, ref, current in bad:
                log.error("normative model was built with %s %g, this run uses %g",
                          flag, ref, current)
            log.error("the FA thresholds set the voxel support of every metric, so the z-scores "
                      "would not be comparable with the model's mean/std -- rerun with %s, "
                      "rebuild the model, or pass --ignore-threshold-mismatch",
                      " ".join(f"{flag} {ref:g}" for flag, ref, _ in bad))
            if not args.ignore_threshold_mismatch:
                return 1
            log.warning("--ignore-threshold-mismatch given: continuing with mismatched thresholds")

    sessions = find_sessions(args.data_dir, age_table, age_re)
    if not sessions:
        log.error("no sessions found under %s -- expected %s/sub-*/ses-*/AtlasReg/*_Deformed*.nii.gz "
                  "or DTI_Register outputs sub-<id>_ses-<id>_*_Registered_<METRIC>.nii.gz below it",
                  args.data_dir, args.data_dir)
        return 1
    flip_name = resolve_flip(sessions)
    if normative_dir and do_angular and atlas_pd is not None:
        check_normative_frame(normative_dir, bins, atlas_pd, atlas_fa, args.angular_fa_min, flip_name)

    cfg = {"scalar_metrics": scalar_metrics, "do_angular": do_angular, "mask_thr": args.mask_threshold,
           "angular_fa_min": args.angular_fa_min, "angular_sigma_floor": args.angular_sigma_floor,
           "z_thresh": args.z_thresh, "flip": flip_name,
           "ssim_blob_pct": args.ssim_blob_pct, "ang_blob_deg": args.ang_blob_deg,
           "blob_top_k": args.blob_top_k}

    if normative_dir:
        dated = [s for s in sessions if s["age"] is not None]
        if len(dated) < len(sessions):
            undated = [s["id"] for s in sessions if s["age"] is None]
            log.warning("skipping %d of %d session(s) without an age (%s%s): they cannot be placed "
                        "in a normative age bin -- supply --age-csv (or --age-regex), or drop "
                        "--normative-dir to run the raw atlas-comparison QC on the whole cohort",
                        len(undated), len(sessions), ", ".join(undated[:3]),
                        ", ..." if len(undated) > 3 else "")
        if not dated:
            log.error("no session has an age, so none can be matched to a normative bin; "
                      "supply --age-csv, or run without a normative model")
            return 1
        sessions = dated

    log.info("QC on %d sessions", len(sessions))

    save_all = args.save_all_maps
    rows, scored = [], []
    for s in sessions:
        if "FA" not in s["scalars"]:
            log.warning("%s: no FA; skipping", s["id"])
            continue
        rows.append(qc_subject(s, atlas, bins, normative_dir, cfg, args.out_dir if save_all else None))
        scored.append(s)
        log.info("  scored %s (age %s, bin %s)%s", s["id"],
                 f"{s['age']}m" if s["age"] is not None else "unknown", rows[-1]["bin"],
                 " [maps saved]" if save_all else "")

    if not rows:
        log.error("none of the %d session(s) under %s had a deformed FA map, so nothing was scored; "
                  "check that AtlasReg contains *_DeformedFA.nii.gz or that DTI_Register wrote "
                  "*_Registered_FA.nii.gz (or adjust --scalar-metrics)",
                  len(sessions), args.data_dir)
        return 1

    import pandas as pd
    df = pd.DataFrame(rows)

    # --- combined per-subject score + outlier flag ---
    if normative_dir:
        prim = [f"{m}_meanAbsZ" for m in scalar_metrics if f"{m}_meanAbsZ" in df]
        if do_angular and "ANG_meanZ" in df:
            prim.append("ANG_meanZ")
        df["combined_score"] = df[prim].mean(axis=1)
    else:
        parts = []
        for m in scalar_metrics:
            if f"{m}_MAE" in df:
                parts.append(robust_z(df[f"{m}_MAE"].to_numpy()))
                parts.append(robust_z(1.0 - df[f"{m}_SSIM"].to_numpy()))
                parts.append(robust_z(1.0 - df[f"{m}_NCC"].to_numpy()))
        if do_angular and "ANG_meanDeg" in df:
            parts.append(robust_z(df["ANG_meanDeg"].to_numpy()))
        df["combined_score"] = np.mean(np.vstack(parts), axis=0) if parts else np.nan

    unscored = [r.id for r in df.itertuples() if not np.isfinite(r.combined_score)]
    if unscored:
        log.warning("%d of %d session(s) have no combined score and can never be flagged (%s%s): "
                    "their metrics are missing -- with a normative model this usually means the "
                    "model has no data for their age bin (%s)",
                    len(unscored), len(df), ", ".join(unscored[:3]),
                    ", ..." if len(unscored) > 3 else "",
                    ", ".join(sorted({str(b) for b in df.loc[df["id"].isin(unscored), "bin"]})))

    df["combined_robust_z"] = robust_z(df["combined_score"].to_numpy())

    # --- Mahalanobis: always scored, flags only when it is the selected rule ---
    X, names = worseness_features(df, scalar_metrics, do_angular)
    mah = robust_mahalanobis(X, names, support=args.mahal_support)
    mahal_flag = None
    if mah is not None:
        d, top, bad_side, used = mah
        mcut = float(np.sqrt(stats.chi2.ppf(1.0 - args.outlier_chi2_p, len(used))))
        df["mahalanobis_d"] = d
        df["mahalanobis_p"] = stats.chi2.sf(d ** 2, len(used))
        df["mahal_top_contrib"] = top
        # one-sided: only sessions deviating towards *worse* metrics are failures
        mahal_flag = (d > mcut) & bad_side
        log.info("Mahalanobis on %d features (%s), MCD support %.0f%%: d > %.2f "
                 "(chi2 p=%g) would flag %d/%d",
                 len(used), ", ".join(used), 100 * args.mahal_support, mcut,
                 args.outlier_chi2_p, int(mahal_flag.sum()), len(df))
        if mahal_flag.mean() > 0.10:
            log.warning("  that is %.0f%% of the cohort: the metric tail is heavier than chi-square "
                        "predicts, so tighten --outlier-chi2-p before using --combine mahalanobis",
                        100 * mahal_flag.mean())
    elif args.combine == "mahalanobis":
        log.warning("Mahalanobis not usable on this cohort; falling back to the robust-z rule")

    if args.combine == "mahalanobis" and mahal_flag is not None:
        rule, cutoff = "mahalanobis", mcut
        df["is_outlier"] = mahal_flag
    else:
        rule, cutoff = "robust-z", args.outlier_mad
        df["is_outlier"] = df["combined_robust_z"] > args.outlier_mad
    df["outlier_rule"] = rule

    csv = os.path.join(args.out_dir, "registration_qc.csv")
    df.to_csv(csv, index=False)
    n_out = int(df["is_outlier"].sum())
    log.info("Wrote %s | %d/%d sessions flagged (%s > %.2f)",
             csv, n_out, len(df), "Mahalanobis d" if rule == "mahalanobis" else "combined robust-z",
             cutoff)
    if n_out:
        out = df.loc[df["is_outlier"]]
        log.info("Outliers: %s", ", ".join(
            f"{r.id} ({r.mahal_top_contrib})" for r in out.itertuples()
        ) if rule == "mahalanobis" else ", ".join(out["id"]))

    # --- maps + previews: flagged only (default) or all (already done above) ---
    if save_all:
        log.info("Saved maps + previews for all %d sessions (--save-all-maps)", len(scored))
    else:
        for i in np.where(df["is_outlier"].to_numpy())[0]:
            qc_subject(scored[i], atlas, bins, normative_dir, cfg, args.out_dir)
        log.info("Saved maps + previews for %d flagged session(s) under %s/{maps,previews}", n_out, args.out_dir)
    return 0


### dmrifiberprofile command

def add_parser(subparsers):
    p = subparsers.add_parser("qc-registration", help="QC of the registration of subjects to the atlas (similarity, angular error, normative z-scores, outliers)", description=__doc__,
                              formatter_class=argparse.RawDescriptionHelpFormatter)
    configure_parser(p)
    p.set_defaults(func=lambda args: run_args(args, p))


if __name__ == "__main__":
    sys.exit(main())
