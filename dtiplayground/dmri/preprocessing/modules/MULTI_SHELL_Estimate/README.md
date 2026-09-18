### MULTI_SHELL_Estimate

##### Introduction

MULTI_SHELL_Estimate fits diffusion models to the image produced by the previous modules of the pipeline, within the
brain mask (`maskPath`, else the mask of BRAIN_Mask, else the whole image):

- **dipy**
  - `dti`: diffusion tensor; FA, CFA, MD, AD, RD, eigenvalues/eigenvectors
  - `dki`: diffusion kurtosis (needs 2+ non-zero shells); diffusion tensor, kurtosis tensor (15 elements, dipy order),
    FA, MD, AD, RD, MK, AK, RK, MKT (kurtosis clipped to [0, 3]), KFA
  - `msdki`: mean signal diffusion kurtosis; MSD, MSK, plus the diffusion and kurtosis tensors of the full DKI fit
  - `fwdti`: free water elimination DTI (needs 2+ non-zero shells); diffusion tensor of the tissue, FA, MD, AD, RD and
    the free water fraction (FW)
  - `ivim`: intravoxel incoherent motion (needs low b-values); S0, perfusion fraction, D* (DSTAR), D
- **amico**: NODDI; NDI, ODI, FWF and the principal direction (`AMICO/fit_*.nii.gz`)
- **mrtrix3**: `dwi2adc`; S0 and ADC

The tensors (`tensor.nrrd`, `kurtosis_tensor.nrrd`) are in the frame of the gradients (the measurement frame of the image,
written in the NRRD header), like DTI_Estimate.

##### Protocol Parameters

- `tool`: dipy, amico or mrtrix3
- `model`: the dipy model (dti, dki, msdki, fwdti, ivim)
- `optimizationMethod_dti` / `optimizationMethod_dki` / `optimizationMethod_fwdti`: fit method of the model
  (`optimizationMethod_dti` is also the DTI fit that AMICO uses for the fiber directions)
- `split_b_D`, `split_b_S0`: b-values of the two-stage IVIM fit
- `maskPath`: brain mask (NRRD or NIfTI)

##### Author(s)
Joshua Barnett
