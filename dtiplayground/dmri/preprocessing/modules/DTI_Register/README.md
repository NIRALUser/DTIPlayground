### DTI_Register

##### Introduction
DTI_Register registers the DTI to a reference DTI (e.g. an atlas, or the age appropriate mean tensor of a normative model, see referenceNormativeModel), with one of two methods:

- **ANTs** (default): DTI-Reg, an initial affine transform of the scalar images (BRAINSFit), refined by a diffeomorphic ANTS registration of the scalar images (FA); the tensors are resampled log-Euclidean with reorientation. The defaults are those of the FiberAnalysis pipeline.
- **TensorSVF**: the same initial affine, a rotation of the tensor frame (tensorFlip rotation), then a diffeomorphic registration of the tensors themselves (stationary velocity field, PyTorch; the GPU when available, otherwise the CPU). It matches the orientation and shape of the tensors (normalised deviatoric part of the log tensors, finite strain reorientation), so it is insensitive to the anisotropy differences between a subject and the reference (age, resolution). When a free water fraction map of the DTI is available (multi-shell data: `<prefix>FWf` of the FW-tensor fit or `<prefix>NODDI_FWF`) with its reference mean map (`FWF_mean` / `NODDI_FWF_mean` of the age bins of the normative model), a free water term also aligns the ventricles; otherwise (single shell) the tensors alone are registered.

  Recommended settings: `method: TensorSVF`, `tensorFlip: rotation`, `referenceNormativeModel` with the age of the subject. On 137 scans of 4 studies (0-12 years, infants at 1.5-2 mm to school age, ventricles from small to mildly enlarged) against DTI-Reg and DTI-TK: median white matter principal direction angle 7.2 deg (tensors only) / 7.2 deg (with free water) vs 10.5 deg (DTI-Reg) and 8.0 deg (DTI-TK), periventricular white matter 9.9 deg vs 13.4 deg (DTI-Reg); ventricle overlap (Dice) 0.81 with the free water term vs 0.70 (DTI-Reg); smoother deformations (sd of the log Jacobian 0.19-0.25 vs 0.32), no folding; and the least affected by a synthetic change of the ventricle size. Run time about 1.5 min on a GPU (RTX A6000), 12 min (29 min CPU time, 7 GB of memory) on 4 CPU cores.

Outputs: `registered_dti.nrrd` (DTI in reference space), `registered_<name>` for the diffusion metrics of the DTI folder (see registerMetrics), `displacementField.nrrd` (for every reference position, the displacement to the corresponding position in the DTI: the field EXTRACT_Profile uses to sample the DTI along reference-space fibers), `inverse_displacementField.nrrd`, and `initialAffine.txt` with the initial affine transform. TensorSVF also writes `tensor_registration.json` (device, settings, Jacobian, time) and, with tensorFlip rotation, `tensor_frame_rotation.json`.

##### Protocol Parameters

- method: ANTs (default, DTI-Reg) or TensorSVF (diffeomorphic tensor registration, see the introduction)
- referenceImage: reference (fixed) DTI
- referenceNormativeModel: normative model of the reference atlas (folder with `manifest.json` and `<age bin>/DTI_mean.nrrd`, written by `dmrifiberprofile qc-registration --build-normative`). The DTI is then registered to the mean tensor of the age bin of the subject, so the target is age appropriate; the mean tensors are on the grid of the atlas, so the result is still in atlas space. Without a model, an age or a usable bin, referenceImage is used (with a warning)
- age: age of the subject in the unit of the age bins (months); taken from ageCSV, or read from the image path with ageRegex, if not set. It overrides the others for every image: for an age of only the images that have none, use ageFallback
- ageCSV: CSV/TSV with the age of each scan, for cohorts whose session names don't carry the age (`ses-V02`, ...). The same table as `dmrifiberprofile qc-registration --age-csv`: the subject and session columns are detected (`participant_id`/`session_id` and the usual variants), as is the age column (`age`, `age_months`, `candidate_age`, ... ), and a table without a session column gives one age per subject that applies to all of its sessions. The subject and session of the scan are read from its path (`sub-<id>`, `ses-<id>`), else from the IBIS organization, a 6 digit id folder followed by a visit folder starting with `V` (`.../999434/VSA-CVD/...` is subject `999434`, session `SA-CVD`; the table may name the session `SA-CVD` or `VSA-CVD`). A scan that is not in the table, an unreadable table and a path with neither fall back to ageRegex, each with a warning
- ageColumn: name of the ageCSV column holding the age, when it should not be auto-detected
- ageSubjectColumn, ageSessionColumn: names of the ageCSV columns holding the subject id and the session / visit, when they should not be auto-detected
- ageUnits: units of that column and of ageFallback, months (default), years, weeks or days; converted to the months of the age bins (age and ageRegex are in months)
- ageRegex: regular expression for the age in the path of the input image (group 1), default `ses-(\d+)m`, used when neither age nor ageCSV gives one
- ageFallback: age, in ageUnits (months by default), of an image that neither age, ageCSV nor ageRegex gives one, with a warning in the log; default none, such an image is registered to referenceImage

