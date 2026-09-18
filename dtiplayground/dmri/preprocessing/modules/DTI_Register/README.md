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
- tensorFlip: correction of the tensor frame applied to the DTI before the registration (as `dmrifiberprofile flip-tensor`), for tensors whose components don't match the frame of their header: none, auto, the axes to flip (D' = R D R^T, R = diag(+-1), e.g. `x` or `x,z`), or `voxel` for components in the frame of the voxel axes (tensors estimated in voxel coordinates), which are rotated into the space of the header (on an oblique grid a rotation no flip corrects; with flips e.g. `voxel,x`); when empty (default), the global variable `tensor_flip`, else none. auto scores the flips in the header frame and in the voxel frame as `dmrifiberprofile detect-tensor-flip`: by the median angle between the principal directions of the DTI and of the reference after the initial affine transform (computed from the scalar image, which a flip doesn't change), or by the coherence of the principal directions along the tracts when there is no initial affine. The corrected DTI is written as `input_flipped.nrrd`, and tensor images among the diffusion metrics get the same correction before they are registered
- tensorFlipFAThreshold: FA threshold of the white matter voxels used by the automatic flip detection, default 0.3
- BRAINSFitTransforms: BRAINSFit transform stages, default Rigid,Affine
- BRAINSFitInitializeTransformMode: default useCenterOfHeadAlign
- registerMetrics: apply the displacement field to the diffusion metrics in the folder of the input DTI that share its file name prefix (e.g. `<scan>_dwi_QCed_FA.nii.gz`, `_NODDI_NDI.nii.gz` or `_FWtensor.nrrd` for `<scan>_dwi_QCed_tensor.nrrd`), default true. Tensor images are resampled log-Euclidean with reorientation (ResampleDTIlogEuclidean, as DTI-Reg resamples the DTI), scalar images linearly; written as `registered_<name>`
- metricExclude: comma delimited parts of file names that are not registered, default `mask`; integer images and images that are neither scalar nor tensor (e.g. NODDI directions) are not registered either
- BRAINSFitSamplingPercentage: fraction (0-1) of the voxels sampled by BRAINSFit, default 0.5 (reproducible to ~0.4 mm; smaller values are faster but less reproducible)

##### Command line

The module can be run without a protocol file, with the reference and the age given as global variables:

```
dmriprep run -i <subject DTI> -o <output dir> -d DTI_Register \
    -g reference_dti <atlas DTI> reference_normative_model <normative model dir> age <months>
```

A diffusion tensor NRRD given with `-i` is registered directly; otherwise the DTI to register is `dti_path` (set by
DTI_Estimate in a full pipeline, or given with `-g dti_path <subject DTI>`). `reference_normative_model` and `age` are
optional (the age is otherwise read from the image path). Add `tensor_flip auto` (or e.g. `tensor_flip x`) to detect
and correct a flip of the tensor frame before the registration. Options of the protocol take precedence over these
variables.

##### Examples


##### Author(s)

