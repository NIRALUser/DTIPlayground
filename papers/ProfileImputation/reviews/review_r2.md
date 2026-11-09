# Review, round 2

**Manuscript:** "Imputing diffusion profiles of white matter fiber tracts in early brain development: an extensive
evaluation of normative, local, graph and transformer models" (revision 1)
**Recommendation:** Minor revision

---

## Summary of the revision

The authors have done a thorough job. Every essential request of round 1 was run:

- E1, an untouched test set;
- E2, real-mask hiding;
- E3, HBCD as a second cohort;
- E4, a downstream analysis with multiple imputation;
- E5, a pooling decomposition;
- E6, a kernel-norm reference;
- E7, calibration of the released default;
- E8, generic cohort imputers.

The authors also ran most of the optional items (O1, O3 and O5–O7). The paper is reorganised by method family, and
the recommendations are now pattern-specific.

I re-computed the key new numbers from the raw v16 result files and they reproduce exactly:

| Quantity | Value | Pairs / subjects |
|---|---|---|
| E1, released default vs PPCA + SIREN, four patterns | 0.925 [0.919–0.931] | 111 pairs, 63 subjects |
| E1, released default vs PPCA + SIREN, real masks | 0.916 [0.905–0.927] | |
| E1, PPCA + kNN vs PPCA + SIREN, whole profiles | 0.965 | |
| E3, released default vs PPCA + SIREN, four patterns | 0.872 [0.862–0.881] | 180 pairs, 159 subjects |
| E3, released default vs PPCA + SIREN, real masks | 0.828 [0.808–0.848] | |
| E3, real-mask score of PPCA + SIREN | 1.086 | |
| E3, real-mask score of transformer alone | 0.767 | |

The E1 subjects do not overlap the 96 subjects validated in seeds 0–2.

The central conclusions now rest on a held-out evaluation and a second cohort, and on the missingness that actually
occurs. This is a substantially stronger paper.

The remaining issues are of a different kind:

- the HBCD real-mask results are driven partly by masks outside the tool's own scope;
- a few HBCD statements contradict the paper's own tables;
- the downstream conclusion is stated more generally than E4 supports.

All can be fixed with CPU re-scoring of existing dumps and text changes.

## Assessment of the round-1 points

### Major issues