The age is taken from the first of these that has one: the protocol `age` (or the global variable `age`), the row of the scan in `ageCSV`, then `ageRegex` on the path, then `ageFallback`. In a batch, a single table for the whole cohort is the simplest way: put `ageCSV` in the protocol. The age options can also be given as global variables of `dmriprep run -g`, by their name or in snake case (`age_csv`, `age_column`, `age_subject_column`, `age_session_column`, `age_units`, `age_fallback`); a value in the protocol wins, except for `ageUnits`. A column name with a comma (LORIS exports, `"VSA demographics,CandID"`) is quoted on the command line: `-g age_csv ages.csv age_subject_column 'VSA demographics,CandID' age_column 'VSA demographics,Age_at_visit_start'`. A per scan age can also be given in the datasheet of `dmriprep run-batch` with the `overrides` column, e.g. `{"DTI_Register": {"age": 12}}`.
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
- tensorFlip: correction of the tensor frame applied to the DTI before the registration (as `dmrifiberprofile flip-tensor`), for tensors whose components don't match the frame of their header: none, auto, the axes to flip (D' = R D R^T, R = diag(+-1), e.g. `x` or `x,z`), or `voxel` for components in the frame of the voxel axes (tensors estimated in voxel coordinates), which are rotated into the space of the header (on an oblique grid a rotation no flip corrects; with flips e.g. `voxel,x`); when empty (default), the global variable `tensor_flip`, else none. auto scores the flips in the header frame and in the voxel frame as `dmrifiberprofile detect-tensor-flip`: by the median angle between the principal directions of the DTI and of the reference after the initial affine transform (computed from the scalar image, which a flip doesn't change), or by the coherence of the principal directions along the tracts when there is no initial affine. The corrected DTI is written as `input_flipped.nrrd`, and tensor images among the diffusion metrics get the same correction before they are registered. With an initial affine, every mode but rotation also checks the frame: with none, whether a flip fits the reference better (a warning, and `tensor_flip_suggested` in the module output); otherwise, and when none fits best, the rotation of the frame left after the correction (`tensor_frame_residual_deg`) and warns when it is above 5 deg and lowers the mean angle to the reference by more than 1 deg, which only `rotation` corrects (in 139 test scans of 4 studies: 2 scans, 11.5 and 31.5 deg; the voxel frame of oblique acquisitions is corrected by auto). All these comparisons go through the initial affine, so the head position doesn't count as a frame rotation; when the affine doesn't align the DTI with the reference (FA correlation below 0.25 at the same positions), auto uses the coherence only and rotation leaves the frame as is, with a warning
  With `rotation` (needs an initial affine), any rotation of the frame is estimated, flips and axis swaps included: the 24 axis permutations and flips, then a continuous refinement, by the FA weighted mean angle between the principal directions of the DTI and of the reference in white matter after the initial affine (e.g. tensors of an oblique acquisition whose gradients were not rotated into the frame of the image, which `voxel` also corrects, or a frame rotated otherwise: 11.5 and 31.5 deg beyond the best auto correction in 2 of 139 test scans). The rotation is written to `tensor_frame_rotation.json`, and tensor images among the diffusion metrics get the same rotation
- tensorFlipFAThreshold: FA threshold of the white matter voxels used by the automatic flip detection, default 0.3
- BRAINSFitTransforms: BRAINSFit transform stages, default Rigid,Affine
- BRAINSFitInitializeTransformMode: default useCenterOfHeadAlign
- registerMetrics: apply the displacement field to the diffusion metrics in the folder of the input DTI that share its file name prefix (e.g. `<scan>_dwi_QCed_FA.nii.gz`, `_NODDI_NDI.nii.gz` or `_FWtensor.nrrd` for `<scan>_dwi_QCed_tensor.nrrd`), default true. Tensor images are resampled log-Euclidean with reorientation (ResampleDTIlogEuclidean, as DTI-Reg resamples the DTI), scalar images linearly; written as `registered_<name>`
- metricExclude: comma delimited parts of file names that are not registered, default `mask`; integer images and images that are neither scalar nor tensor (e.g. NODDI directions) are not registered either
- freeWater (TensorSVF): auto (default: the FW-tensor fraction `<prefix>FWf` of the folder of the input DTI, else the NODDI fraction `<prefix>NODDI_FWF`, each when the folder of the reference tensor has its mean map `FWF_mean` / `NODDI_FWF_mean`; otherwise the tensors only), FWf, NODDI_FWF (an error when missing), or none
- freeWaterImage, referenceFreeWater (TensorSVF): the free water map of the DTI and the reference mean map, when they are not found as above
- freeWaterWeight (TensorSVF): weight of the free water term, default 1 (2 overlaps the ventricles slightly more, but aligns the white matter of scans with small ventricles worse)
- tensorRegRegularization (TensorSVF): smoothness weight of the velocity field, default 0.15 (below 0.1 the deformation may fold)
- tensorRegSmoothing (TensorSVF): Gaussian sigma (voxels) of the velocity field, default 0.5
- tensorRegLevels, tensorRegIterations (TensorSVF): resolution levels (downsampling factors) and iterations per level, default 4x2x1 and 200x150x100
- tensorRegDevice (TensorSVF): auto (default, the GPU when available), cpu, cuda or cuda:<n>
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

For the diffeomorphic tensor registration, set `method: TensorSVF` and `tensorFlip: rotation` in the protocol (e.g.
with `dmriprep make-protocols -d DTI_Register` and an edit of the protocol file); the free water term is used
automatically when the folder of the DTI has a `<prefix>FWf` or `<prefix>NODDI_FWF` map.

##### Examples


##### Author(s)

