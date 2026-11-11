DTI registration study
======================

This page documents the study (2026-11-08 to 2026-11-10) that replaced the FA-only DTI-Reg registration of
DTI_Register by **TensorSVF**, a diffeomorphic registration of the tensors with an optional free water term. It also
covers the tensor frame correction (``tensorFlip rotation``). The results set the defaults of DTI_Register (v0.9.11 to
v0.9.13; see `DTI_Register <https://github.com/NIRALUser/DTIPlayground/tree/master/dtiplayground/dmri/preprocessing/modules/DTI_Register>`_).

Goal
----

DTI-Reg registers the FA maps (ANTs SyN), so the tensors follow the FA edges, not their own orientation. Its
registrations of the test scans failed the registration QC (``dmrifiberprofile qc-registration``): principal
directions off in the white matter and ventricles of the wrong size. The goal was a registration that

- aligns the orientation of the tensors, not only the FA, and
- is insensitive to the size of the lateral ventricles, which varies widely between subjects and ages.

The order of the steps was set beforehand:

1. an affine registration of the scalar images;
2. a correction of the tensor frame (any rotation, not just flips) against the mean tensor of the age bin;
3. a deformable registration.

Data
----

There were 139 scans of four studies, aged 0-12 years. They had ``dwifit`` tensors, and the multi-shell scans also had
FW-tensor (``FWf``) and NODDI (``NODDI_FWF``) free water maps.

======  =====================  ====================================================================
study   scans (137 compared)   age bin of the normative model
======  =====================  ====================================================================
ABCD    33                     10-60m (school age)
BCP     35                     0-3m (7), 4-9m (13), 10-60m (15)
HBCD    32 (34)                0-3m (newborns, 1.5-2 mm)
VSA     37                     10-60m (IBIS school age, oblique acquisitions)
======  =====================  ====================================================================

Two HBCD scans were excluded from the comparisons:

- One scan was corrupted.
- One scan had a strongly pitched head and tensors inconsistent with it.

The reference was the IBIS normative model (``normativeModel_dtiplayground``, written by
``qc-registration --build-normative``). Each scan was registered to the mean tensor (``DTI_mean.nrrd``) and the mean
free water map (``FWF_mean``) of its age bin.

A 24-scan subset (6 per study) was used for development. All 139 scans were run with the finalists.

Measures
--------

All measures are taken in atlas space.

- **WM angle** (the main measure): the mean angle between the principal directions of the registered tensor and of the
  bin mean tensor, in strong white matter (atlas FA > 0.4, registered FA > 0.15).
- **Periventricular WM angle**: the same angle in the white matter within 5 mm of the ventricles (atlas FA > 0.25),
  where ventricle size differences distort a registration most.
- **Ventricle Dice and volume ratio**: the overlap of the registered free water fraction (> 0.5) with the bin mean
  (> 0.5) near the ventricles (within 8 mm of the atlas deep CSF ROI), and the ratio of the two volumes. 1 is the
  target; DTI-Reg shrinks the ventricles of the subjects that have large ones.
- **Smoothness**: the minimum Jacobian, the number of folds (Jacobian <= 0), and the standard deviation of the log
  Jacobian in the brain.
- **Synthetic ventricle test**: six scans were deformed by a known radial field that enlarges (k = +3, +6) or shrinks
  (k = -3) the ventricles, giving 18 synthetic scans. The test measures the error (mm) of the correspondence of the
  white matter between the synthetic scan and its original. It isolates the influence of ventricle size on the
  registration of the white matter.
- **Tract overlap**: Dice of the atlas bundles mapped into each scan with its tractography labelled by RecoBundles
  (23 scans).

Every method started from the same BRAINSFit affine and the same frame-corrected tensors, so only the deformable step
differed.

Results on 137 scans
--------------------

=====================================  =========  ===========  ======  ========  ==========  ==========  =====
method                                 WM angle   periventr.   frac.   vent.     vent. vol.  sd log      time
                                       (deg)      WM (deg)     > 30°   Dice      ratio       Jacobian    (s)
=====================================  =========  ===========  ======  ========  ==========  ==========  =====
DTI-Reg (ANTs, FA)                     10.48      13.42        0.033   0.70      0.87        0.32        214
DTI-TK 2.3.1                           8.00       11.53        0.018   0.65      0.83        0.26        367
TensorSVF, tensors only (``trsN_ss``)  **7.16**   9.92         0.008   0.69      0.88        **0.19**    81
TensorSVF + FWf, weight 1 (default)    7.20       **9.90**     0.009   0.81      0.95        0.25        80
TensorSVF + FWf, weight 2              7.28       10.20        0.009   **0.83**  **0.97**    0.28        81
=====================================  =========  ===========  ======  ========  ==========  ==========  =====

These are medians over the scans. TensorSVF times are on an RTX A6000 GPU; the CPU fallback takes about 12 min on
4 cores. DTI-Reg times are on 4 CPU threads.

