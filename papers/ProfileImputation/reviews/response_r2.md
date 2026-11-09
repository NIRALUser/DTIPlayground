# Response to the round-2 review

**Manuscript:** "Imputing diffusion profiles of white matter fiber tracts in early brain development: an extensive
evaluation of normative, local, graph and transformer models" (revision 2)

We thank the reviewer for re-computing the key numbers and for the precise diagnosis of the real-mask donor pool. All
three essential requests (R1–R3) were addressed with CPU analyses of the existing result files, and all 12 minor points
were fixed. The round-1 version is archived as `reviews/main_r1.tex` / `main_r1.pdf`.

Numbering below refers to the revised PDF:

- main text: Tables 1–10, Figures 1–9;
- appendix: Section A.1, Tables A1–A23, Figures A1–A5.

The main text now has 10 tables (15 before). The Discussion starts on page 23, and the Discussion and Conclusion end on page 26 (28 before).

New or changed scripts, all run by `scripts/run_all.sh`:

| Script | Purpose |
|---|---|
| `realmask.py`, `realmask_tables.py` | R1: donor recovery and real-mask scoring by donor scope, load and hidden share |
| `e4_downstream.py --mask-groups g1` | R3: the two differential-missingness scenarios |
| `e4_tables.py` | R3: the two new scenarios, the renamed column, and the difference in SD units |
| `descriptives.py` | R1: missingness descriptives of both cohorts in Table 1 |

---

## N1 / R1. Real-mask donors outside the tool's scope; HBCD load

**How we identified the donors.**

- The dumps do not name the donor, so `scripts/realmask.py` replays the draws of `validate()` for every real-mask pass. It
  uses the same random stream (`seed + 3`, one draw per round), the same donor pool and the same scan order.
- It then checks each replayed donor: the donor's missing cells, intersected with the scan's observed cells, must
  equal the hidden cells exactly.
- All 325 E1 passes and all 433 E3 passes replayed exactly, so every donor is known, with no ambiguity.
- Donor load is counted with the rule of `--max-missing-tracts` (`missing_tracts`: tracts with no observed value of any
  measure).

**(a) Restricted re-scoring.** This is the new Table 7. It replaces the old real-mask table, which moved to Appendix
Table A22 because it also has PPCA alone and the pooled BCP runs. Scoring follows the paper: RMSE ratio per measure ×
age bin, then the mean over measures, bins and seeds.

| Setting | E1, all donors | E1, donors ≤ 50% | E3, all donors | E3, donors ≤ 50% |
|---|---|---|---|---|
| PPCA + kNN | 0.758 | 0.752 | 1.083 | 0.973 |
| PPCA + SIREN | 0.777 | 0.771 | 1.086 | 0.975 |
| Transformer alone | 0.757 | 0.754 | 0.767 | 0.743 |
| Fixed blend | 0.723 | 0.718 | 0.816 | 0.786 |
| Released default (shipped table) | 0.713 | 0.708 | 0.799 | 0.768 |
| Table refitted on the cohort (cross-fitted) | 0.712 | 0.707 | 0.764 | 0.737 |

- The all-donor values reproduce the validation results exactly, and the restricted values agree with the reviewer's
  (E3 PPCA + SIREN 0.975, transformer 0.743).
- **Out-of-scope passes.**
  - BCP: 2 of 325 passes (0.6%), holding 10% of the real-mask cells.
  - HBCD: 20 of 433 passes (4.6%), hiding up to 97% of the scan and holding 36% of the cells.
- **Paired per-scan contrasts on in-scope passes** (subject-bootstrap CI):

  | Contrast | E1 | E3 |
  |---|---|---|
  | Released vs PPCA + SIREN | 0.917 [0.906, 0.928] | 0.851 [0.832, 0.869] |
  | PPCA + kNN vs PPCA + SIREN | 0.968 [0.957, 0.980] | 0.991 [0.984, 0.998] |
  | Transformer alone vs released | 1.081 [1.066, 1.099] | 0.993 [0.979, 1.005] |
  | Refitted table vs transformer alone | 0.925 [0.909, 0.938] | 0.983 [0.977, 0.989] |

