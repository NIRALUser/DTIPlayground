### BASELINE_Average

##### Introduction

BASELINE_Average.py will average the baseline scans of a subject. The baseline scans are defined as the first scans of each session. The baseline scans are averaged and saved as a new baseline scan. The new baseline scan is saved in the same directory as the original baseline scan

##### Protocol Parameters

- averageMethod is a list with a default value of BaselineOptimized, it will choose the Average method by which the baseline images are averaged between three methods : DirectAverage, BSplineOptimized, BaselineOptimized

- averageInterpolationMethod is a list with a default value of linear-interpolation, it will choose the Interpolation method by which the baseline images are averaged between three methods : linear-interpolation, bspline-interpolation, ba_windowedsinc_interpolation

- stopThreshold is a float with a default value of 0.02, it will choose the threshold for the averaging process

- maxIterations is an integer with a default value of 2, it will choose the maximum number of iterations for which affine registration of baselines are performed

- outputDWIFileNameSuffix is a string with a default value of null, it will choose the suffix for the output DWI filename

##### Examples


##### Author(s)

