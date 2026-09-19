### BRAIN_Mask

##### Introduction

BRAIN_Mask.py create a mask by two defined methods, by antspynet, or by fslbet and then apply the mask to the DWI image

##### Protocol Parameters

- method is a list with a default value of fsl, it will choose the Method to extract the brain between two methods : fsl or antspynet

- averagingMethod is a list with a default value of idwi, it will choose the Averaging method by which the source image is generated for the mask between two methods : direct_average or idwi

- betFractionalThreshold (method fsl) is a float with a default value of 0.5, the fractional intensity threshold of FSL bet (-f, between 0 and 1): smaller values give a larger brain outline, larger values a smaller one

- method synthstrip: SynthStrip deep learning brain extraction (Hoopes et al., NeuroImage 2022, https://synthstrip.io)
  - synthstripInput: `ad` (default), the axial diffusivity of a DTI fit (WLS) of the image, using the diffusion weighted
    volumes up to b=1500 when there are any; or `b0`, the average of the baseline (b=0) images
  - synthstripBorder (default 1.0): mask border threshold in mm (`mri_synthstrip -b`); larger values give a larger mask
  - synthstripNoCSF (default false): exclude the CSF from the brain border (`--no-csf`)
  - synthstripImplementation: `auto` (default) runs FreeSurfer's `mri_synthstrip` (FreeSurfer 7.3+) when it is found
    (synthstripPath, `$FREESURFER_HOME` or the PATH) and otherwise the built-in version; `freesurfer` or `builtin` force
    one. The built-in version runs the SynthStrip network with torch (same preprocessing, identical masks) and downloads
    the model weights (MIT / CC BY 4.0) to `~/.niral-dti/models/synthstrip` on first use
  - synthstripPath: FreeSurfer home directory or path of `mri_synthstrip`

- modality is a list with a default value of t2, it will choose the Modality of the input image between two methods : t2 or fa

##### Examples


##### Author(s)

