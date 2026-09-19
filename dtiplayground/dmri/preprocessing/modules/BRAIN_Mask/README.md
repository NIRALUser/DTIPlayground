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

- method hdbet: HD-BET deep learning brain extraction (Isensee et al., Human Brain Mapping 2019,
  https://github.com/MIC-DKFZ/HD-BET), run through its `hd-bet` command. hd-bet (2.x) needs numpy 2 and nnunetv2, so
  install it in a separate Python environment (`python -m venv hdbet-env; hdbet-env/bin/pip install hd-bet`) and set
  hdbetPath; the model weights are downloaded to `~/hd-bet_params` on first use. HD-BET is applied to the average of
  the baseline (b=0) images (it is trained on structural images; on the AD map it includes background noise)
  - hdbetDevice: `auto` (default) uses the GPU if the torch of the hd-bet environment sees one, otherwise the CPU;
    `cuda` or `cpu` force one
  - hdbetTTA (default true): test time augmentation; disabling it (`--disable_tta`) is faster, mainly on CPU
  - hdbetPath: path of `hd-bet`, or of the Python environment (or its bin directory) it is installed in; if empty, the
    environment of dtiplayground and the PATH are searched

- method medianOtsu: dipy's `median_otsu`, a median filter followed by an Otsu threshold of the average of the
  baseline (b=0) images (all volumes if there is none); no additional software needed
  - medianOtsuRadius (default 4): radius in voxels of the median filter
  - medianOtsuNumpass (default 4): number of median filter passes
  - medianOtsuDilate (default 0): binary dilation iterations applied to the mask

- modality is a list with a default value of t2, it will choose the Modality of the input image between two methods : t2 or fa

##### Examples


##### Author(s)

