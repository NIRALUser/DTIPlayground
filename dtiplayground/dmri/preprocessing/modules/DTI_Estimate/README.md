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

##### Examples


##### Author(s)