- **Stratification by donor load.** This is Appendix Table A23, with the reviewer's classes 1, 2–5, 6–15, 16–34 and ≥35
  tracts, and the share of cells in each class.
- **PPCA alone.** It is not in the dumps. The validation's by-scan tables pool the three rounds of a scan, so a per-pass
  restriction is not possible. Table 7's caption says so, and PPCA alone is reported with all donors in Table A22.
- **E5 (pooled runs, no dumps).** The text and captions state that the restricted score is reported for E1 and E3 only.
  The E5 real-mask contrasts compare settings on the same passes, so donor scope does not favour either side of those
  contrasts.

**(b) Load statement and descriptives.**

- "About as much as in BCP" is replaced by the measured load: HBCD passes hide a median of 204 locations (mean 513),
  against 98 (mean 231) in BCP, about twice as much.
- Table 1 has four new rows, computed from the profile tables:

  | Row | BCP | HBCD |
  |---|---|---|
  | Cells missing after QC | 2.3% | 8.8% |
  | Scans with ≥1 rejected tract | 201 (48%) | 2,056 (90%) |
  | Rejected tracts per affected scan, median (mean) | 1 (3.3) | 3 (6.8) |
  | Scans missing >50% of their tracts | 2 | 98 |

- Section 4.7 cites these values.

**(c) Error against the share hidden** (new Fig. 6).

- **Classes:** <5%, 5–10%, 10–25%, 25–50% and >50% of the 5,388 locations.
- **BCP:** errors are flat for all settings (released default 0.68–0.76).
- **HBCD, PPCA + SIREN:**
  - 1.081 below 5%;
  - 0.946, 0.792 and 0.973 for 5–50%;
  - 1.454 above 50%.
- **HBCD, transformer:** 0.66–0.83 throughout, robust to the load.
- **Is the 0.5 default safe?** Section 4.7 now says that the 0.5 default of `--max-missing-tracts` is needed for the
  PPCA-based settings and is sufficient on BCP, because it excludes the region where PPCA fails.
- "No better than (worse than) the age-bin mean" is replaced by the restricted numbers and the dependence on load. On
  HBCD the population model makes a small gain within the tool's scope (0.975), not a failure. It fails only for scans
  with most of their tracts missing, which the tool does not impute.

**Cell-weighting (minor 12).** Section 4.6 now states that the real-mask score is cell-weighted, so donors with many
rejected tracts dominate it, unlike the per-scan paired ratios.

## N2 / R2. HBCD statements consistent with Table 8 (old Table 9) and with R1

Your expectation was correct: "transformer alone best" holds only against the shipped BCP table. The per-scan
real-mask contrast is even equivalent (0.993 [0.979, 1.005]).

**Changes:**

- **Section 4.7.**
  - The blends remain best for the synthetic patterns, including whole profiles: shipped table 0.612, transformer alone
    0.630, fixed blend 0.631.
  - For regions and real masks, the transformer alone matched or beat the blend with the shipped BCP table (real masks
    in scope 0.743 vs 0.768).
  - The HBCD-refitted table matched or beat the transformer alone on every pattern:
    - overall 0.545 vs 0.578;
    - whole profiles 0.607 vs 0.630;
    - regions 0.734 vs 0.740;
    - real masks in scope 0.737 vs 0.743 (per scan 0.983 [0.977, 0.989]).
- **Principal finding 6** carries the qualification you suggested: "beat the blend with the shipped BCP weights for
  regions and real masks, but not for whole profiles, and a weight table refitted on the target cohort matched or beat
  it everywhere". It also notes the small PPCA gain on HBCD real masks within scope (0.975) and the failure only for
  out-of-scope scans.
- **Recommendation 4.** With a large cohort, the transformer alone matched or beat the shipped-weight blend for regions
  and real masks, though not for whole profiles. Refit the weights (`--ensemble-weights fit`), which matched or beat the
  transformer alone for every pattern, or check the blend against the transformer alone in a validation of the target
  cohort.
