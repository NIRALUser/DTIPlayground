### DTI_Register

##### Introduction
DTI_Register allows you to register DTI images to a template. It is based on the ANTs software. It allows to register the DTI images to a template and to apply the transformation to the FA image.

##### Protocol Parameters

- method is a list with a default value of ANTs, it will check the method to register DTI (ANTs)

- referenceImage is a string with a default value of null, it will be the reference (Fixed Image) path

- ANTsPath is a string with a default value of $ANTSDIR, it will be the ANTs installation directory (default is dtiplayground-tools/ANTs)

- ANTsMethod is a string with a default value of useScalar-ANTS, it will be the ANTs method

- registrationType is a list with a default value of GreedyDiffeo, it will check the registration type

- similarityMetric is a list with a default value of CC, it will check the similarity metric

- similarityParameter is an integer number with a default value of 4, it will be the similarity parameter

- ANTsIterations is a string with a default value of 100x50x25, it will be the iteration parameter for ANTS

- gaussianSigma is an integer number with a default value of 3, it will be the gaussian parameter sigma

##### Examples


##### Author(s)

