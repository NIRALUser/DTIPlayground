### DTI_Register

##### Introduction
DTI_Register registers the DTI to a reference DTI (e.g. an atlas) with DTI-Reg: an initial affine transform of the scalar images (BRAINSFit), refined by a diffeomorphic ANTS registration of the scalar images; the tensors are resampled log-Euclidean with reorientation. The defaults are those of the FiberAnalysis pipeline.

Outputs: `registered_dti.nrrd` (DTI in reference space), `displacementField.nrrd` (for every reference position, the displacement to the corresponding position in the DTI: the field EXTRACT_Profile uses to sample the DTI along reference-space fibers), `inverse_displacementField.nrrd`, and `initialAffine.txt` with the initial affine transform.

##### Protocol Parameters

- method: ANTs (default)
- referenceImage: reference (fixed) DTI
- ANTsPath: ANTs installation directory (default is dtiplayground-tools/ANTs)
- ANTsMethod: useScalar-ANTS (default)
- registrationType: GreedyDiffeo (default)
- similarityMetric: CC (default)
- similarityParameter: radius of the CC metric, default 2
- ANTsIterations: default 100x50x20
- gaussianSigma: default 1
- ANTsTransformationStep: default 0.25
- ANTsUseHistogramMatching: default true
- scalarMeasurement: scalar image registered, FA (default) or MD
- tensorCorrection: correction of tensors with negative eigenvalues, abs (default), zero, nearest or none
- initialAffine: BRAINSFit (default, affine registration of the scalar images, fixed = reference, moving = DTI), file (initialAffineFile) or none
- initialAffineFile: ITK transform file used with initialAffine 'file'
- BRAINSFitTransforms: BRAINSFit transform stages, default Rigid,Affine
- BRAINSFitInitializeTransformMode: default useCenterOfHeadAlign
- BRAINSFitSamplingPercentage: fraction (0-1) of the voxels sampled by BRAINSFit, default 0.5 (reproducible to ~0.4 mm; smaller values are faster but less reproducible)

##### Examples


##### Author(s)