| # | Issue | Status | Comment |
|---|---|---|---|
| M1 | No held-out test | **Resolved** | E1 on untouched subjects (4–60 months; the 0–3 month bin exhausted, stated) and E3 on HBCD. The refitted vs shipped table check (0.633 vs 0.633) is a good addition. "Pre-specified" corrected. |
| M2 | Score not aligned with real missingness | **Resolved** | Real-weighted score, pattern-specific contrasts (Table 5), the real-mask pass, the 2- vs 4-mm limit re-scored under the current protocol (Table A3), pattern-specific recommendations. One problem with the real-mask donor pool, see N1. |
| M3 | Weak reference | **Resolved** | Kernel-norm reference in Table 4 and for E1; absolute RMSEs for all main rows; age definitions stated (BCP nominal chronological months, HBCD term-corrected). |
| M4 | Pooling oversimplified | **Resolved** | Per-bin contrasts, the fully pooled blend reported, equal-epoch comparison, E5 decomposition (the PPCA, not the norm, carries the loss), batch-correction residual check (Table A12), O1 learning curve replacing the untested "more data" claim. The description of the reference transformer is now accurate. |
| M5 | No downstream evaluation | **Partly** | E4 is well designed and informative. The masks are assigned independently of group and value, but the conclusion is stated generally, and the earlier caveat about normative-vs-clinical comparisons was removed (N3). |
| M6 | Missing baselines; unequal budgets | **Resolved** | E8 (iterative SVD ≈ PPCA; kNN across scans and MICE 13–15% worse; scan offset ≈ 40% of PPCA's gain). Budget table. O5 shows the transformer's advantage over the U-Net is not a budget artefact. |
| M7 | Reproducibility | **Partly** | The supplementary tables now back the former "software documentation" claims, and the phase chronology moved to Table A1. Remaining before acceptance: the release number containing the new `--validate-*` options, a DOI, and the release of the result files and scripts. |
| M8 | Calibration of the released default | **Resolved** | Tables A5–A6 with per-band rescaling factors; the blend SD is defined. |

### Minor issues

Items 1–8, 10–20 and 22 are resolved.

- **Item 9 (Fig. 5c without PPCA alone):** acceptable as explained, since Fig. 5 shows it on a common footing.
- **Item 21 (archival references):** pending, author placeholders.
- **Item 22 (related work):** TractSeg-based tractometry was not added. That is acceptable.

### Essential requests

| # | Request | Status |
|---|---|---|
| E1 | Untouched test | Resolved |
| E2 | Realistic masks | Partly (see N1) |
| E3 | HBCD as a test cohort | Resolved as an experiment; the interpretation needs correction (N1, N2) |
| E4 | Downstream analysis | Partly (N3) |
| E5 | Pooling decomposition | Resolved |
| E6 | Kernel-norm reference | Resolved |
| E7 | Calibration | Resolved |
| E8 | Generic imputers | Resolved |

## New major issues

**N1. The real-mask pass includes masks that the tool itself would not impute, and they drive the HBCD real-mask
conclusions. The paper also misstates the HBCD hidden load.**

*How donors are drawn.* In `validate()`, the donor of a real mask is any scan with missing values of the same age bin
and another subject, including donors that miss more than half of their tracts. `impute-profiles` itself leaves such
scans unimputed (`--max-missing-tracts 0.5`). HBCD has heavier and more clustered missingness than BCP. From
`v15/data/HBCD/Profiles_Clean`:

- 8.8% of cells are missing (BCP 2.3%);
- 2,056 of 2,293 scans have rejected tracts;
- the median is 3 rejected tracts per affected scan and the mean 6.8 (BCP: median 1, mean 3.3).

*The hidden load is not "about as much as in BCP".* From the dumps, a real-mask pass hides:

| Cohort | Median hidden locations | Mean hidden locations |
|---|---|---|
| HBCD | ~200 | 420–600 |
| BCP (E1) | ~98 | 180–300 |

So the statement in Section 4.7 that "the real masks hid about as much as in BCP" (and "about 4 tracts" in the
response) is not correct.

*Extreme passes.* In E3, 4–10 passes per seed hide more than half of the 5,388 locations, up to 97%. They hold 25–49%
of all real-mask cells. In those passes, PPCA + SIREN is 2–3 times worse than the age-bin mean, for example 81,432 vs
27,124 standardized SSE in one seed-1 pass.

*Effect on the scores.* I re-scored the real-mask pattern from the dumps with the paper's scoring (RMSE ratio per
measure × age bin, mean over cells, then over seeds), leaving out passes that hide more than half of the locations:

| Setting | E3, all passes | E3, ≤ half hidden | E1, all passes | E1, ≤ half hidden |
|---|---|---|---|---|
| PPCA + SIREN | 1.086 | 0.975 | 0.777 | 0.771 |
| Transformer alone | 0.767 | 0.743 | (unchanged) | (unchanged) |

The qualitative HBCD conclusion survives: PPCA-based methods gain little on HBCD's real masks, and the transformer
gains much. But "no better than (worse than) the age-bin mean" is an artefact of out-of-scope masks.

*The underlying failure mode matters to practitioners.* PPCA (and PPCA + SIREN) becomes worse than the norm when
most of a scan is hidden. The transformer does not. The ratio of PPCA + SIREN to the age-bin mean also varies widely by
seed and bin on HBCD real masks (PPCA alone 0.81–1.48 per bin), which indicates heavy tails.

Please:

- (a) restrict real-mask donors to masks the tool would impute, i.e. at most `--max-missing-tracts` of the tracts
  missing. Alternatively, report the real-mask results stratified by donor load (e.g. 1, 2–5, 6–15, 16–34, ≥35
  tracts). This is a CPU re-scoring of the existing dumps for the base, transformer and table blends. PPCA alone needs
  either the by-scan tables or a note.
- (b) correct the load statement, and add the HBCD missingness descriptives (cells missing, rejected tracts per scan)
  to Table 1 or Fig. 1.
- (c) report, from the same dumps, the error of PPCA + SIREN, the transformer and the released default against the
  share of the scan hidden. State whether the 0.5 default of `--max-missing-tracts` is safe for the PPCA-based
  settings.

**N2. Several HBCD statements contradict the paper's own tables.**

