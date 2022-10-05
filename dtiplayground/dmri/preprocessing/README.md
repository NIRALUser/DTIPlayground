# Prepocessing

The Preprocessing module contains a lot of modules that are used to preprocess the data.

## Modules

- BASELINE_AVERAGE : will average the baseline scans of the subject. The baseline scans are defined as the first scans of each session. The baseline scans are averaged and saved as a new baseline scan.
[ReadMe for this module](modules/BASELINE_Average/README.md)
- BRAIN_Mask : will create a brain mask for the subject.
[ReadMe for this module](modules/BRAIN_Mask/README.md)
- BRAIN_Tractography : will help to the treatment of the tracts observed in the white matter of the brain. It is based on the FSL software.
[ReadMe for this module](modules/BRAIN_Tractography/README.md)
- DTI_Estimate : will run DTI by several methods like : runDTI, runDTI_DIPY, runDTI_dtiestim.
[ReadMe for this module](modules/DTI_Estimate/README.md)
- DTI_Register :  will allow to register the DTI images. It is based on the ANTs software.
[ReadMe for this module](modules/DTI_Register/README.md)
- EDDYMOTION_Correc : will correct the eddy current distortion in the DTI images.
[ReadMe for this module](modules/EDDYMOTION_Correct/README.md)
- IDENTITY_Process : will assure a identity process of the input image.
[ReadMe for this module](modules/IDENTITY_Process/README.md)
- INTERLACE_Check : will help to the treatment between slices by rule out weird volumes with statistical conditions.
[ReadMe for this module](modules/INTERLACE_Check/README.md)
- MANUAL_Exclude : will exclude false or weird gradients from the diffusion images.
[ReadMe for this module](modules/MANUAL_Exclude/README.md)
- QC_Report : will generate a report of the quality control.
[ReadMe for this module](modules/QC_Report/README.md)
- SLICE_Check : will check problematic slices in the diffusion images and will exclude them from the image.
[ReadMe for this module](modules/SLICE_Check/README.md)
- SUSCEPTIBILTY_Correct : will correct the susceptibility distortion in the DTI images.
[ReadMe for this module](modules/SUSCEPTIBILITY_Correct/README.md)
- TEST : will launch all the tests for the different images, results.
[ReadMe for this module](modules/TEST/README.md)
- UTIL_Header : will show image headers.
[ReadMe for this module](modules/UTIL_Header/README.md)
- UTIL_Merge : will merge 2 images to one image.
[ReadMe for this module](modules/UTIL_Merge/README.md)