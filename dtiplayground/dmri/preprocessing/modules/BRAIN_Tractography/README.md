### BRAIN_Tractography

##### Introduction

BRAIN_Tractography.py is a code which helps to the treatment of the tracts observed in the white matter of the brain. It is based on the FSL software. It allows to extract the tracts from the brain and to visualize them

##### Protocol Parameters

- whiteMatterMaskThreshold is a list with a default value of manual, it will check the Manual threshold on FA to get a white matter mask of the brain

- thresholdLow is a number with a default value of 0.4, it will be the Lower value of threshold to apply on FA

- thresholdUp is a number with a default value of 0.98, it will be the Upper value of threshold to apply on FA

- maxBValue (default empty): the shells with a b-value above it are left out of the tensor fit of the tractography
  (the FA of the white matter mask and of the stopping criterion, the peaks of the tensor method); empty takes the
  maxBValue of DTI_Estimate (1600 without DTI_Estimate), so that the tracking uses the tensor of the DTI maps; 0 uses
  all the shells. The CSA and OPDT methods use all the shells

- Tensor output: with DTI_Estimate in the protocol, its tensor is the DTI output (`<name>_DTI.nrrd`, global variable
  `dti_path`) and the tensor of the tracking isn't written. Without it, the tensor of the tracking is (components
  first, rotated into the space of the image). Before 0.9.6 the module always wrote its own tensor, which replaced the
  one of DTI_Estimate as the DTI output, fitted on all the shells and with its components in the frame of the voxel
  axes while the header gave the measurement frame of the image (misoriented by the obliquity of the image)

- method is a list with a default value of tensor, it will choose the Method used to generate the peaks used to generate the streamlines between different methods like CSA model, OPDT model or DTI tensor model

- shOrder is a number with a default value of 2, it will be the sh order used for peak generation model

- relativePeakThreshold is a number with a default value of 0.9, it will be the Only keeps peaks greater than relativePeakThreshold * m where m is the largest peak

- minPeakSeparationAngle is a number with a default value of 25, it will be the The minimum distance between directions. If two peaks are too close only the larger of the two is returned. It will return a number between 0 and 90

- stoppingCriterionThreshold is a number with a default value of 0.3, it will be the Threshold on FA to stop tracts

- vtk42 is a boolean with a default value of False, it will check the Save output tractogram in VTK format 4.2 (instead of 5.0)

- removeShortTracts is a boolean with a default value of False, it will check the Remove short tracts from tractogram

- shortTractsThreshold is a number with a default value of 100, it will be the Minimal length for tracts to be conserved

- removeLongTracts is a boolean with a default value of False, it will check the Remove long tracts from tractogram

- longTractsThreshold is a number with a default value of 100, it will be the Maximal length for tracts to be conserved

For single tract : 

- referenceTractFile is a string with a default value of null, it will be the Path of the reference tract file (.vtk)

- displacementFieldFile is a string with a default value of null, it will be the Path of the displacement file for transform

- dilationRadius is a number with a default value of 2, it will be the Dilation radius

##### Examples


##### Author(s)

