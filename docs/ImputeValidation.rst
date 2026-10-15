Validation of impute-profiles
=============================

This page documents the validation of ``dmrifiberprofile impute-profiles`` (phase 1: every method imputes a scan from
its own observed values only), run on 2026-10-15 with ``--validate`` (see
`Imputing the profiles <DMRIFiberProfile.html#imputing-the-profiles>`_ for the command and its outputs). The results
set the defaults of the command.

Summary
-------

- **Gaps inside a profile** are the only missing values that the scan's own data imputes better than the cohort
  mean at each location: ``arc-linear`` along the profile (0.70 of the cohort mean's error on all scans, no GPU),
  and SIREN with the tract code (``xyz+tract``, omega0 30, 1000 epochs; 0.81 against 0.85 for ``arc-linear`` on the
  same 30 scans). The diffusivities and NDI are imputed well (0.4-0.7); FA, AD, FW-FA, FW-AD, ODI and FWF stay close
  to the cohort mean (0.8-1.2).
- **Missing starts and ends** (the most common partial gaps) are imputed about as well as by the cohort mean (best:
  0.91 on all scans with ``arc-linear`` and constant ends, 1.04 with SIREN ``xyz+arc`` on 30 scans): only MD, RD and
  NDI are clearly better on both samples (0.5-0.8), FWF is worse on both, and the free-water corrected measures
  depend on the sample (better than the cohort mean on all scans, worse on the 30).
- **Whole profiles and regions** (all tracts through a region, as after a regional artifact) are imputed about 2 to
  3 times worse than by the cohort mean by every method (best: SIREN ``xyz`` with 100 epochs, 2.07 and 2.52). The
  values of neighbouring tracts differ systematically, by the tract's orientation and organization, so the scan
  alone can't tell what a missing tract looks like. Only NDI and FW-MD come near the cohort mean.
- The error grows with the distance to the nearest observed location: for ``linear``, from about 1.1 within 2 mm to
  about 3 at 4-6 mm (whole profiles), and tracts far from the others (prefrontal cortico-thalamic, splenium,
  anterior commissure) are the worst.
- **Defaults** (from these results): ``--method arc-linear``, ``--arc-ends none``, ``--fallback none``: only gaps
  inside profiles are filled, up to ``--max-gap`` 15 mm (the longest gaps validated). SIREN defaults are its best setting for gaps (``--siren-inputs xyz+tract --omega0 30
  --epochs 1000``); for whole profiles ``xyz``, omega0 10, 100 epochs did best. ``--k 1``.
- Imputing missing ends, whole profiles and regions needs normative information (deviations from the norm, a
  population model): the next phases of ``impute-profiles``.

Data
----

- A normative reference cohort: 423 scans of 208 subjects, ages 0 to 65 months (median 13, quartiles 8 and 21), the
  cleaned profiles of ``qc-profiles`` (``Profiles_Clean``, the EXTRACT_Profile layout).
- 69 tracts of the DTI_IBISEP_Feb26 atlas and their axes (``compute-axis``), 5388 profile locations (1 mm apart along
  the arc length).
- 11 measures: FA, MD, RD, AD; the free-water corrected FW-FA, FW-MD, FW-RD, FW-AD; the free water fraction FWF;
  NDI and ODI (NODDI).
- 2.45% of the cells are missing, nearly all as whole profiles (7743 scan x tract x measure profiles); 242 profiles
  are partly missing: a missing start (88) or end (132), 1 to 7 positions long (median 3), rarely a gap inside (22).
  Two scans have no free-water measures.
- The axes of the tracts are dense: half of the tracts are within 2.4 mm of another one (median distance of their
  locations to the nearest other tract), and 37% of the locations are within 2 mm of another tract.

Setup
-----

Values that were measured are hidden and imputed, then compared with the hidden values. Per scan and round, two
passes:

- random: whole profiles (all measures) of 10% of the tracts; one gap inside the profile, 3 to 15 mm long, in 20% of
  the other tracts; the start or end of the profile, 1 to 8 mm long, in another 20% (pattern ``end gap``)
- region: every tract with a location within a sphere around a random observed location (radius 10 to 25 mm; a
  median of 13 of the 69 tracts) loses its whole profile

3 rounds per scan; a sample of 30 scans for all methods (SIREN is limited by GPU time) and, for the methods without
SIREN, all 421 eligible scans (marked \* in the tables). All settings see the same hidden values.

**Errors.** The error of each imputed value is divided by the between-scan SD at its location (at least a quarter of
the measure's median SD), the RMS is taken per measure and pattern, and averaged over the measures. The reference
row imputes the cohort mean at each location (of the other scans). Over all scans its error is 1.00 for every
measure; on the 30 scans 0.71 (FW-RD) to 0.99 (FA): those scans happen to lie closer to the cohort mean than the
cohort, especially for the diffusivities. The results are therefore given as ``vs_reference``, the error relative to
that of the cohort mean on the same cells: below 1, a method does better than the cohort mean. On the 30 scans every
method looks about 15% worse by this measure than on all scans, as the cohort mean does unusually well there; SIREN
is compared with the other methods on the same 30 scans.

**Settings compared.**

- ``arc-linear``, its ends left, repeated (``constant``) or extrapolated (``linear``)
- ``linear`` (3-D)
- ``knn``, k 1, 3, 5, 10, 20, 50, each with 1/distance and equal weights
- SIREN per scan: inputs ``xyz``, ``xyz+arc``, ``xyz+tract``; omega0 5, 10, 20, 30; 100, 200, 500 and 1000 epochs; 3
  seeds each (the SD over the seeds is about 0.01-0.03); 3 hidden layers of 256, Adam, learning rate 1e-4. One
  training of 1000 epochs on the 5388 locations and 11 measures takes about 1.2 s on an NVIDIA RTX A6000.
- ``--max-distance`` 10 mm and ``--min-observed`` 0.5 as in an imputation.

Results
-------

Overall
~~~~~~~

``vs_reference``, mean over the 11 measures; 30 scans, and all scans (\*). For SIREN, its best omega0/epochs per
pattern.

.. table::
   :class: longtable

   ============================================  ==============  ==============  =============  =============  =====  =========  ===============  ========
   method                                        gap             end gap         whole profile  region         gap *  end gap *  whole profile *  region *
   ============================================  ==============  ==============  =============  =============  =====  =========  ===============  ========
   arc-linear                                    0.85                                                          0.70
   arc-linear, constant ends                     0.85            1.07                                          0.70   0.91
   arc-linear, linear ends                       0.85            1.10                                          0.70   0.96
   linear                                        1.29            1.14            2.32           3.03           1.09   1.08       1.98             2.54
   knn k=1                                       1.63            1.16            2.96           3.63           1.44   1.01       2.54             3.10
   knn k=3                                       1.70            1.23            2.89           3.58           1.50   1.06       2.46             3.05
   knn k=5                                       1.76            1.27            2.80           3.51           1.55   1.11       2.37             2.98
   knn k=10                                      1.87            1.35            2.60           3.34           1.61   1.24       2.21             2.83
   knn k=20                                      1.99            1.43            2.49           3.19           1.67   1.36       2.12             2.70
   knn k=50                                      2.07            1.54            2.40           3.13           1.73   1.45       2.03             2.63
   SIREN xyz (best ω0/epochs per pattern)        0.99 (10/1000)  1.10 (10/1000)  2.07 (10/100)  2.52 (20/100)
   SIREN xyz+arc (best ω0/epochs per pattern)    0.90 (10/1000)  1.04 (10/1000)  2.33 (10/100)  2.75 (30/100)
   SIREN xyz+tract (best ω0/epochs per pattern)  0.81 (30/1000)  1.06 (30/1000)  2.74 (30/100)  2.92 (30/100)
   ============================================  ==============  ==============  =============  =============  =====  =========  ===============  ========

Per measure
~~~~~~~~~~~

``vs_reference`` per measure; columns without \*: the 30 scans, with \*: all scans. SIREN: the best omega0/epochs
of each input for the pattern (in parentheses).

Gaps inside the profile:

.. table::
   :class: longtable

   ========  ==========  ======  =======  ========  ===================  =======================  =========================  ============  ========  =========  ==========
   measure   arc-linear  linear  knn k=1  knn k=50  SIREN xyz (10/1000)  SIREN xyz+arc (10/1000)  SIREN xyz+tract (30/1000)  arc-linear *  linear *  knn k=1 *  knn k=50 *
   ========  ==========  ======  =======  ========  ===================  =======================  =========================  ============  ========  =========  ==========
   FA        0.93        1.38    1.81     2.11      0.95                 0.97                     0.82                       0.88          1.33      1.71       2.00
   MD        0.73        1.04    1.20     1.54      0.80                 0.69                     0.71                       0.55          0.85      1.08       1.27
   RD        0.71        1.02    1.28     1.48      0.74                 0.71                     0.68                       0.60          0.90      1.17       1.30
   AD        1.03        1.53    1.97     2.43      1.14                 1.06                     0.93                       0.87          1.28      1.74       2.06
   FW-FA     1.03        1.48    1.93     2.34      1.07                 1.04                     0.89                       0.79          1.16      1.52       1.81
   FW-MD     0.61        0.71    0.81     0.94      0.59                 0.57                     0.61                       0.41          0.49      0.62       0.70
   FW-RD     0.71        0.87    1.13     1.35      0.69                 0.69                     0.66                       0.47          0.62      0.81       0.97
   FW-AD     0.94        1.36    1.74     1.83      0.97                 0.95                     0.85                       0.80          1.05      1.42       1.48
   FWF       1.03        2.40    2.86     5.03      2.17                 1.50                     1.23                       0.86          1.98      2.78       4.01
   NDI       0.50        0.56    0.71     0.84      0.47                 0.46                     0.46                       0.44          0.53      0.70       0.83
   ODI       1.18        1.89    2.50     2.91      1.32                 1.23                     1.08                       1.06          1.77      2.32       2.58
   **mean**  0.85        1.29    1.63     2.07      0.99                 0.90                     0.81                       0.70          1.09      1.44       1.73
   ========  ==========  ======  =======  ========  ===================  =======================  =========================  ============  ========  =========  ==========

Missing starts and ends (``end gap``):

.. table::
   :class: longtable

   ========  =========================  =======================  ======  =======  ========  ===================  =======================  =========================  ===========================  =========================  ========  =========  ==========
   measure   arc-linear, constant ends  arc-linear, linear ends  linear  knn k=1  knn k=50  SIREN xyz (10/1000)  SIREN xyz+arc (10/1000)  SIREN xyz+tract (30/1000)  arc-linear, constant ends *  arc-linear, linear ends *  linear *  knn k=1 *  knn k=50 *
   ========  =========================  =======================  ======  =======  ========  ===================  =======================  =========================  ===========================  =========================  ========  =========  ==========
   FA        1.09                       1.02                     1.60    1.56     2.11      1.18                 1.03                     0.98                       1.09                         1.01                       1.60      1.54       2.13
   MD        0.79                       0.73                     0.71    0.80     0.87      0.69                 0.63                     0.73                       0.70                         0.67                       0.63      0.67       0.81
   RD        0.80                       0.77                     0.79    0.85     0.96      0.71                 0.66                     0.67                       0.72                         0.69                       0.69      0.74       0.87
   AD        1.14                       1.05                     1.11    1.19     1.61      1.02                 0.98                     1.08                       0.98                         0.95                       1.06      1.06       1.52
   FW-FA     1.20                       1.05                     1.46    1.43     2.18      1.25                 1.15                     1.15                       1.04                         0.90                       1.32      1.25       1.97
   FW-MD     1.17                       1.28                     1.22    1.21     1.33      1.34                 1.34                     1.27                       0.79                         0.92                       0.93      0.83       0.97
   FW-RD     1.14                       1.33                     1.28    1.26     1.57      1.26                 1.26                     1.21                       0.80                         0.96                       1.03      0.93       1.21
   FW-AD     1.24                       1.24                     1.24    1.27     1.54      1.31                 1.29                     1.22                       1.00                         1.05                       1.06      1.06       1.30
   FWF       1.54                       2.02                     1.24    1.15     2.21      1.72                 1.58                     1.77                       1.31                         1.81                       1.70      1.09       2.71
   NDI       0.57                       0.57                     0.62    0.66     0.91      0.53                 0.50                     0.53                       0.59                         0.61                       0.72      0.70       0.98
   ODI       1.11                       1.07                     1.32    1.36     1.66      1.15                 1.03                     1.01                       1.01                         0.96                       1.17      1.23       1.52
   **mean**  1.07                       1.10                     1.14    1.16     1.54      1.10                 1.04                     1.06                       0.91                         0.96                       1.08      1.01       1.45
   ========  =========================  =======================  ======  =======  ========  ===================  =======================  =========================  ===========================  =========================  ========  =========  ==========

Whole profiles:

.. table::
   :class: longtable

   ========  ======  =======  ========  ==================  ======================  ========================  ========  =========  ==========
   measure   linear  knn k=1  knn k=50  SIREN xyz (10/100)  SIREN xyz+arc (10/100)  SIREN xyz+tract (30/100)  linear *  knn k=1 *  knn k=50 *
   ========  ======  =======  ========  ==================  ======================  ========================  ========  =========  ==========
   FA        2.42    2.86     2.50      2.19                2.54                    3.45                      2.30      2.70       2.38
   MD        1.82    2.55     1.92      1.68                1.78                    2.30                      1.42      1.94       1.43
   RD        1.79    2.42     1.86      1.66                1.87                    2.33                      1.47      1.93       1.49
   AD        2.55    3.40     2.73      2.26                2.49                    2.98                      2.18      2.82       2.27
   FW-FA     2.56    3.03     2.66      2.30                2.71                    3.63                      2.06      2.39       2.14
   FW-MD     1.17    1.32     1.14      1.14                1.34                    1.62                      0.86      1.14       0.88
   FW-RD     1.63    1.86     1.63      1.47                1.77                    2.24                      1.15      1.29       1.15
   FW-AD     2.02    2.46     2.02      1.88                2.26                    2.69                      1.67      2.33       1.76
   FWF       5.04    7.18     5.44      4.30                4.53                    3.70                      4.54      6.53       4.74
   NDI       0.99    1.21     1.05      0.95                1.12                    1.37                      0.96      1.15       1.01
   ODI       3.52    4.23     3.40      2.94                3.23                    3.81                      3.18      3.74       3.06
   **mean**  2.32    2.96     2.40      2.07                2.33                    2.74                      1.98      2.54       2.03
   ========  ======  =======  ========  ==================  ======================  ========================  ========  =========  ==========

Regions:

.. table::
   :class: longtable

   ========  ======  =======  ========  ==================  ======================  ========================  ========  =========  ==========
   measure   linear  knn k=1  knn k=50  SIREN xyz (20/100)  SIREN xyz+arc (30/100)  SIREN xyz+tract (30/100)  linear *  knn k=1 *  knn k=50 *
   ========  ======  =======  ========  ==================  ======================  ========================  ========  =========  ==========
   FA        3.19    3.58     3.24      2.92                2.94                    3.66                      3.07      3.50       3.14
   MD        2.87    3.64     3.04      2.08                2.36                    2.53                      1.99      2.59       2.05
   RD        2.87    3.58     3.09      2.24                2.41                    2.64                      2.12      2.65       2.21
   AD        3.21    3.84     3.20      2.52                2.75                    3.03                      2.68      3.31       2.72
   FW-FA     3.38    3.75     3.42      3.08                3.22                    3.84                      2.71      3.03       2.76
   FW-MD     1.49    1.76     1.54      1.44                1.89                    1.81                      1.09      1.24       1.10
   FW-RD     2.14    2.37     2.16      2.03                2.38                    2.52                      1.51      1.67       1.53
   FW-AD     2.44    2.89     2.45      2.27                2.61                    2.69                      2.08      2.43       2.06
   FWF       5.80    7.59     6.15      3.95                4.36                    3.77                      5.28      7.36       5.89
   NDI       1.36    1.60     1.41      1.26                1.47                    1.55                      1.27      1.52       1.34
   ODI       4.54    5.34     4.70      3.91                3.89                    4.03                      4.13      4.83       4.12
   **mean**  3.03    3.63     3.13      2.52                2.75                    2.92                      2.54      3.10       2.63
   ========  ======  =======  ========  ==================  ======================  ========================  ========  =========  ==========

The measures fall in two groups. The diffusivities (MD, RD and their free-water corrected versions) and NDI vary
smoothly in space and are similar in neighbouring tracts: their gaps and ends are imputed well, and NDI and FW-MD
whole profiles near the cohort mean. The measures that depend on the orientation and organization of the fibers
(FA, AD, FW-FA, FW-AD, ODI) and FWF differ between neighbouring tracts, and their whole profiles and regions are
imputed from them 2 to 6 times worse than by the cohort mean.

SIREN: inputs, omega0 and epochs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: _static/impute_validation/siren_epochs.png
   :width: 100%

``vs_reference`` (mean over the measures, 30 scans) of each input at its best omega0 against the epochs (omega0: 10
for ``xyz`` and ``xyz+arc``, 30 for ``xyz+tract``; 20 for ``xyz`` and 30 for ``xyz+arc`` on regions), with the cohort
mean and the best method without SIREN.

- Gaps and ends need long training (1000 epochs, still improving) and a high omega0 for the tract code; whole
  profiles and regions are best after 100 epochs and get worse with more, as the network fits the observed tracts
  more closely. No setting suits both.
- **Arc length** (``xyz+arc`` against ``xyz``): it helps for gaps (0.90 against 0.99) and ends (1.04 against 1.10),
  and hurts for whole profiles (2.33 against 2.07) and regions (2.75 against 2.52). The 3-D position is enough for the
  whole profiles.
- **Tract code** (``xyz+tract``): best for gaps (0.81), worst for whole profiles (2.74). A tract the scan doesn't
  show (a whole missing profile) leaves its code untrained, so the network can't learn what is specific to it.

All settings, ``vs_reference`` (mean over the measures, 30 scans), per pattern; columns: epochs.

Gaps:

.. table::
   :class: longtable

   =========  ==  ====  ====  ====  ====
   inputs     ω0  100   200   500   1000
   =========  ==  ====  ====  ====  ====
   xyz        5   2.01  1.49  1.12  1.01
   xyz        10  1.43  1.16  1.02  0.99
   xyz        20  1.25  1.07  1.00  1.02
   xyz        30  1.28  1.14  1.10  1.12
   xyz+arc    5   2.10  1.59  1.14  0.99
   xyz+arc    10  1.48  1.15  0.96  0.90
   xyz+arc    20  1.27  1.06  0.96  0.93
   xyz+arc    30  1.26  1.09  1.00  0.99
   xyz+tract  5   1.95  1.61  1.12  0.95
   xyz+tract  10  1.78  1.42  1.06  0.89
   xyz+tract  20  1.68  1.31  1.00  0.88
   xyz+tract  30  1.50  1.14  0.90  0.81
   =========  ==  ====  ====  ====  ====

Ends:

.. table::
   :class: longtable

   =========  ==  ====  ====  ====  ====
   inputs     ω0  100   200   500   1000
   =========  ==  ====  ====  ====  ====
   xyz        5   1.73  1.39  1.19  1.12
   xyz        10  1.42  1.22  1.14  1.10
   xyz        20  1.43  1.26  1.19  1.19
   xyz        30  1.52  1.35  1.30  1.31
   xyz+arc    5   1.96  1.49  1.19  1.10
   xyz+arc    10  1.42  1.20  1.11  1.04
   xyz+arc    20  1.39  1.21  1.11  1.07
   xyz+arc    30  1.48  1.30  1.21  1.19
   xyz+tract  5   2.41  1.88  1.36  1.13
   xyz+tract  10  2.18  1.69  1.25  1.09
   xyz+tract  20  2.03  1.59  1.19  1.08
   xyz+tract  30  1.83  1.34  1.12  1.06
   =========  ==  ====  ====  ====  ====

Whole profiles:

.. table::
   :class: longtable

   =========  ==  ====  ====  ====  ====
   inputs     ω0  100   200   500   1000
   =========  ==  ====  ====  ====  ====
   xyz        5   2.27  2.15  2.24  2.25
   xyz        10  2.07  2.12  2.19  2.24
   xyz        20  2.12  2.24  2.34  2.39
   xyz        30  2.18  2.30  2.39  2.44
   xyz+arc    5   2.40  2.41  2.57  2.62
   xyz+arc    10  2.33  2.45  2.55  2.59
   xyz+arc    20  2.35  2.48  2.59  2.63
   xyz+arc    30  2.45  2.57  2.66  2.72
   xyz+tract  5   2.88  3.03  3.13  3.13
   xyz+tract  10  2.91  3.07  3.00  3.00
   xyz+tract  20  2.87  2.96  2.92  2.93
   xyz+tract  30  2.74  2.90  2.96  2.95
   =========  ==  ====  ====  ====  ====

Regions:

.. table::
   :class: longtable

   =========  ==  ====  ====  ====  ====
   inputs     ω0  100   200   500   1000
   =========  ==  ====  ====  ====  ====
   xyz        5   2.72  2.64  2.71  2.74
   xyz        10  2.52  2.61  2.72  2.77
   xyz        20  2.52  2.67  2.80  2.85
   xyz        30  2.53  2.67  2.80  2.87
   xyz+arc    5   2.85  2.99  3.13  3.17
   xyz+arc    10  2.81  2.99  3.11  3.15
   xyz+arc    20  2.79  2.98  3.14  3.20
   xyz+arc    30  2.75  2.91  3.05  3.12
   xyz+tract  5   2.99  3.15  3.30  3.29
   xyz+tract  10  2.99  3.14  3.08  3.07
   xyz+tract  20  2.97  3.07  3.07  3.06
   xyz+tract  30  2.92  3.05  3.08  3.05
   =========  ==  ====  ====  ====  ====

knn: k and the weights
~~~~~~~~~~~~~~~~~~~~~~

``vs_reference`` (mean over the measures, all scans), with 1/distance and equal weights:

.. table::
   :class: longtable

   ==  ========  ==========  ============  ==============  ==================  ====================  ===========  =============
   k   gap, 1/d  gap, equal  end gap, 1/d  end gap, equal  whole profile, 1/d  whole profile, equal  region, 1/d  region, equal
   ==  ========  ==========  ============  ==============  ==================  ====================  ===========  =============
   1   1.44      1.44        1.01          1.01            2.54                2.54                  3.10         3.10
   3   1.50      1.54        1.06          1.08            2.46                2.46                  3.05         3.05
   5   1.55      1.62        1.11          1.16            2.37                2.36                  2.98         2.98
   10  1.61      1.73        1.24          1.37            2.21                2.21                  2.83         2.82
   20  1.67      1.80        1.36          1.52            2.12                2.14                  2.70         2.70
   50  1.73      1.86        1.45          1.60            2.03                2.07                  2.63         2.64
   ==  ========  ==========  ============  ==============  ==================  ====================  ===========  =============

The weights make little difference (at most about 0.15, for gaps and ends with k 10 or more, where 1/distance is
better; none for whole profiles and regions). A small k is best for gaps and ends (the same tract's neighbouring location, 1 mm away), a large k for
whole profiles and regions. The implementation was checked against a brute force search (identical results).

Distance to the nearest observed location
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``vs_reference`` (mean over the measures, all scans) by the distance from a hidden value to the nearest location
still observed in the scan (same measure):

.. table::
   :class: longtable

   ==========  =============  ======  ======  ======  =======
   method      pattern        0-2 mm  2-4 mm  4-6 mm  6-10 mm
   ==========  =============  ======  ======  ======  =======
   arc-linear  gap            0.61    0.80    0.94    0.78
   linear      gap            0.76    1.36    1.88    1.26
   linear      end gap        0.72    1.27    1.94    2.04
   linear      whole profile  1.11    1.80    3.01    2.47
   linear      region         1.22    1.96    2.95    3.09
   knn k=1     gap            0.89    1.67    3.02    2.16
   knn k=1     end gap        0.73    1.09    1.52    1.64
   knn k=1     whole profile  1.25    2.21    4.08    2.70
   knn k=1     region         1.35    2.17    3.71    3.74
   ==========  =============  ======  ======  ======  =======

Share of the hidden values in each distance bin (beyond ``--max-distance``, 10 mm, nothing is imputed):

.. table::
   :class: longtable

   =============  ======  ======  ======  =======  ========  ========  =========
   pattern        0-2 mm  2-4 mm  4-6 mm  6-10 mm  10-15 mm  15-25 mm  25-inf mm
   =============  ======  ======  ======  =======  ========  ========  =========
   gap            61%     32%     6%      1%       –      –      –
   end gap        56%     30%     11%     4%       0%        0%        –
   whole profile  33%     39%     17%     9%       2%        0%        0%
   region         11%     21%     19%     21%      13%       12%       2%
   =============  ======  ======  ======  =======  ========  ========  =========

Locations
~~~~~~~~~

.. image:: _static/impute_validation/error_map_linear.png
   :width: 80%

The error of ``linear`` per location (mean over the measures, all scans) in three projections, per pattern: the
deep, central white matter, where many tracts meet and cross, is imputed worst, the peripheral tracts best. Per tract, the whole profiles of tracts close to others are
imputed better (median 1.07-1.31 for tracts within 3 mm of another, 2.29 for those 3 to 5 mm away; Spearman 0.31
with the distance). Best: Arc_FrontoParietal_R (0.56), SLF_II_R (0.57), UNC_sup_R (0.58); worst:
CorticoThalamic_PreFrontal_L and _R (5.07, 4.95), AC_temporal (3.36), CorpusCallosum_Splenium (3.31).

Checks
------

- ``knn`` is identical to a brute force nearest neighbour search.
- The arc lengths of the profiles and of the axes agree (median difference 0 at both ends); mapped the other way
  round, the cohort-mean FA of a tract is predicted worse from the neighbouring tracts (median 0.131 against 0.094),
  so the profiles are not reversed on the axes.
- The cohort mean's error over all scans is 1.00 per measure, so the scores are on the intended scale.

Reproducing
-----------

::

    $ dmrifiberprofile impute-profiles --profiles-dir Profiles_Clean --axis-dir FiberAxis --validate \
        --validate-scans 30 --validate-rounds 3 --out-dir Validation30
    $ dmrifiberprofile impute-profiles --profiles-dir Profiles_Clean --axis-dir FiberAxis --validate \
        --validate-scans 1000 --validate-rounds 3 --validate-methods arc-linear,linear,knn --out-dir ValidationAll

The SIREN grid was run as separate processes per input (``--validate-methods siren --validate-siren-inputs xyz``,
...) with the same seed, so that they hide the same values; the results are in ``<out-dir>_report/validation``.
