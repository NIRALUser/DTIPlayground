# Change log

All notable changes to DTI Playground. The versions are those of `dtiplayground` on PyPI and of the
`niraluser/dtiplayground` Docker image; `dmriprep`, `dmrifiberprofile` and `dmriplayground` share them.

##### 2026-09-24 (v0.8.1)
- Documentation only; the code is the same as 0.8.0
- README: restructured (one intro naming the tools that ship, installation, a section per tool, project information); the change log moved to CHANGELOG.md, the dependency list that was several major versions behind now points at setup.py and requirements.txt, and the unmaintained dtiplayground-native / dmriprep-ui are no longer documented
- Documentation: a reference page for every module and option of dmriprep and dmrifiberprofile (19 modules, 133 options), generated from the module definitions at build time, so a new module or option is documented by the next build
- Documentation: the readthedocs pages describe what was added in 0.7.23 - 0.8.0 (rerunning, denoising and Gibbs ringing removal, the age appropriate registration target, the QC outputs, and the analysis commands of dmrifiberprofile, which were not documented at all); the build configuration asked for a python and an OS image readthedocs has dropped
- Documentation: built and published from the repository to https://niraluser.github.io/DTIPlayground/ on every change, with warnings failing the build
- The sdists of 0.7.26 - 0.8.0 carried three CSV files of a test run (StatsPlots_Clean) at their root; they are gone, and the folders those commands write by default are ignored

##### 2026-09-24 (v0.8.0)
- The same code as 0.7.30; the minor version marks the QC work of the 0.7.24 - 0.7.30 releases:
- dmriprep - QC_Report: image QC of the raw input and of the preprocessed image (neighboring DWI correlation, bad slices, b-table fiber coherence index), in the report, the QC_Report CSV and the batch QC table
- dmriprep - EDDYMOTION_Correct: the original gradient indexes survive eddy, so the per volume QC tables, the report labels and the gradients excluded afterwards refer to the input of the pipeline
- dmrifiberprofile - qc-profiles: reads the profiles of a run (00_EXTRACT_Profile) as well as gathered tables, and finds the prior stats of either; the locations sampled outside the brain are read as missing on every metric and written empty in the cleaned tables; a profile with less than --min-valid-frac (0.75) of its positions left is an outlier
- Ages come from one table of the cohort in qc-registration (--age-csv), qc-profiles (--age-csv) and the DTI_Register module of dmriprep (ageCSV), with the same columns, units and lookup order

##### 2026-09-24 (v0.7.30)
- dmrifiberprofile - qc-profiles: the age of a profile can come from a table of the cohort (--age-csv, with --age-column and --age-units), the same table as `qc-registration --age-csv` and the ageCSV of DTI_Register, for cohorts whose session names don't carry the age; --age-regex replaces the pattern read from the column names, and the run reports where the ages came from and which profiles have none

##### 2026-09-24 (v0.7.29)
- dmriprep - DTI_Register: the age that picks the bin of the normative model can come from a table of the cohort (protocol ageCSV, with ageColumn and ageUnits), the same table as `dmrifiberprofile qc-registration --age-csv`, for cohorts whose session names don't carry the age; the order is the protocol age, then the table, then ageRegex on the path

##### 2026-09-24 (v0.7.28)
- dmrifiberprofile - qc-profiles: --prior-stats-dir also finds the age bin stats of a run (`<metric>/<tract>_<metric>_agebinstats.csv`, the metric spelled as the run writes it); before, only the gathered layout was found and the profile QC silently skipped every table of such a folder

##### 2026-09-23 (v0.7.27)
- dmrifiberprofile - qc-profiles: --min-valid-frac defaults to 0.75 (was 0.5), so a profile that lost a quarter of its positions to locations outside the brain or to missing values is flagged

##### 2026-09-23 (v0.7.26)
- dmrifiberprofile - qc-profiles: with --clean-dir, the cells at the locations sampled outside the brain are written empty in the cleaned tables (on every metric of that tract and case) instead of keeping the zeros the QC ignored

##### 2026-09-23 (v0.7.25)
- dmrifiberprofile - qc-profiles: a profile location that a metric which cannot be 0 in tissue (FA, MD, RD, AD, NDI, ODI, ...) reports as 0 was sampled outside the brain mask, and is read as missing on every metric of that tract and case (--zero-valid-metrics, default FWF, where 0 is a valid measurement; --keep-outside-brain keeps them). Before, such a 0 counted as a measurement, and in a normative set it lowered the mean and widened the envelope
- dmrifiberprofile - qc-profiles: a profile with less than --min-valid-frac of its positions left is an outlier; before, a profile that was missing everywhere passed as clean because every comparison with it is undefined

