# Review, round 3

**Manuscript:** "Imputing diffusion profiles of white matter fiber tracts in early brain development: an extensive
evaluation of normative, local, graph and transformer models" (revision 2)
**Recommendation:** Accept after trivial edits and the author-provided placeholders

---

## Summary

The authors addressed all three essential round-2 requests with CPU analyses of the existing result files:

- **Real masks.** The real-mask pass is re-scored with donors restricted to the tool's scope. The donor of every pass
  is recovered by an exact replay of the validation's random draws.
- **Consistency.** The HBCD statements are made consistent with Table 8.
- **Downstream.** A differential-missingness scenario is added to E4, and the downstream claims are qualified.

The twelve minor points are fixed, and the main text was shortened to 10 tables. I checked the new numbers
independently and looked for problems introduced by the revision.

## Assessment of the round-2 points

### Essential requests

**R1 / N1, real-mask donors and HBCD load: resolved.**

`scripts/realmask.py` replays the donor draw of every pass and accepts it only if the donor's missing cells reproduce
the hidden cells exactly. All 325 E1 and 433 E3 passes replayed with a unique match (cache `realmask_*_passes.csv`:
`how = replayed`, `n_match = 1` for every pass). From the cached per-pass sums I recomputed the paper's cell-weighted
scores and the in-scope paired contrasts. They match the manuscript exactly.

| Quantity | Cohort | Value |
|---|---|---|
| Real-mask score, PPCA + SIREN, all donors / in scope | E1 | 0.777 / 0.771 |
| Real-mask score, transformer, all donors / in scope | E1 | 0.757 / 0.754 |
| Real-mask score, released default, all donors / in scope | E1 | 0.713 / 0.708 |
| Real-mask score, PPCA + SIREN, all donors / in scope | E3 | 1.086 / 0.975 |
| Real-mask score, transformer, all donors / in scope | E3 | 0.767 / 0.743 |
| Real-mask score, released default, all donors / in scope | E3 | 0.799 / 0.768 |
| Released vs PPCA + SIREN, in scope, per scan | E1 | 0.917 [0.906–0.928] |
| Released vs PPCA + SIREN, in scope, per scan | E3 | 0.851 [0.832–0.869] |
| PPCA + kNN vs PPCA + SIREN, in scope, per scan | E1 | 0.968 |
| PPCA + kNN vs PPCA + SIREN, in scope, per scan | E3 | 0.991 |
| Transformer vs released, in scope, per scan | E1 | 1.081 |
| Transformer vs released, in scope, per scan | E3 | 0.993 [0.979–1.005] |
| Refitted table vs transformer, in scope, per scan | E1 | 0.925 |
| Refitted table vs transformer, in scope, per scan | E3 | 0.983 [0.977–0.989] |

The E3 restricted values agree with my round-2 estimate. That estimate excluded passes by the share of locations
hidden rather than by donor tracts; the two definitions give the same numbers here.

The other parts of R1 are also done:

- The load statement is corrected: median 204 vs 98 locations hidden.
- Table 1 now has the missingness descriptives of both cohorts.
- Fig. 6 and Table A23 give the load dependence.
- The cell weighting of the real-mask score is stated.

**R2 / N2, HBCD statements: resolved.**

- Section 4.7, principal finding 6, recommendation 4, the abstract and the conclusion now say the following, which
  Table 8 and the dump results support:
  - the blends are best for the synthetic patterns, including whole profiles: shipped table 0.612 against 0.630 for
    the transformer alone;
  - the transformer alone matches or beats the shipped-BCP-weight blend only for regions and real masks;
  - a table refitted on HBCD matches or beats the transformer alone everywhere.
- From `dump_e3_results.csv` I checked the refitted table against the transformer alone:

  | Pattern | Refitted table | Transformer alone |
  |---|---|---|
  | Overall | 0.545 | 0.578 |
  | Whole profiles | 0.607 | 0.630 |
  | Regions | 0.734 | 0.740 |
  | Real masks | 0.764 | 0.767 |
  | Tensor family | 0.341 | 0.341 |
  | NODDI family | 0.516 | 0.516 |

  So "matched or beat everywhere" holds.
- Recommendation 2 now states the limited gain of the population model on HBCD.

