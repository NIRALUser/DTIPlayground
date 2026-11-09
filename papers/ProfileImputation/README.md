# Imputing diffusion profiles of white matter fiber tracts in early brain development

Manuscript (target: Imaging Neuroscience; fallback MELBA) on the evaluation of `dmrifiberprofile impute-profiles`
(DTIPlayground 0.9.8).

## Layout

| Path | Content |
|------|---------|
| `main.tex`, `refs.bib`, `main.pdf` | manuscript, bibliography, compiled PDF |
| `tables/` | generated LaTeX tables and `macros.tex` / `descriptives_macros.tex` (every number quoted in the text) |
| `figures/` | generated figures (PDF for the paper, PNG previews) |
| `scripts/` | the analysis scripts; `scripts/cache/` intermediate CSVs (not in the repository, see below) |
| `experiments/requests.md` | GPU runs requested from the coordinator |
| `reviews/` | reviewer reports and responses |

Do not edit `tables/*.tex` or `figures/*` by hand: they are overwritten by the scripts.

The intermediate caches (`scripts/cache/`), the local rebuild check (`rebuild_check/`) and the LaTeX build files are
not in the repository (`.gitignore`). `bash scripts/run_all.sh` regenerates the caches; it needs the validation result
folders (`testProfiles/ImputeValidation/v10`...`v16`, including the cell dumps and the E4 fold models) and the profile
tables of both cohorts, at the paths set in `scripts/common.py`. `QUICK=1` works only once the caches exist.

## Rebuild

    bash scripts/run_all.sh          # everything (several CPU hours: baselines, O1/O3, E4)
    QUICK=1 bash scripts/run_all.sh  # tables, figures and PDF from the existing caches (~2 min)

or step by step (Python: `/tools/devel/linux/Anaconda/Anaconda3/envs/dmriplayground_latest/bin/python`):

1. `scripts/descriptives.py` - cohort and missingness descriptives from the profile tables (reads them with the
   reader of `impute_profiles.py`) -> `tables/tab_data.tex`, `tables/descriptives_macros.tex`, `cache/desc_*.csv`
2. `scripts/dump_analysis.py` - cell-level analyses of the phase-6 validation dumps: cross-fitted weight-table blends,
   the HBCD-trained transformer combined with the BCP default, per-scan scores, error by distance, the refitted weight
   tables -> `cache/dump_*.csv`
3. `scripts/make_tables.py` - all tables, paired statistics and `tables/macros.tex`
4. `scripts/make_figures.py [name ...]` - all figures
5. `pdflatex main; bibtex main; pdflatex main; pdflatex main`

Revision 1 (see `reviews/response_r1.md`) added:

- `scripts/e6_kernel_norm.py`: leave-subject-out kernel age norms in the validation folds (E6) -> `cache/kernel_norm_*.npz`
- `scripts/dump_analysis.py` (generalized): datasets `bcp` (v15 dumps), `e1`, `e3` (v16 dumps): blends incl. the
  shipped table, kNN-base blends, kernel-norm reference, calibration by band (E7), per tract (O6), load (O7), ages
- `scripts/baselines.py`: generic cohort imputers on the same hidden cells (E8)
- `scripts/batch_check.py`: residual age x cohort difference after the batch correction (M4)
- `scripts/o1_o3.py`: learning curve and finer age bins (O1, O3; CPU PPCA fits)
- `scripts/e4_downstream.py`, `scripts/e4_tables.py`: downstream analyses with transplanted real masks (E4, including the differential-missingness scenarios diff03/diff01; needs the
  fold transformers `v16/e4_fold*/transformer.pt`)
- `scripts/revision_tables.py`: all revision tables and `tables/macros_rev.tex`
- `scripts/realmask.py`, `scripts/realmask_tables.py`: real-mask pattern by donor (round-2 review): the donor of every
  pass is recovered by replaying the validation's draws, then scored with all donors and with donors within
  `--max-missing-tracts 0.5`, by donor load and by the share of the scan hidden -> `tables/realmask_*.tex`,
  `tables/macros_realmask.tex`, `figures/fig_realmask.*`
- `scripts/v16_tables.py`: E1, E2 (real-mask pattern), E3, E5 from `v16/*_report` -> `tables/v16_*.tex`,
  `tables/macros_v16.tex`; results that do not exist yet are `\pending{}` (orange in the PDF)