- **WM angle**: TensorSVF beat DTI-Reg in all 137 scans. The tensors-only variant beat DTI-TK in 135 scans and the
  FWf variant in 132.
- **Folding**: no method folded. The minimum Jacobian was 0.08-0.14 for all of them.
- **Ventricles**: the free water term raised the ventricle Dice from 0.69 to 0.81 and the volume ratio from 0.88 to
  0.95, without changing the WM angle.

Per study (medians):

======  =================================  =================================  ==============================
study   WM angle: DTI-Reg / DTI-TK /       periventricular WM angle           ventricle Dice: DTI-Reg /
        TensorSVF / TensorSVF+FWf          (same order)                       DTI-TK / TensorSVF / +FWf
======  =================================  =================================  ==============================
ABCD    11.1 / 7.9 / 7.6 / 7.6             15.1 / 12.0 / 11.2 / 11.1          0.70 / 0.66 / 0.68 / 0.80
BCP     8.5 / 6.2 / 5.9 / 5.8              9.3 / 7.8 / 7.6 / 7.5              0.78 / 0.75 / 0.74 / 0.83
HBCD    12.7 / 9.4 / 8.4 / 8.6             16.1 / 12.3 / 11.1 / 11.2          0.64 / 0.61 / 0.67 / 0.81
VSA     10.4 / 8.3 / 7.1 / 7.1             13.5 / 12.7 / 10.3 / 10.3          0.69 / 0.63 / 0.67 / 0.79
======  =================================  =================================  ==============================

The newborn HBCD scans gained most in ventricle volume: the ratio was 0.72 with DTI-Reg and 0.86 with the FWf term.

Synthetic ventricle test (mean over 18 synthetic scans; error of the white matter correspondence in mm):

=========================  ========  =========  ===================  ===================
method                     WM        WM p95     periventricular WM   periventricular p95
=========================  ========  =========  ===================  ===================
TensorSVF + FWf weight 1   **0.26**  **0.75**   **0.41**             **0.99**
TensorSVF + FWf weight 2   0.26      0.75       0.42                 1.04
TensorSVF tensors only     0.31      0.91       0.49                 1.19
DTI-TK                     0.35      0.91       0.52                 1.26
DTI-Reg                    0.71      2.24       0.78                 2.40
=========================  ========  =========  ===================  ===================

With the FWf term TensorSVF is the least affected by the ventricle size, and DTI-Reg the most.

Alternatives on the 24-scan subset
----------------------------------

These are medians over the subset (23 scans for the tract channel rows).

========================================================  ========  ===========  =====  ==========  ==========  ======
method                                                    WM angle  periventr.   vent.  vent. vol.  sd log      time
                                                                    WM           Dice   ratio       Jacobian    (s)
========================================================  ========  ===========  =====  ==========  ==========  ======
DTI-Reg                                                   11.02     14.23        0.69   0.82        0.32        219
ANTs SyN, FA                                              11.81     15.68        0.70   0.83        0.42        507
ANTs SyN, FA + MD                                         11.64     14.15        0.82   1.06        0.42        929
ANTs SyN, FA + RD + AD                                    11.03     13.77        0.83   1.07        0.42        1321
ANTs SyN, FA + FWf                                        11.34     14.18        0.84   1.00        0.42        945
ANTs SyN, FA + MD + FWf                                   11.07     13.98        0.83   1.03        0.42        1287
ANTs SyN, FA + FWf + DEC colour                           10.31     13.24        0.82   0.97        0.42        2041
DTI-TK                                                    8.27      12.11        0.64   0.78        0.27        370
hybrid: ANTs FA + MD + FWf, then DTI-TK                   8.61      12.74        0.73   0.89        0.44        284
tensor SVF, plain deviatoric term, reg. 0.1               8.65      11.48        0.66   0.87        0.34        80
tensor SVF, plain deviatoric term + FWf 1, reg. 0.1       8.59      11.32        0.79   0.94        0.38        81
tensor SVF, plain deviatoric term + FWf 2, reg. 0.15      8.54      11.26        0.81   0.95        0.35        81
**TensorSVF (normalised deviatoric term), tensors only**  **7.69**  10.71        0.67   0.84        **0.19**    83
**TensorSVF + FWf 1**                                     7.78      **10.67**    0.79   0.92        0.26        83
TensorSVF + FWf 2                                         7.84      10.90        0.83   0.95        0.29        83
TensorSVF + NODDI_FWF 2                                   8.16      11.37        0.80   0.80        0.28        82
TensorSVF + tract channels 0.5                            7.68      10.23        0.67   0.84        0.19        82
TensorSVF + tract channels 2                              7.79      10.46        0.67   0.84        0.20        81
TensorSVF + tract channels 8                              8.77      12.09        0.67   0.83        0.27        82
TensorSVF + FWf 1 + tract channels 0.5                    7.64      10.08        0.79   0.93        0.26        83
========================================================  ========  ===========  =====  ==========  ==========  ======

