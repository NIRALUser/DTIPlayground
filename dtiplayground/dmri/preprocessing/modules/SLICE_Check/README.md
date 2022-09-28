### SLICE_Check

##### Introduction

SLICE_Check.py will check problematic slices in the diffusion images and will exclude them from the image
 
##### Protocol Parameters

- bSubregionalCheck is a boolean with a default value of false, it will check all the subregional slices

- subregionalCheckRelaxationFactor is a float with a default value of 1.10, it will check the relaxation factor of the subregional slices

- checkTimes is an integer with a default value of 0, it will check the number of times the slice is problematic

- headSkipSlicePercentage is a float with a default value of 0.10, it will skip the first 10% of the slices

- tailSkipSlicePercentage is a float with a default value of 0.10, it will skip the last 10% of the slices

- correlationDeviationThresholdbaseline is a float with a default value of 3.0, it will check the correlation's deviation threshold of the baseline

- correlationDeviationThresholdgradient is a float with a default value of 3.5, it will check the correlation's deviation threshold of the gradients

- quadFit is a boolean with a default value of True, it will check the quadratic fit of the stdev multiple between the baseline and the gradients
##### Examples


##### Author(s)