##### 2026-09-23 (v0.7.24)
- dmriprep - QC_Report: image QC of the raw input and of the preprocessed image (IMAGE_QC.tsv, IMAGE_ndc.tsv, figure): neighboring DWI correlation (NDC, per shell), bad slices (corrupted slices and signal dropouts) and the fiber coherence index of the b-table, which names the b-vector axis whose sign would raise it; protocol options imageQC and bTableCheck
- dmriprep - QC_Report CSV and batch QC table include these numbers (raw_ / qced_); the batch report marks a low neighboring DWI correlation and many bad slices
- dmriprep - EDDYMOTION_Correct: the original gradient indexes were renumbered after eddy, so the original_index of EDDY_motion.tsv and DTI_fit.tsv, the labels of the QC report and the gradients excluded by a later module did not refer to the input of the pipeline once a volume had been excluded before eddy
- dmriprep - MANUAL_Exclude: the listed (original) indexes are logged with the volume they are at in the image, with a warning when an earlier module already excluded volumes or a listed one is gone
- dmrifiberprofile - qc-profiles: --profiles-dir also takes the profiles of a run as EXTRACT_Profile writes them (00_EXTRACT_Profile/<metric>/<tract>_<metric>.csv, either orientation), so gather is not needed to QC a single run; before, its tables were read as one tract named after the metric

##### 2026-09-19 (v0.7.23)
- dmriprep - DWI_Denoise: denoising with DIPY, MP-PCA (default, automatic patch size as QSIPrep) or Patch2Self; noise level map (MP-PCA) or residual map (Patch2Self), DENOISE_QC.tsv and a before/after figure
- dmriprep - GIBBS_Correct: Gibbs ringing removal with DIPY (full Fourier acquisitions), GIBBS_QC.tsv and a before/after figure. Neither module is in the default pipeline: put them first
- dmriprep - EDDYMOTION_Correct: per volume motion (EDDY_motion.tsv: framewise displacement, translations, rotations, outlier slices) and summary (EDDY_QC.tsv: mean/max FD, maximum motion, outlier slices, b=0 SNR and CNR per shell from eddy --cnr_maps, now also reported by eddy_quad); the RMS movement counts are relative to the previous volume (the report said the first)
- dmriprep - DTI_Estimate: tensor fit QC (DTI_fit.tsv, DTI_fit_QC.tsv): R2 and correlation of each volume with the tensor prediction, poorly fitted slices, carpet plot in the QC report
- dmriprep - QC_Report CSV and batch QC table include these summaries; the batch report marks unusual motion, outlier or poorly fitted slices and low fit R2
- dmriprep - QC_Report CSV: original_number_of_gradients was wrong when the result of the first module was reused

##### 2026-09-19 (v0.7.22)
- dmrifiberprofile: `run --atlas <folder>`; without tracts (e.g. without a protocol file) all the tracts of the atlas are profiled
- dmrifiberprofile - EXTRACT_Profile: supportBandwidth defaults to 3 mm (was 1 mm); cleanup defaults to noCleanup, and the profiles of a previous run are reused only if their settings and input files are unchanged (before, a changed bandwidth or reprocessed image could reuse stale profiles)
- dmrifiberprofile: the datasheet detection follows symbolically linked folders

##### 2026-09-19 (v0.7.21)
- dmrifiberprofile: `run -i <folder>` detects the datasheet from the files below the folder (case id: the part of the file names before `_dwi`; tensor and displacement field in native space, or registered tensor in atlas space, and the maps of the other properties), with an error listing the known file names when no scan matches; `make-datasheet` writes the detected datasheet only