- **Recommendation 2** has the added sentence: "In a large multi-site cohort (HBCD) the population model gained little
  for spatially clustered missingness (regions 0.970, real masks 0.973 for PPCA + kNN), so a GPU-trained transformer is
  worth its cost there."
- **Abstract.** "With the transformer strongest" is replaced by: "On HBCD the ranking transferred; the transformer alone
  matched or beat the blend with BCP weights for regions and real masks, and blend weights refitted on HBCD matched or
  beat it everywhere."
- **Conclusion.** It now says that blend weights refitted on the second cohort did best.

## N3 / R3. Downstream scope: differential-missingness scenario

We ran the scenario you recommended: `e4_downstream.py --mask-groups g1 --donors missing`, 50 replicates each at
δ = 0.3 and δ = 0.1.

**Design.**

- Every scan of the group carrying the planted effect received a real donor mask, and no scan of the other group did.
- Everything else is as in E4: the same random stream and fold models, and Rubin's rules for MI.
- Complete-case analysis then removes the whole effect group, so it cannot estimate the group effect; Table 10 shows "--".
- The `ols_cluster` group fit is skipped when only one group remains.

**Results** (Table 10, rows "group 1 masked"):

| Imputer | Est./full, δ=0.3 | Est.−full (SD), δ=0.3 | Est./full, δ=0.1 | Type I | Power δ=0.3 |
|---|---|---|---|---|---|
| Available case | 1.000 | −0.000 | 1.025 | 5.5% | 98% |
| Age-bin mean | 0.959 | −0.012 | 0.997 | 5.6% | 98% |
| PPCA | 0.956 | −0.013 | 0.975 | 5.5% | 98% |
| PPCA + kNN | 0.957 | −0.012 | 0.987 | 5.6% | 98% |
| Blend (table) | 0.956 | −0.012 | 0.980 | 5.7% | 98% |
| MI (PPCA) | 0.956 | −0.013 | 0.973 | 5.5% | 98% |

**Interpretation, now in Section 4.10.**

- Every imputer attenuated the effect by about the share of imputed values in the effect group, about 4%. That share is
  twice the cohort-wide 2.2%, because only that group was masked.
- The SE and power were unchanged, and type I error was not inflated.
- The effect was planted in whole tracts, so the imputed values carry no information about it, and no imputer recovers
  it: PPCA and the blend attenuate it as much as the age-bin mean.
- Imputation toward the norm therefore shrinks a group difference in proportion to the imputed share of the affected
  group. At these cohorts' missingness the shrinkage is a few percent; it grows with that share.

**Changes to the claims.**

- **Abstract (v).** It now reads "At realistic missingness unrelated to group, imputation kept all scans with
  negligible bias …; with missingness concentrated in one group, imputation shrank its group difference by about its
  imputed share (estimate 0.956 of the complete-data estimate)."
- **Principal finding 7** is restricted to masks independent of group and values, and adds the differential result.
- **Recommendation 6** now says to report the share of imputed values per group. When one group has more rejected
  tracts, imputation shrinks the group difference by about that group's imputed share, so group results should be
  compared with tract-wise available-case analysis.
- **The round-0 caveat is restored:** "do not rely on imputed values for group differences between normative and
  clinical scans, whose deviations the norm of a typically developing cohort does not represent."
- **Conclusion:** "with missingness concentrated in one group it shrinks that group's difference by about its imputed
  share."

## New minor issues

1. **E4 terminology.**
   - The column is renamed "Deviation (SD)" (mean absolute difference from the complete-data curve). The text states
     that under random masks the complete-case value (0.047 SD) is the sampling deviation of a fit on half the scans,
     not bias.
   - A column "Est. − full (SD)" gives the mean difference from the complete-data estimate in between-scan SD units.
   - The text notes that the complete-case ratio of 1.177 at δ = 0.1 is a ratio of small, noisy numbers; its
     difference is +0.001 SD.
   - Fig. A3 now shows the difference instead of the ratio.
2. **QC truncation.** A new limitation, next to the missing-not-at-random point, says that the profile QC removed tracts
   deviating by more than 3.5 SD from a prior built on the full BCP cohort. Only values that passed this filter can be
   hidden, so the errors are likely optimistic for atypical scans (clinical cohorts, residual artefacts).
