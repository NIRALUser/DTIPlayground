### DTI_Estimate

##### Introduction

DTI_Estimate will run DTI by several methods like : 
- runDTI
- runDTI_DIPY
- runDTI_dtiestim

##### Protocol Parameters

- protocol:
      method: 
        type: list
        caption: Method
        default_value: dipy
        candidates:
          - value: dipy
            caption: DIPY
            description: Use DIPY library
          - value: dtiestim
            caption: dtiestim
            description: Use NIRAL dtiestim software
        description: Method to estimate DTI (dipy/dtiestim)
      optimizationMethod:
        type: list
        caption: Optimization Method
        default_value: wls
        candidates:
          - value : wls
            caption: Weighted Least Squares
            description: Weighted Least Squares
          - value : lls
            caption: Linear Least Squares
            description: Linear Least Squares
          - value : nls
            caption: Non-Linear Least Squares
            description: Non-Linear Least Squares
          - value : ml
            caption: Maximum Likelihood (dtiestim Only)
            description: Maximum Likelihood (dtiestim Only)
          - value : restore
            caption: RESTORE (DIPY Only)
            description: RESTORE (DIPY Only)
      correctionMethod:
        type: list
        caption: Tensor Correction
        default_value: zero
        description: Tensor correction method when a computed tensor is not positive semi-definite (dtiestim only)
        candidates:
          - value: zero
            caption: Zero
            description: Substitute to zero value
          - value: nearest
            caption: Nearest (dtiestim only)
            description: Nearest (dtiestim only)
          - value: abs
            caption: Absolute (dtiestim only)
            description: Absolute (dtiestim only)
          - value: none
            caption: None (dtiestim only)
            description: None (dtiestim only)

##### Examples


##### Author(s)

- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
- Timothée Teyssier - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