`scripts/common.py` holds the paths, the names of the validation settings and the scoring (it reproduces
`v13/analyse_c.py`, `v15/analyse.py`; `dump_analysis.py` imports `v15/blend.py` for the blend learners).

## Which result folders feed what

All under `/NIRAL/devel/linux/DTI/testProfiles/ImputeValidation`. Runs of v12, v13 and v15 share the protocol (BCP,
7 measures, 20 scans per age bin capped at half, 3 rounds, seeds 0-2, 5 folds by subject) and hide identical values
for the same seed.

| Source | Used for |
|--------|----------|
| `v12/data/BCP/Profiles_Clean`, `v15/data/HBCD/Profiles_Clean`, `v15/hbcd_ages.csv` | tab_data, fig_data, missingness and axis-proximity macros, fig_patterns (a, b) |
| `/NIRAL/tools/atlas/DTI/DTI_IBISEP_Feb26/FiberAxis` | 3-D positions (Fig. 3, axis proximity) |
| `v13/P12_s{0,1,2}` | phases 1-2 rows of tab_main, fig_progression, fig_metric_heat, fig_distance, absolute RMSE of the age-bin mean |
| `v13/P3_s{0,1,2}` | phase 3 (PPCA components, kNN/SIREN residuals), paired contrasts |
| `v12/S{0,1,2}` | phase 4 (graph U-Net) |
| `v15/E_s*` | U-Net blends, reference age-bin mean for Q and P |
| `v15/Q_s*` | acquisition correction |
| `v15/T_s*` | transformer (200 epochs), fixed and precision blends, seed-0 reference for R1/R2 |
| `v15/R3_s*`, `v15/dump_R3*` | transformer (400 epochs), weight table (cross-fitted), fig_weights, fig_age, tab_calibration, tab_absolute |
| `v15/P_s*`, `v15/dump_P*` | BCP+HBCD pooled runs; HBCD-trained transformer combined with the BCP default |
| `v15/R1_s0`, `v15/R2_s0` | context inputs, seed ensembles (seed 0) |
| `v14/*.log` (`RESULT` lines) | quick screens: functa, partial VAE, age-dependent PPCA, transformer variants (tab_screens, fig_screens) |
| `v10/B1,B2,Q5,Q6_s*` | phase 3b: pooling and continuous age norms, 11 measures (tab_pooling) |
| `docs/_static/impute_validation/phase2/stratified_overall.csv` (repo) | SIREN grid (fig_siren_grid; 30 scans, 1 seed, 11 measures) |
| `docs/_static/impute_validation/phase3/grid_caps_long.csv` (repo) | distance limit (fig_cap; 30 scans, 1 seed, 11 measures) |
| `v16/E1_s{3,4,5}`, `v16/dump_E1_s*` | untouched subjects (E1), real-mask pattern (E2) |
| `v16/E3_s{0,1,2}`, `v16/dump_E3_s*` | HBCD alone (E3) |
| `v16/E5i,E5ii,E5iii_s{0,1,2}` | pooling decomposition (E5) |
| `v16/e4_fold*/transformer.pt`, `v16/e4_complete_folds.csv`, `v16/e4_fold*.log` | downstream analyses (E4) |
| `v11/A,D,E,F_s0`, `v11/H_s*` | graph U-Net development (tab A8), 11 measures (tab A10) |
| `v15/cross_s*.pkl`, `v15/Q_s*_report/validation/acquisition_correction.csv` | blend learners (tab A7), acquisition offsets |
| `docs/_static/impute_validation/phase3/grid_caps_long.csv` (repo) | noise models (tab A9) |
| training logs `v11`-`v15` | tuning budget (tab A14) |
| `dtiplayground/.../impute_profiles.py` `ENSEMBLE_TABLES` | checked against the refitted weight tables (tab_weights) |

Cross-checks against `docs/ImputeValidation.rst`: default 0.614, U-Net beyond 0.610, transformer alone 0.654, fixed
blend 0.582, 400-epoch blend 0.576, pooled default 0.626, HBCD transformer alone 0.580, pooling 1.010 (0.992-1.027,
p = 0.37) are reproduced exactly. The cross-fitted weight tables give 0.567 / 0.538 pooled over seeds (as documented)
and 0.569 / 0.540 as the mean of the per-seed scores (used in the paper for consistency with the other rows).