**R3 / N3, downstream scope: resolved.** The differential scenario was run as specified: all scans of the effect
group masked with real donor masks, none in the other group, δ = 0.3 and 0.1, 50 replicates.

- The result is credible and well interpreted. Every imputer attenuates the effect by about the imputed share of the
  effect group: 0.956–0.959 at δ = 0.3, a difference of −0.012 SD. Power and type I error are unchanged.
- The authors correctly note that PPCA and the blend cannot recover an effect planted in whole tracts. This scenario
  is therefore close to a worst case for model-based imputers, and diffuse real effects would be partly recovered.
- The claims now match the evidence: abstract (v), principal finding 7, recommendation 6 and the conclusion. The
  normative-vs-clinical caveat is restored, with the advice to report imputed shares per group and to compare with
  available-case analysis.

### New minor issues of round 2

All twelve are resolved:

- the "deviation" column and the difference in SD units in E4;
- the QC-truncation limitation;
- recommendation 2 without a threshold;
- the untested SIREN + kNN combination flagged;
- E5(i) cited in recommendation 5;
- the multi-site hypothesis, labelled untested;
- "seven families" in the abstract;
- the Table 3 caption;
- the exact processing versions, now an author placeholder;
- the main text shortened to 10 tables, with the processing details in Appendix A.1;
- the figure fixes (Fig. 8 tick labels and titles, Fig. 2b label, Fig. 4 spacing, the `\pending` figure fallback
  removed);
- the cell-weighting statement.

The `\pending` macro definition is still in the preamble but is no longer used.

## New issues introduced by the revision

**1. One statement contradicts Fig. 6b and Table A23 (trivial edit).**
Principal finding 6 says the population model on HBCD "failed only for scans with most of their tracts missing". But
Fig. 6b and Table A23 show PPCA + SIREN and PPCA + kNN also above the age-bin mean for the smallest masks:

- 1.08 when less than 5% of the scan is hidden, which is 247 of 433 passes, the most common HBCD situation;
- 1.20 for single-tract donors.

Section 4.7 reports the 1.081 correctly. My check from the cached per-pass sums shows that this is a cell-weighted
tail effect rather than a typical failure. On passes hiding less than 5%, per scan:

| Setting vs age-bin mean | Ratio | Better on |
|---|---|---|
| PPCA + SIREN | 0.901 [0.845–0.966] | 63% of scans |
| Transformer | 0.748 | 90% of scans |
| Released default | 0.760 | 82% of scans |

Across all in-scope passes, PPCA + SIREN is 0.861 [0.820–0.902], better on 76% of scans.

Please replace "failed only for scans with most of their tracts missing" with a sentence that matches Fig. 6b. For
example: "...gained little on HBCD's real masks (0.975 within scope, cell-weighted; per scan about 0.86–0.90, better
than the norm in only about two thirds of scans), and was worse than the norm when most of a scan was hidden". Adding
the per-scan figure to Section 4.7 would help readers interpret the >1 cell-weighted points. This one-sentence fix
strengthens recommendation 2: for a large multi-site cohort, prefer the transformer.

**2. Wording in Section 4.7 (trivial).**
"Between these it reached 0.946, 0.792 and 0.973" reads as if the population model had a U-shaped dependence on load.
Given the heavy tails, a short qualifier would avoid over-reading the shape: the classes have 86, 64 and 16 passes,
the cell-weighted score is driven by a minority of scans, and the per-scan ratios are smaller.

No other inconsistencies found. The abstract (363 words incl. LaTeX) still reads densely but is accurate.

## Remaining author placeholders (not scientific issues)

- the release number containing the new `--validate-*` options;
- the Docker image and Zenodo DOI;
- the locations of the processing scripts, the paper scripts and the result files;
- the NDA collection ID and the HBCD DUA, if required;
- whether derived profiles can be shared;
- the exact DTIPlayground versions for registration, extraction and QC;
- CRediT and competing interests.

## Recommendation

**Accept after trivial edits** (new issues 1 and 2, one or two sentences each) and completion of the author-provided
placeholders.

Over three rounds the paper has become a rigorous and practically useful evaluation:

- the main gains are confirmed on untouched subjects and on a second cohort;
- the recommendations follow the real missingness;
- the pooling result is properly decomposed;
- the downstream consequences, including differential missingness, are quantified;
- every number I checked reproduces from the result files.

SATISFIED: yes
