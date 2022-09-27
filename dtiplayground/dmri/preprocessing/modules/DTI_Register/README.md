### DTI_Register

##### Introduction
DTI_Register allows you to register DTI

##### Protocol Parameters

- protocol:
      method: 
        type: list
        caption: Method
        default_value: ANTs
        candidates:
          - value: ANTs
            caption: ANTs
            description: Use ANTs to register
        description: Method to register DTI (ANTs)
      referenceImage:
        type: string
        caption: Reference Image Path 
        default_value: null
        description: Reference (Fixed Image)
      ANTsPath:
        type: string
        caption: ANTS directory
        default_value: $ANTSDIR
        description: ANTs installation directory (default is dtiplayground-tools/ANTs)
        tag:
          - ANTS
      ANTsMethod:
        type: string
        caption: ANTS method
        default_value: useScalar-ANTS
        tag:
          - ANTS
      registrationType:
        type: list
        caption: Registration Type
        default_value: GreedyDiffeo
        candidates:
          - value: GreedyDiffeo 
            caption: Greedy Diffeo
            description: Greedy Diffeo
        description: Registration Type
        tag:
          - ANTS
      similarityMetric:
        type: list
        caption: Similarity Metric
        default_value: CC
        candidates:
          - value: CC 
            caption: Cross Correlation
            description: Cross Correlation
        description: Similarity Metric 
        tag:
          - ANTS 
      similarityParameter:
        type: number
        caption: Similarity Parameter
        default_value: 4
        description: Similarity Parameter
        tag:
          - ANTS
      ANTsIterations:
        type: string
        caption: Iterations
        default_value: 100x50x25
        description: Iteration parameter for ANTS
        tag:
          - ANTS
      gaussianSigma:
        type: number
        caption: Gaussian Sigma
        default_value: 3
        description: Gaussian Sigma
        tag:
          - ANTS

##### Examples


##### Author(s)

- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
- Timothée Teyssier - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
