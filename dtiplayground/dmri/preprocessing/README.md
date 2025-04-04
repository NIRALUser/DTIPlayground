# Prepocessing

The Preprocessing module contains a lot of modules that are used to preprocess the data.

## Modules

- BASELINE_AVERAGE : will average the baseline scans of the subject. The baseline scans are defined as the first scans of each session. The baseline scans are averaged and saved as a new baseline scan.
[ReadMe about the module BASELINE_Average](modules/BASELINE_Average/README.md)
- BRAIN_Mask : will create a brain mask for the subject.
[ReadMe about the module BRAIN_Mask](modules/BRAIN_Mask/README.md)
- BRAIN_Tractography : will help to the treatment of the tracts observed in the white matter of the brain. It is based on the FSL software.
[ReadMe about the module BRAIN_Tractography](modules/BRAIN_Tractography/README.md)
- DTI_Estimate : will run DTI by several methods like : runDTI, runDTI_DIPY, runDTI_dtiestim.
[ReadMe about the module DTI_Estimate](modules/DTI_Estimate/README.md)
- DTI_Register :  will allow to register the DTI images. It is based on the ANTs software.
[ReadMe about the module DTI_Register](modules/DTI_Register/README.md)
- EDDYMOTION_Correc : will correct the eddy current distortion in the DTI images.
[ReadMe about the module EDDYMOTION_Correct](modules/EDDYMOTION_Correct/README.md)
- IDENTITY_Process : will assure a identity process of the input image.
[ReadMe about the module IDENTITY_Process](modules/IDENTITY_Process/README.md)
- INTERLACE_Check : will help to the treatment between slices by rule out weird volumes with statistical conditions.
[ReadMe about the module INTERLACE_Check](modules/INTERLACE_Check/README.md)
- MANUAL_Exclude : will exclude false or weird gradients from the diffusion images.
[ReadMe about the module MANUAL_Exclude](modules/MANUAL_Exclude/README.md)
- QC_Report : will generate a report of the quality control.
[ReadMe about the module QC_Report](modules/QC_Report/README.md)
- SLICE_Check : will check problematic slices in the diffusion images and will exclude them from the image.
[ReadMe about the module SLICE_Check](modules/SLICE_Check/README.md)
- SUSCEPTIBILTY_Correct : will correct the susceptibility distortion in the DTI images.
[ReadMe about the module SUSCEPTIBILITY_Correct](modules/SUSCEPTIBILITY_Correct/README.md)
- TEST : will launch all the tests for the different images, results.
[ReadMe about the module TEST](modules/TEST/README.md)
- UTIL_Header : will show image headers.
[ReadMe about the module UTIL_Header](modules/UTIL_Header/README.md)
- UTIL_Merge : will merge 2 images to one image.
[ReadMe about the module UTIL_Merge](modules/UTIL_Merge/README.md)
- MULTI_SHELL_Estimate : will run DTI by several methods like : runDIPY, runMRTRIX3, runAMICCO.
[ReadMe about the module MULTI_SHELL_Estimate](modules/MULTI_SHELL_Estimate/README.md)