##### 2026-09-19 (v0.7.20)
- dmriprep - batch processing: `dmriprep bids <bids_dir> <output_dir> participant|group` (BIDS-App interface; single runs, or pairs of runs with opposite phase encoding with the phase encoding axis and readout time of the sidecars for SUSCEPTIBILITY_Correct) and `dmriprep run-batch -m <datasheet>`; protocols per acquisition (`-p PATTERN=protocol.yml`) or default protocols (`-d`); local (`-j`) or SLURM job array (`--slurm`) execution; resuming, `batch-status`, cohort QC report and dmrifiberprofile datasheet (`group` / `batch-report`)
- dmriprep: the default pipeline of two images includes SUSCEPTIBILITY_Correct before EDDYMOTION_Correct
- dmriprep - SUSCEPTIBILITY_Correct: topup is recomputed when its inputs (b0s, acqp, configuration) changed; the outputs of a previous run were reused even with other parameters or image order

##### 2026-09-19 (v0.7.19)
- dmriprep - BRAIN_Mask: method hdbet, HD-BET deep learning brain extraction (Isensee et al. 2019) of the average b0 through the hd-bet command (install it in a separate Python environment and set hdbetPath; GPU if available); options hdbetDevice, hdbetTTA, hdbetPath
- dmriprep - BRAIN_Mask: method medianOtsu, dipy's median_otsu of the average b0 (no additional software); options medianOtsuRadius, medianOtsuNumpass, medianOtsuDilate
- relative input paths work on the first run after a version change (the initialization of the local configuration no longer changes the working directory)

##### 2026-09-19 (v0.7.18)
- dmriprep - BRAIN_Mask: method synthstrip, SynthStrip deep learning brain extraction (Hoopes et al. 2022) of the axial diffusivity (synthstripInput ad, default) or the average b0 (b0), with FreeSurfer's mri_synthstrip if found, otherwise a built-in torch version (identical masks; model weights downloaded on first use); options synthstripBorder, synthstripNoCSF, synthstripImplementation, synthstripPath

##### 2026-09-18 (v0.7.17)
- dmriprep - BRAIN_Mask: betFractionalThreshold sets the fractional intensity threshold of FSL bet (-f, default 0.5)