- *Whole profiles.* Section 4.7 says that "for whole-tract missingness the transformer alone was the best setting".
  Recommendation 4 says that with a large cohort "the transformer alone was the best setting for whole-tract and
  real missingness". But Table 9 gives whole profiles 0.630 for the transformer alone against 0.612 for the shipped
  table blend and 0.631 for the fixed blend. For whole profiles the blend is better.
- *Real masks.* The same paragraph says the transformer alone was "better than every blend on the real masks". Yet
  the HBCD-refitted table blend reaches 0.764 against 0.767 for the transformer alone. The paragraph itself then says
  the refitted table "matches the transformer alone where it is best".
- *Principal finding 6* ("the transformer alone became the best setting for regions and real masks") needs the same
  qualification: "best against the shipped BCP table; matched by a table refitted on the target cohort".

Please make Section 4.7, principal finding 6, recommendation 4, the abstract ("with the transformer strongest") and
the conclusion consistent with Table 9. After N1(a), re-check whether "transformer alone best for real masks" still
holds. I expect it to hold only against the shipped table.

Recommendation 2 presents PPCA + kNN as "a strong CPU-only baseline". On HBCD it gains little for regions (PPCA + kNN
0.970) and real masks (1.083; about 0.97 after N1(a)). Add one sentence: in a large multi-site cohort the population
model gained little for spatially clustered missingness, so a GPU-trained transformer is worth the cost there.

**N3. The downstream conclusion is stated more generally than E4 supports.**
E4 assigns donor masks independently of group membership and of the values (MCAR at the scan level), at low
prevalence, in a normative cohort. Under these conditions, imputation toward the norm can only slightly attenuate a
group difference, and E4 confirms this (about 2%). The setting in which practitioners most need guidance is
differential missingness: a clinical or high-motion group with more rejected tracts. There, imputation toward the norm
biases the group contrast towards zero. Yet:

- the abstract states (v) "imputation kept all scans with negligible bias in trajectory and group analyses";
- recommendation 6 says point imputation "preserved trajectory and group analyses";
- the round-0 caveat "do not rely on imputed values for group differences between normative and clinical scans" was
  removed.

Either:

- (a) restrict these statements explicitly to missingness independent of group and of the values, and restore the
  caveat; or, preferably,
- (b) add one E4 scenario with differential missingness. It runs on the CPU with the existing `e4_downstream.py`, 50
  replicates. Use δ = 0.3 and 0.1 planted in group 1, and real donor masks assigned only to group-1 scans (all
  group-1 scans masked, no group-0 scan masked; or prevalence 80% vs 20%). Report estimate/full, SE ratio and
  power for the age-bin mean, PPCA, PPCA + kNN, the blend, MI and available case.

If attenuation stays within a few percent for PPCA and the blend, the general statement can stand, with the age-bin
mean flagged. If not, recommendation 6 must warn against imputation for group comparisons with unequal missingness.

## New minor issues

1. **E4 terminology.**
   - With masks assigned at random, complete-case analysis is unbiased. Its larger "bias" (0.047 SD) is the extra
     sampling deviation from the complete-data fit with 114 instead of 220 scans. Rename the column, e.g. "deviation
     from the complete-data curve", and say so in the text.
   - The complete-case estimate/full of 1.177 at δ = 0.1 is a ratio of noisy small numbers. Report the mean
     difference (estimate − full) in SD units instead, or as well.
2. **QC truncates the hidden values.** The profile QC removed tracts deviating more than 3.5 SD from a prior built
   on the full BCP cohort, so the validation hides only values that passed this outlier filter. Errors are therefore
   likely optimistic for atypical scans, such as clinical cohorts or residual artefacts. Add this to the Limitations
   next to the MNAR point.
3. **Recommendation 2: "about 300 scans or more".** O1 shows a monotone curve without a threshold (+19% at ~100
   scans, +7% at ~200, +2% at ~300), with the norm refitted on the same subsets. State the curve, not a threshold.
4. **Recommendation 3: "or in addition, within 2 mm".** PPCA + kNN with SIREN additionally within 2 mm was not
   evaluated. Remove it or mark it as untested.
