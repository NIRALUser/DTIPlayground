### DWI_Denoise

##### Introduction

Denoises the DWI with DIPY, either with Marchenko-Pastur PCA of local patches (MP-PCA, Veraart et al. 2016, the method
of MRtrix `dwidenoise`) or with Patch2Self (Fadnavis et al. 2020), which predicts each volume from the other volumes.
Both assume that the noise is independent between voxels: use this module first in the pipeline, on the raw images,
before any interpolation (EDDYMOTION_Correct, SUSCEPTIBILITY_Correct, BASELINE_Average) and before GIBBS_Correct.

##### Protocol Parameters

- method: `mppca` (default) or `patch2self`.
- patchRadius (MP-PCA): patch radius in voxels (2: 5x5x5 patches). 0 (default) chooses the smallest patch with at
  least as many voxels as there are volumes.
- patch2selfModel (Patch2Self): regression model, `ols` (default), `ridge` or `lasso`. Patch2Self treats b-values up to
  50 as b=0 volumes (as QSIPrep) and denoises them too.

##### Outputs

- The denoised image (float) for the next module.
- `noise_sigma.nii.gz` (MP-PCA), copied as `<base>_DWI_noise_sigma.nii.gz`: the noise level of each voxel.
- `noise_residual.nii.gz` (Patch2Self), copied as `<base>_DWI_noise_residual.nii.gz`: RMS over the volumes of the
  removed signal (input - denoised), as the residual map of QSIPrep.
- `denoise_qc.tsv` (`<base>_DENOISE_QC.tsv`): noise level (median MP-PCA sigma in the brain), b=0 SNR (median of the
  mean b=0 over sigma), or for Patch2Self the median of the residual map, standard deviation of the removed signal in the brain (b=0 and diffusion weighted volumes).
- `denoise.png`: middle slice of a b=0 and of a highest shell volume, before, after and their difference (also in the
  module report and QC_Report).
