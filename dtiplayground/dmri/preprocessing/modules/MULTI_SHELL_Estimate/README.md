### MULTI_SHELL_Estimate

##### Introduction

MULTI_SHELL_Estimate fits diffusion models to the image produced by the previous modules of the pipeline, within the
brain mask (`maskPath`, else the mask of BRAIN_Mask, else the whole image):

- **dipy**
  - `dti`: diffusion tensor, fitted on the shells up to `maxBValue` (default 1600, as DTI_Estimate); FA, CFA, MD, AD, RD,
    eigenvalues/eigenvectors. With DTI_Estimate in the protocol, its outputs are named `MULTI_SHELL_DTI`
    (`<name>_MULTI_SHELL_DTI_FA`, ...) so that they don't replace those of DTI_Estimate (`<name>_DTI`, `<name>_DTI_FA`);
    without it, `DTI` as before
  - `dki`: diffusion kurtosis (needs 2+ non-zero shells); diffusion tensor, kurtosis tensor (15 elements, dipy order),
    FA, MD, AD, RD, MK, AK, RK, MKT (kurtosis clipped to [0, 3]), KFA
  - `msdki`: mean signal diffusion kurtosis; MSD, MSK, plus the diffusion and kurtosis tensors of the full DKI fit
  - `fwdti`: free water elimination DTI (needs 2+ non-zero shells); diffusion tensor of the tissue, FA, MD, AD, RD and
    the free water fraction (FW)
  - `ivim`: intravoxel incoherent motion (needs low b-values); S0, perfusion fraction, D* (DSTAR), D
- **amico**: NODDI; NDI, ODI, FWF and the principal direction (`AMICO/fit_*.nii.gz`)
- **mrtrix3** (ADC): the mono-exponential decay S = S0 exp(-b ADC) fitted by least squares on the log of the signal,
  as mrtrix3's `dwi2adc`; S0 and ADC (outputs `MRTRIX3_S0`, `MRTRIX3_ADC`), set to 0 outside the brain mask.
  `adcImplementation`: `auto` (default) and `builtin` fit it in dtiplayground, without mrtrix3 (identical to dwi2adc
  3.0.3 to float precision on the IBIS test scan); `mrtrix3` runs `dwi2adc`. `adcMaxBValue` (default 0, off): the
  shells above it are left out of the fit; with several shells the ADC depends on their b-values

The tensors (`tensor.nrrd`, `kurtosis_tensor.nrrd`) are in the frame of the gradients (the measurement frame of the image,
written in the NRRD header), like DTI_Estimate, with the components first (`sizes: 6 x y z`, or 15 for the kurtosis
tensor), as teem and 3D Slicer write them.

##### Protocol Parameters

- `tool`: dipy, amico or mrtrix3
- `model`: the model of the tool: with dipy dti, dki, msdki, fwdti or ivim; with amico `noddi`; with mrtrix3 `adc`
  (for amico and mrtrix3 the model is fixed: another value, as the `dti` of protocols before 0.9.6, is ignored)
- `optimizationMethod_dti` / `optimizationMethod_dki` / `optimizationMethod_fwdti`: fit method of the model
  (`optimizationMethod_dti` is also the DTI fit that AMICO uses for the fiber directions). For DTI, `lls` is dipy's
  ordinary least squares (OLS, LS and LLS are the same fit in dipy); the former `ols` choice was the same and is still
  read. For DKI, `ols` (unweighted) and `wls` (weighted) differ
- `maxBValue` (model dti; default 1600): the shells above it are left out of the DTI fit; 0 or empty fits all
- `split_b_D`, `split_b_S0`: b-values of the two-stage IVIM fit
- `maskPath`: brain mask (NRRD or NIfTI), for all the tools

##### Author(s)
Joshua Barnett