5. **Recommendation 5.** "Helped slightly in the thin 0–3 month bin" should cite E5(i): 0.977 [0.955–0.999].
6. **E5 interpretation.** HBCD is multi-site and multi-vendor, so with 85% of the pooled scans its between-site
   variance probably dominates the leading PPCA components. This is a more specific candidate explanation than "a
   covariance that fits the BCP scans worse", and it also fits HBCD's weak PPCA for regions in E3 (0.98). Mention it
   as a hypothesis.
7. **Abstract.** It says "six method families", whereas Table 2 has seven (A–G). It also states E3 as "the ranking
   transferred, with the transformer strongest"; see N2.
8. **Table 3 caption.** It still refers to "the software documentation" for the pooled-over-seeds values. Drop that
   phrase.
9. **Processing paragraph.** "DTIPlayground (versions 0.5.10 and later)": give the exact versions used for model
   fitting, registration, extraction and QC.
10. **Length.**
    - The main text has 15 tables and 9 figures, and the Data section has grown to about two pages of processing
      detail.
    - Consider moving to the supplement the QC and processing details beyond what defines the missingness, Table 6
      (screen), Table 12 (per measure; Fig. 6 shows the same) and Table 15 / Fig. 9 (four-pattern contrasts largely
      superseded by Table 5 and E1).
    - The paper is clear, but 40 pages will deter some readers.
11. **Figures.**
    - Fig. 7a,b: the x tick labels overlap ("7-910-14", "24-3536-69"), and the two x-axis titles run into each
      other.
    - Fig. 2b: the "r = 14 mm" label overlaps the tracts.
    - Fig. 4c: the y-axis label crowds panel (b).
    - The `\pending{}` fallback for Fig. A3 in main.tex should be removed before submission.
12. **Section 4.6.** Say that the real-mask score is cell-weighted, so donors with many rejected tracts dominate it,
    unlike the per-scan paired ratios. This also helps the reader with N1.

## Remaining requests

### Essential (all CPU; existing dumps and scripts)

- **R1 (N1).** Re-score the real-mask pattern of E1 and E3 with donors restricted to at most 50% of tracts missing,
  or stratified by donor load. Report Table 8, the paired real-mask contrasts, and the error against the share of the
  scan hidden for PPCA + SIREN, the transformer and the released default. Correct the load statement and add the
  HBCD missingness descriptives.
- **R2 (N2).** Make every HBCD statement consistent with Table 9 and with R1: Section 4.7, principal finding 6,
  recommendations 2 and 4, the abstract and the conclusion.
- **R3 (N3).** Either qualify the downstream conclusions (abstract (v), principal finding 7, recommendation 6) to
  group- and value-independent missingness and restore the caveat about normative-vs-clinical comparisons, or run the
  differential-missingness E4 scenario specified above. I recommend running it: it is cheap and directly tests the
  paper's most practical claim.

### Optional

- **O-a.** A short diagnostic of why PPCA is weak for regions and real masks on HBCD despite six times the data:
  per age bin and per scanner vendor or site, and q = 80 vs 160. CPU-feasible for PPCA alone.
- **O-b.** Seeds 1–2 for the context-input and seed-ensemble checks (R4 of round 1). Not needed for the conclusions,
  given the ±2% equivalence on seed 0.

## Author placeholders still required before acceptance

- the release number containing `--validate-exclude-subjects`, `--validate-real-masks`, `--validate-norm-batches`
  and `--validate-model-batches`;
- the Docker image and the Zenodo DOI;
- the location of the processing scripts and of the paper scripts and result files;
- the NDA collection ID and the HBCD DUA, if required;
- whether derived profiles can be shared;
- CRediT and competing interests.

## Recommendation

**Minor revision.** The revision answers the substance of round 1 convincingly:

- the gains reproduce on untouched subjects (0.925 vs 0.923) and transfer to a second cohort;
- the recommendations now follow the real missingness;
- the pooling story is properly decomposed;
- the downstream analysis shows that, at BCP-like missingness, imputation clearly beats complete-case analysis.

What remains:

- the real-mask pass includes masks the tool would not impute, which exaggerates the HBCD population-model failure;
- a few HBCD statements contradict Table 9;
- the downstream claim needs either qualification or one more CPU scenario.

None of this requires new GPU runs. I expect to recommend acceptance once R1–R3 and the placeholders are addressed.

SATISFIED: no
