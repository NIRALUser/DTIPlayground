# Experiment requests (round 1)

GPU runs for the coordinator. Each run uses `testProfiles/ImputeValidation/v15/job.sh` (BCP, 7 measures, phase-4
protocol: `--validate-rounds 3 --validate-scans-per-bin 20 --validate-max-share 0.5`, folds by subject) unless stated
otherwise. Please put the outputs in a new folder `testProfiles/ImputeValidation/v16/` and keep `--validate-dump-dir`
on, so that the blends can be re-scored offline by `scripts/dump_analysis.py`.

Priority order: R1 > R2 > R3 > R4 > R5.

## R1. Fresh validation seeds for the released default (selection bias)

**Why.** All hyperparameters, the blend variant and the weight table were chosen on seeds 0-2. The weight table is
cross-fitted by subject, but the choice among variants is not. A reviewer will ask for an estimate on draws not used
for any decision.

**What.** Seeds 3, 4, 5 with the transformer configuration of R3 (400 epochs) and the built-in weight table, which
`validate_pass` now scores directly as the setting `table: ...`:

    for s in 3 4 5; do ./job.sh H_s$s $s $GPU --validate-methods prior-mean,population,transformer \
      --validate-transformer-patch 8 --validate-transformer-width 192 --validate-transformer-layers 6 \
      --validate-transformer-hybrid 80 --transformer-epochs 400 --validate-measure-families dti,noddi \
      --validate-dump-dir $V16/dump_H_s$s; done

Report: the scan overlap with seeds 0-2 (the scripts compute it). Scored against PPCA + SIREN and the fixed blend
on the same cells. Estimated cost: 3 runs x ~2.5 h on one GPU.

## R2. External test cohort: HBCD

**Why.** One normative cohort only. The question is whether the method ranking and the size of the gains carry over to
a second infant cohort with a different acquisition and age distribution (mostly 0-9 months).

**What.** (a) The same validation on HBCD alone (`--profiles-dir v15/data/HBCD/Profiles_Clean --age-csv
v15/hbcd_ages.csv`), 3 seeds, settings prior-mean, population (80) + SIREN, transformer (400 epochs), fixed blend, table
blend; HBCD has 133 scans in 10-60 months, so 20 per bin are available in every bin.
(b) Transfer: validate HBCD scans with the norm, PPCA and transformer fitted on BCP only (`--model` / `--transformer-model`
saved from `v15/impute_default`), to show what happens when a small clinical cohort is imputed with a model from another
study. If (b) needs code that does not exist (validation with a fixed external model), please say so and we will
describe it as future work.

## R3. Realistic missingness masks

**Why.** Hidden values are drawn at random within each pattern; real rejections are concentrated in some tracts
(paper Fig. 2b) and may be associated with ages or subjects (missing not at random).

**What.** A validation pass that transplants the real missingness mask of a randomly chosen BCP scan with rejected
tracts (scan x tract x measure from `Profiles_Clean`) onto a complete validation scan, 3 rounds, 3 seeds, same settings as
R1. This needs a small extension of `hide()` (a "real" pattern reading the masks of other scans); if that is out of
scope, CPU-side alternative: re-score the existing dumps restricted to hidden whole profiles of tracts weighted by their
real rejection rate (we can do this offline; tell us which you prefer).

## R4. Seeds 1 and 2 for the single-seed checks

**Why.** Context inputs (`R1_s0`) and 3 members (`R2_s0`) were run on seed 0 only. The conclusion (no gain) is unlikely to
change, but a reviewer may ask for consistency with the other contrasts.

**What.** `queue3.sh` cases R1 and R2 with seeds 1 and 2 (200 epochs, as before).

## R5. Downstream impact on an age-trajectory analysis (CPU, no GPU needed if the imputed tables exist)

**Why.** Imputed values are pulled towards the norm; we should show what that does to a typical analysis.

**What.** Using `v15/impute_default` (imputed BCP tables) and the masks: fit per-tract age trajectories of FA and MD
(e.g. a spline of log age) on (i) observed values only, (ii) observed + imputed values, and compare the fitted curves and
their CIs. The writer can do this on the CPU if the coordinator confirms that `v15/impute_default` is the 0.9.8 default
run (log says `--fit-transformer-model ... impute_default_transformer.pt`) and where the mask tables are.
