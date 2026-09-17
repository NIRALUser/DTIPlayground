### DTI_Register

##### Introduction
DTI_Register registers the DTI to a reference DTI (e.g. an atlas, or the age appropriate mean tensor of a normative model, see referenceNormativeModel) with DTI-Reg: an initial affine transform of the scalar images (BRAINSFit), refined by a diffeomorphic ANTS registration of the scalar images; the tensors are resampled log-Euclidean with reorientation. The defaults are those of the FiberAnalysis pipeline.

Outputs: `registered_dti.nrrd` (DTI in reference space), `registered_<name>` for the diffusion metrics of the DTI folder (see registerMetrics), `displacementField.nrrd` (for every reference position, the displacement to the corresponding position in the DTI: the field EXTRACT_Profile uses to sample the DTI along reference-space fibers), `inverse_displacementField.nrrd`, and `initialAffine.txt` with the initial affine transform.

##### Protocol Parameters

- method: ANTs (default)
- referenceImage: reference (fixed) DTI
- referenceNormativeModel: normative model of the reference atlas (folder with `manifest.json` and `<age bin>/DTI_mean.nrrd`, written by `dmrifiberprofile qc-registration --build-normative`). The DTI is then registered to the mean tensor of the age bin of the subject, so the target is age appropriate; the mean tensors are on the grid of the atlas, so the result is still in atlas space. Without a model, an age or a usable bin, referenceImage is used (with a warning)
- age: age of the subject in the unit of the age bins (months); read from the image path with ageRegex if not set
- ageRegex: regular expression for the age in the path of the input image (group 1), default `ses-(\d+)m`
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
- registerMetrics: apply the displacement field to the diffusion metrics in the folder of the input DTI that share its file name prefix (e.g. `<scan>_dwi_QCed_FA.nii.gz`, `_NODDI_NDI.nii.gz` or `_FWtensor.nrrd` for `<scan>_dwi_QCed_tensor.nrrd`), default true. Tensor images are resampled log-Euclidean with reorientation (ResampleDTIlogEuclidean, as DTI-Reg resamples the DTI), scalar images linearly; written as `registered_<name>`
- metricExclude: comma delimited parts of file names that are not registered, default `mask`; integer images and images that are neither scalar nor tensor (e.g. NODDI directions) are not registered either
- BRAINSFitSamplingPercentage: fraction (0-1) of the voxels sampled by BRAINSFit, default 0.5 (reproducible to ~0.4 mm; smaller values are faster but less reproducible)

##### Examples


##### Author(s)