3. **"About 300 scans or more"** is removed from recommendation 2, which now states the curve without a threshold:
   1.187 at about 99 scans, 1.073 at about 198 and 1.022 at about 295, relative to about 395, with norm and PPCA refitted
   on each subset.
4. **"Or in addition, within 2 mm"** is marked as untested: "a combination of kNN for whole tracts and SIREN within 2 mm
   for gaps is plausible but was not evaluated".
5. **Recommendation 5** now cites E5(i): "neither helped nor hurt overall, 0.999, and helped slightly in the thin 0–3
   month bin, 0.977 [0.955, 0.999]; E5, Table 9".
6. **E5 interpretation.** Your hypothesis is added and labelled untested: HBCD is multi-site and multi-vendor and makes
   up 84% of the pooled scans (2,293 of 2,716), so its between-site variance probably dominates the leading PPCA
   components. This would also explain the weak HBCD PPCA for regions in E3 (0.978).
7. **Abstract.** "Six method families" is now seven (A–G). The E3 statement is corrected as described under N2.
8. **Table 3 caption.** "As in the software documentation" is dropped.
9. **Processing versions.**
   - Model fitting: version 0.5.10, as recorded in the processing scripts.
   - Registration, profile extraction and QC: the scripts ran in a rolling "latest" environment, and we could not
     recover the exact version from the outputs. This is marked `\todo{exact version(s)}` for the authors.
10. **Length.**
    - Moved to the appendix:
      - Table 6 (screens), now Table A17;
      - Table 12 (per measure, which Fig. 7 shows), now Table A18;
      - Table 13 (absolute RMSE), now Table A19;
      - Table 15 and Fig. 9 (paired contrasts), now Table A20 and Fig. A5;
      - Table 10 (pooling per bin), now Table A21;
      - the old real-mask table, now Table A22.
    - The acquisition, eligibility, ethics and preprocessing details of both cohorts, and processing steps (i)–(iv)
      (model fitting, registration, registration QC, profile extraction), moved to Appendix A.1. The Data section keeps
      a one-paragraph summary, the profile QC that defines the missingness, the age scales and the missingness
      descriptives.
    - Result: 10 tables in the main text, and the Discussion and Conclusion end on page 26 instead of 28. The new
      Fig. 6 (real-mask error against hidden share) replaces the paired-contrast figure in the main text, so there are
      still 9 main figures. The PDF grew from 40 to 43 pages, all of it in the appendix.
11. **Figures.**
    - Fig. 8 (formerly Fig. 7, error by age):
      - tick labels are rotated, so "0-1 (11)" and the like no longer overlap;
      - the x-axis titles are shortened and no longer run into each other;
      - the legend moved above the panels;
      - panel (c) has headroom for its legend.
    - Fig. 2b: the "r = 14 mm" label moved into the legend ("Region (13 tracts) in a sphere, r = 14 mm"), and the panel
      titles have padding so they no longer touch the orientation labels.
    - Fig. 4: the gap between panels is wider, so the y-axis label of (c) no longer crowds (b).
    - The `\pending{}` fallback for Fig. A3 is removed from main.tex.
12. **Section 4.6** states that the real-mask score is cell-weighted (see N1).

## Optional

- **O-a (PPCA on HBCD per site or vendor, q = 80 vs 160):** not run in this round. The load analysis (Fig. 6,
  Table A23) and the hypothesis in minor point 6 cover part of the question.
- **O-b (seeds 1–2 for the context-input and seed-ensemble checks):** not run. As you note, it is not needed given the
  ±2% equivalence on seed 0.

## Author placeholders still open

- the release number with `--validate-exclude-subjects`, `--validate-real-masks`, `--validate-norm-batches` and
  `--validate-model-batches`;
- the Docker image and the Zenodo DOI;
- where the processing scripts, the paper scripts and the result files will be shared;
- the NDA collection ID and the HBCD DUA, if required;
- whether derived profiles can be shared;
- the exact DTIPlayground versions for registration, extraction and QC (new, minor point 9);
- CRediT and competing interests.