##### 2026-09-18 (v0.7.16)
- dmrifiberprofile - qc-registration: finds the outputs of the dmriprep DTI_Register module (<scan>_DTI_Registered.nrrd, <scan>_Registered_<METRIC>.nii.gz, in any folder below the data folder) besides AtlasReg/*_Deformed*; missing FA/MD/AD/RD maps are computed from the registered tensor

##### 2026-09-18 (v0.7.15)
- dmriprep - MULTI_SHELL_Estimate: DKI/MSDKI/FWDTI tensors were invalid (5D) NRRDs and the MSDKI kurtosis tensor was empty; new full DKI model (MK, AK, RK, MKT, KFA, kurtosis tensor); FWDTI saves the free water fraction; AMICO NODDI failed and now fits the output of the previous modules (NIfTI or NRRD input); mrtrix3 dwi2adc fixed; IVIM D* output renamed DSTAR

##### 2026-09-18 (v0.7.14)
- dmrifiberprofile - qc-registration: tensor directions in physical space from the NRRD headers; --tensor-flip uses the corrections of detect-tensor-flip (flips, voxel frame); every subject is checked on its own (TENSOR_frame_best, TENSOR_frame_gain_deg, warning when another correction fits the atlas better)

##### 2026-09-18 (v0.7.13)
- dmriprep - DTI_Estimate: dipy wrote an invalid (5D) tensor NRRD; dtiestim tensors were in the voxel frame (wrong on oblique or non-LPS grids), now rotated into the image space
- dmriprep - NIfTI images: geometry (oblique space directions, origin) and bvecs (FSL convention) are read and written correctly; results from NIfTI input, dtiestim on oblique grids and EDDYMOTION_Correct (bvecs given to eddy) of earlier versions should be recomputed (--overwrite)
- dmriprep - BASELINE_Average no longer fails when saving the gradients
- dmriprep - QC_Report labels the QCed DWIs with their original gradient index and keeps its full report.md

##### 2026-09-18 (v0.7.12)
- dmriprep - QC_Report CSV: original_number_of_gradients held the remaining count (now the count before the first module, plus a remaining_number_of_gradients column), number_of_excluded_gradients counts the exclusions of all modules (before only SLICE_Check and INTERLACE_Check), image_name is the input image
- dmrifiberprofile - qc-profiles uses remaining_number_of_gradients when present

##### 2026-09-18 (v0.7.11)
- dmriprep - rerunning into an existing output directory recomputes the modules whose protocol or command line global variables changed (stored in settings.yml), and the following ones; run / run-dir --overwrite recompute all modules
- dmriprep - global variables given with -g take precedence over those stored by a previous run
- dmriprep - DTI_Register: a tensor given as input image takes precedence over dti_path

##### 2026-09-18 (v0.7.10)
- dmrifiberprofile - flip-tensor --voxel-frame and detect-tensor-flip handle tensors whose components are in the frame of the voxel axes (estimated in voxel coordinates, header with another measurement frame): on oblique grids a rotation that no flip corrects
- dmriprep - DTI_Register: tensorFlip / tensor_flip accepts voxel (and voxel,<axes>); auto chooses among the flips in the header frame and in the voxel frame

##### 2026-09-18 (v0.7.9)
- dmrifiberprofile - detect-tensor-flip: finds the flip of the tensor frame (all combinations of x, y, z) that orients a DTI correctly, by the coherence of the principal directions along the tracts and their agreement with a reference tensor (registered, or with an affine transform)
- dmriprep - DTI_Register: tensorFlip / global variable tensor_flip (none, auto or axes) detects and applies a flip of the tensor frame before the registration

##### 2026-09-18 (v0.7.8)
- dmriprep - DTI_Register registers a diffusion tensor given as the input image (-i) directly, so a standalone run no longer needs -g dti_path
- requires dmri-amico>=2.1.1: version 2.1.0 imports pkg_resources, which newer setuptools no longer provide (ModuleNotFoundError: No module named 'pkg_resources')

##### 2026-09-17 (v0.7.7)
- dmriprep - global variables given on the command line (run -g key value ...) reach the modules again; they were discarded when the pipeline was created
- dmriprep - DTI_Register: reference image, normative model and age can be given as global variables (reference_dti, reference_normative_model, age), so the module runs with default protocols from one command line

##### 2026-09-17 (v0.7.6)
- dmriprep - DTI_Register: with a normative model of the reference atlas (referenceNormativeModel), the DTI is registered to the mean tensor of the age bin of the subject (age / ageRegex), so the registration target is age appropriate

##### 2026-09-17 (v0.7.5)
- dmriprep - DTI_Register: the displacement field is applied to all diffusion metrics in the folder of the input DTI (tensor images log-Euclidean with reorientation, scalar images linearly; options registerMetrics, metricExclude)

##### 2026-09-17 (v0.7.4)
- dmriprep - DTI_Register: defaults of the FiberAnalysis pipeline (ANTS iterations 100x50x20, CC radius 2, Gaussian sigma 1, transformation step 0.25, histogram matching, FA with abs tensor correction); initial affine computed with BRAINSFit (Rigid,Affine, center of head, sampling fraction 0.5, all configurable), read from a file, or none; WarpImageMultiTransform of the configured ANTs is used

##### 2026-09-17 (v0.7.3)
- dmrifiberprofile - EXTRACT_Profile: the fibers of each subject with the sampled values (one VTK file per subject, property and tract) are only written with the new option writeFiberFiles (default false); the profiles are unchanged

##### 2026-09-17 (v0.7.2)
- dmrifiberprofile - qc-registration --build-normative: per age bin also the mean/std/count images of every deformed metric map of the reference scans (FA, MD, RD, AD, ...) and the log-Euclidean mean tensor (DTI_mean.nrrd)

##### 2026-09-17 (v0.7.1)
- dmrifiberprofile - EXTRACT_Profile: with a DTI input, <prefix>FA, MD, AD, RD are computed from the tensors of the column mapped as '<prefix> DTI Image' (e.g. FWFA from free-water corrected tensors), other properties are sampled from their own image in the same run; an empty datasheet cell leaves that property out for the subject
- examples/normative_profiles - protocol, datasheet and datasheet script to compute the normative profiles of an atlas, sampling native tensors and maps with the deformation field of each scan

##### 2026-09-17 (v0.7.0)
- dmrifiberprofile - fiber profile analysis and QC tools (from FiberProfileAnalysis): flip-tensor, parametrize-fibers, compute-axis, gather, impute, qc-registration, qc-profiles; new dependencies torch, matplotlib, scikit-image, scikit-learn, scipy
- dmrifiberprofile - parametrize-fibers replaces dtitractstat -f: parametrized fibers store the arc lengths computed like EXTRACT_Profile
- dmrifiberprofile - EXTRACT_Profile option arcLength: stored arc lengths of parametrized tracts are used by default (computed for tracts without); compute-axis uses them too (--arc-source auto). Fibers parametrized by the C++ tools store different arc lengths and should be re-parametrized
- dmrifiberprofile - exits with the return code of the command; no crash when the configuration directory doesn't exist yet

##### 2026-09-16 (v0.6.0)
- dmrifiberprofile - fiber profile extraction reimplemented in Python (dtiplayground.dmri.common.fibers); fiberprocess, FiberPostProcess and dtitractstat are no longer needed
- dmrifiberprofile - DTI input: tensors are interpolated along the fibers (log-Euclidean by default, or linear as fiberprocess) and FA, MD, AD, RD computed from them; dtiprocess is no longer needed
- dmrifiberprofile - bugs of the C++ tools fixed, which changes profile values: scalar values assigned to the wrong fibers after removing fibers that don't cross the plane, arc length starting at a cosine, imprecise plane normal, 'median' plane crash, first subject processed with different options, empty parameterized fiber file, mask and noNaN options
- dmrifiberprofile - all subjects share the same arc length samples (multiples of the step size from the plane); points with NaN values are ignored; runs no longer fail at the end
- dmriprep - EDDYMOTION_Correct / SUSCEPTIBILITY_Correct: --nthr and --b_range only passed to FSL versions that support them (FSL 6.0.3 failed); new bRange option
- dmriprep - BRAIN_Tractography: reference tract voxelized in Python (failed with DWI input); pkg_resources removed
- dmriprep - thread count from the protocol, run-dir output base name, fractional b0 threshold
- dtiplayground - dependency version ranges (numpy < 2), Python 3.9 - 3.12, vtk dependency; Docker image on ubuntu 22.04; docker-compose rewritten

##### 2023-02-23
- dmriplaygroundlabs - Modern Web UI
- dmriplayground - installation, bug fixed
- dmriprep - minor bug fixed, antspynet removed
- dmriatlas - bug fixed, added directory build mode ($ dmriatlas build-dir [dir])

##### 2022-11-10
- dmriplayground - refactored, local-server mode enabled
- dmriprep - refactored
- dmriatlas - refactored

##### 2022-10-13
- dmriplayground - executable name dpg changed to dmriplayground (dtiplaground lab)
- dmriprep - minor bug fixed
- dmriatlas - minor bug fixed in using BRAINS (parameter error)
- dmriatlas - cropping image bug fixed
- dmriatlas - issue of external software : DTIReg doesn't generate inverse deformation field if BRAINS is selected

##### 2022-10-08

- dtiplayground - dpg server development initiated
- dtiplayground - readthedocs added [ReadTheDocs](https://dtiplayground.readthedocs.io)
- dtiplayground - official dockerhub repository [DTIPlayground](https://hub.docker.com/r/niraluser/dtiplayground)
- dmriprep - BRAIN_Tractography bug fixed

##### 2022-09-22
- dmriprep - Measurement frame bug fixed (inversion of measurement frame applied)
- dmriprep - BRAIN_Tractography_v2 : partial tractography with reference dti. Registration added

##### 2022-09-13
- dmriprep - v0.4.3b8
- dmriprep - Bug fixed : Affine matrix transposition bug fixed
- dmriprep - Memory usage: redundancy and inefficient memory management has been improved
- dmriprep - Dependency removal: fury is removed from dependency
- dmriprep - DTIPlayground tools installation without compile

##### 2022-08-19
- dmriprep - v0.4.1 Release
- dmriautotract - Initialized
- dmrifiberprofile - Initialized
- dmriatlas - name changed

##### 2022-08-16
- dmriprep - dwi module moved to common namespace (dtiplayground.dmri.common.dwi)

##### 2022-08-12
- dmriprep - add BRAIN_Tractography, DTI_Register and SINGLETRACT_Process in UI

##### 2022-08-11 (0.3.8b4)
- dmriprep - Bug fixed : Conversion between NRRD and NIFTI now includes space direction conversion as well as measurement frame
- dmriprep - Bug fixed : B value rounding issue resolved

##### 2022-08-10 (0.3.8b3)
- dmriprep - **New Module** BRAIN_Tractography module for generating a tractogram of the whole brain using DIPY

##### 2022-07-22
- dmriprep - Remove option to use ANTsPyNet in BRAIN_Mask module

##### 2022-07-08
- dmriprep - update QC_Report, pdf and csv outputs directly in output directory

##### 2022-07-06
- dmriprep - **New Module** DTI_Register module added for DTI registration (for tractography), it uses DTIReg with ANTS
- dmriprep - software path related enhancement, each module can access to software path information more intuitively using self.softwares variable
- dmriprep - yaml.dump replaced by yaml.safe_dump for potential exception handling

##### 2022-06-19
- dmriprep - module commands added. add-module, remove-module
- dmriprep - FSL installation
- dmriprep - global variables in .niral-dti directory storing global information such as FSL/DTIPlaygroundTools paths

##### 2022-06-17
- dmriprep - installation of dtiplayground tools
- dmriprep - software path generation modified for the tools

##### 2022-06-07
- dmriprep - Change EDDYMOTION_Correction parameters

##### 2022-06-03
- dmriprep - Bug fix in UI (Exclude gradients module with manual selection)

##### 2022-01-26
- dmriprep - Minor bug fix (conversion related)
- dmriprep - Intermediary files can be exported during computation (in module level)

##### 2021-12-10
- dmriprep **New Module** MANUAL_Exclude module added. It is a simple utility module that can exclude gradient volumes from an image with gradient indices from user input via protocols file.

##### 2021-12-08
- dmriprep - **New Module** DTI_Estimate module added with limited capability (only dtiestim is enabled)
- dmriprep - new option --no-output-image, if it's on, there will be no QCed outputfile (only use when there should be no output file. e.g. utilities such as BRAIN_Mask, DTI_Estimate)
- dmriprep - Intermediary files can be saved in output directory with user-specified postfix. e.g. (Module).addOutputFile(sourcefile, postfix). These stored files will be copied into project directory with filename changed with postfix.

##### 2021-11-10
- dmriprep - Singularity setup in slurm cluster
- dmriprep - removed system logging
- dmriprep - Nifti affine matrix orientation problem fixed.

##### 2021-09-02
- dmriprep - Only modules listed in the protocols will be loaded.
- dmriprep - BRAIN_Mask module added (use antspynet, fsl bet), only single file modalities (t2,fa) are available.
- dmriprep - Image orientation between Nrrd and Nifti issue are mostly cleared, however 4d Nifti in Slicer doesn't work properly. Need to look into the issue

##### 2021-08-24
- dmriprep - AntsPyNet library added for brain masking
- dmriprep - BRAIN_Mask module development initiated 

##### 2021-08-12
- dmriprep : change directory name for the merged output to 'combined' from 'consolidated'
- dmriprep : configuration directory will be provided to the protocol and submodules for reading configurations.
- dmriprep : threading issue is addressed. --num-threads will cap the maximum number of threads to be used in the process

##### 2021-07-15

- dmriprep : --num-threads option is added for users to control the resource allocation. 
- dmriprep : FSL wrapping 
- dmriprep : Eddymotion/susceptibility correction implemented with 2 modules (SUSCEPTIBILITY_Correct, EDDYMOTION_Correct)
- dmriprep : Multi image input is implemented for susceptibility correction (if susceptibility correction module is not in the protocol, the input images will be QCed independently)

##### 2021-06-8
- dmriprep : Multi input enabled both for multi processing and multi-input modules (such as susceptibility correction).

##### 2021-05-20
- dtiatlasbuilder : Threading bug fixed.
- dtiatlasbuilder : 1st refactoring is finished. 

##### 2021-05-14
- dtiatlasbuilder : ported to python3, refactoring

##### 2021-04-21
- dmriprep : Baseline average implemented (DirectAverage, BaselineOptimized)
- dmriprep : Optionalized pipeline implemented 
- dmriprep : dmriprep cli implemented
- dmriprep : initial configuration directory management (default $HOME/.niral-dti/dmriprep)
- dmriprep : Minor bug fixed

##### 2021-04-18
- dmriprep : Slicewise check implemented
- dmriprep : Interlace check implemented
- dmriprep : Continuation from stopped point has been implemented , but if image itself is deformed it won't work. It only has ability to track exclusion of gradients yet.
- dmriprep : Colored output is enabled with the logger. (dmriprep.Color.WARNING, dmriprep.Color.OK ... thingks like that look in __init__.py of dmriprep module)

##### 2021-04-15
- dmriprep : Sequential Pipelining implemented

##### 2021-04-09
- dmriprep : New protocol format (YAML)
- dmriprep : New protocol template (YAML)

##### 2021-04-01
- dmriprep : Deveopement initiated
