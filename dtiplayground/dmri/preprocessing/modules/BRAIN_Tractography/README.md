### BRAIN_Tractography

##### Introduction

BRAIN_Tractography.py is a code which helps to the treatment of the tracts observed in the white matter of the brain. It is based on the FSL software. It allows to extract the tracts from the brain and to visualize them

##### Protocol Parameters

- whiteMatterMaskThreshold is a list with a default value of manual, it will check the Manual threshold on FA to get a white matter mask of the brain

- thresholdLow is a number with a default value of 0.4, it will be the Lower value of threshold to apply on FA

- thresholdUp is a number with a default value of 0.98, it will be the Upper value of threshold to apply on FA

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