The conclusions from the subset:

- **Extra scalar channels in ANTs** (MD, RD/AD, FWf) fix the ventricle overlap (Dice 0.82-0.84 against 0.69) but
  barely change the WM angle. Direction-encoded colour channels gain 1 deg at 4-10 times the run time. An FA-based
  registration does not align the tensor orientation.
- **DTI-TK** aligns the orientation well (8.3 deg) but not the ventricles (Dice 0.64), and is the slowest tensor
  method.
- **The hybrid** (ANTs with free water, then DTI-TK) made the two stages work against each other. It was worse than
  DTI-TK in angle and had the roughest field.
- **The normalised deviatoric term** compares unit deviatoric tensors weighted by the anisotropy of the template. It
  removed the sensitivity to the anisotropy difference between a subject and the mean tensor (age, resolution) that the
  plain term had, gaining 0.9 deg over the plain term and 0.6 deg over DTI-TK. It beat DTI-TK in 22 of the 23 subset
  scans and closed the gap DTI-TK had on ABCD.
- **The free water term**:

  - With weight 1 it gives the ventricle overlap with no loss of WM angle.
  - With weight 2 it overlaps the ventricles slightly more, but in scans with small ventricles it inflates them and
    aligns their white matter worse, so the default is 1.
  - The FW-tensor fraction (``FWf``) works slightly better than NODDI's ``NODDI_FWF``, so ``freeWater auto`` prefers
    FWf.

- **Regularization and smoothing**: a sweep of the regularization (0.005-0.2) and smoothing (0.5-1) chose 0.15 and
  0.5. Below 0.1 the deformation can fold.
- **Tract probability channels**: 15 tract groups from RecoBundles labels, with leave-one-out population templates.
  At weight 0.5 they were neutral, at 2 and 8 worse, and slightly worse in the synthetic ventricle test, so they were
  not adopted.
- **Tract overlap** (Dice of the atlas bundles with each scan's labelled tractography) was 0.28-0.30 for every method,
  DTI-Reg included. It does not separate the methods at this resolution, so the angle and ventricle measures decided.

The released module (``method: TensorSVF``) reproduces the prototype: on a VSA scan it gave a WM angle of 7.65 deg
against 7.58 deg for the prototype.

Tensor frame correction
-----------------------

The angles above are only meaningful when the tensor components are in the frame of the image. The scans needed
different corrections:

- ABCD and HBCD tensors needed a z flip.
- VSA and most BCP scans were estimated in the voxel frame of oblique acquisitions, which needs a rotation that no flip
  gives.

``tensorFlip rotation`` (``frame_align.py``) handles both. It fits any rotation of the tensor frame against the bin
mean tensor after the initial affine: the 24 axis permutations and flips, then a continuous refinement. The head
position is removed by the affine, so it is not taken for a frame rotation.

After ``tensorFlip auto`` (flips in the header frame or in the voxel frame), the rotation left was:

======  =====================  ======================  ========  ===========
study   auto choice            median residual (deg)   maximum   scans > 5°
======  =====================  ======================  ========  ===========
ABCD    z                      1.1                     6.3       1
BCP     voxel (20), x (15)     1.1                     6.6       1
HBCD    z                      3.0                     31.5      7
VSA     voxel (35), z (2)      1.2                     11.5      1
======  =====================  ======================  ========  ===========

Only 2 of the 139 scans have a residual that removing it improves (above 5 deg and more than 1 deg lower mean angle):
a VSA scan (11.5 deg) and the excluded HBCD scan with the pitched head (31.5 deg). DTI_Register and ``qc-registration`` warn about
them (v0.9.12).

The frame checks refuse an image that is not aligned with the reference: the correlation of the FA of the image and
of the reference at the same positions must be 0.25 or more. The threshold was calibrated on 24 scans:

- -0.03 to 0.18 unregistered;
- 0.30 to 0.61 after the initial affine;
- 0.45 to 0.85 after the registration.

Defaults
--------

Since v0.9.13 the DTI_Register defaults are the settings of this study:

- ``method: TensorSVF``;
- ``tensorFlip`` empty, which means ``rotation`` (or ``auto`` when ``initialAffine`` is none);
- ``freeWater: auto`` (FWf for multi-shell scans, the tensors only for single shell) with ``freeWaterWeight: 1``;
- ``tensorRegRegularization: 0.15``, ``tensorRegSmoothing: 0.5``, ``tensorRegLevels: 4x2x1``,
  ``tensorRegIterations: 200x150x100``;
- BRAINSFit ``Rigid,Affine`` with ``BRAINSFitSamplingPercentage: 0.5`` (reproducible initial affines).

Give a ``referenceNormativeModel`` and the age of each scan so that it is registered to the mean tensor of its age
bin, as in the study.

The scripts, per-scan scores and run parameters are kept in ``/NIRAL/devel/linux/DTI/test-DWI/RegistrationStudy``
(NIRAL); its README describes the files and the score columns.
