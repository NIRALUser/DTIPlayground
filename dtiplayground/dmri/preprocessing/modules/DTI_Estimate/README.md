### DTI_Estimate

##### Introduction

DTI_Estimate will run DTI by several methods like : 
- runDTI
- runDTI_DIPY
- runDTI_dtiestim

##### Protocol Parameters

- method is a list with a default value of dipy, it will choose beetween different candidates the method to estimate DTI : dipy by using DIPY library or dtiestim by using NIRAL dtiestim software

- optimizationMethod is a list with a default value of wls, it will choose beetween different candidates the optimization method: wls by using Weighted Least Squares, lls by using Linear Least Squares, nls by using Non-Linear Least Squares, ml by using Maximum Likelihood (dtiestim Only), restore by using RESTORE (DIPY Only)

- correctionMethod is a list with a default value of zero, it will choose beetween different candidates the tensor correction method when a computed tensor is not positive semi-definite (dtiestim only): zero by substituting to zero value, nearest by using Nearest (dtiestim only), abs by using Absolute (dtiestim only), none by using None (dtiestim only)

- maxBValue (default 1600): the shells with a b-value above it are left out of the tensor fit, with either method, and
  of the tensor fit QC: on multi-shell data the high b-value shells bias the tensor, the signal no longer decaying
  mono-exponentially (kurtosis). Whole shells are kept or dropped, by their mean b-value (b=1605 is in the shell of
  1600). 0 or empty fits all the shells. When no diffusion weighted shell is at or below it (single-shell data at
  b=2000, say), all the volumes are used, with a warning. The output image keeps all the volumes, for the modules after
  it (MULTI_SHELL_Estimate, BRAIN_Tractography); the log and the result (`fit_volumes`) say which shells were fitted

##### Examples


##### Author(s)

