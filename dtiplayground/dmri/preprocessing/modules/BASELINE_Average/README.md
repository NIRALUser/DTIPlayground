### BASELINE_Average

##### Introduction

BASELINE_Average.py will average the baseline scans of a subject. The baseline scans are defined as the first scans of each session. The baseline scans are averaged and saved as a new baseline scan. The new baseline scan is saved in the same directory as the original baseline scan

##### Protocol Parameters


- averageMethod: 
        type: list 
        caption: Average Method
        candidates:
          - value: DirectAverage
            caption: Direct Averaging
            description: Direct Averaging over baseline images 
          - value: BSplineOptimized
            caption: B-Spline Optimized Averaging
            description: NOT IMPLEMENTED
          - value: BaselineOptimized
            caption: Baseline Optimized Averaging
            description: Baseline  optimized averaging. Average initial baselines and use the averaged one to register baselines and repeat the process until it converge
          # ...
        default_value: BaselineOptimized # from prep v1
        description: Averaging method for the baselines
      averageInterpolationMethod: 
        &interpolation_methods
        type: list 
        caption: Interpolation Method
        candidates:
          - value: &ba_linear_interpolation linear-interpolation
            caption:  Linear Interpolation
            description: Linear Interpolation will be used in averaging
          - value: &ba_bspline_interpolation bspline-interpolation
            caption: B Spline Interpolation
            description: B Spline Interpolation will be used in averaging
          - value: &ba_windowedsinc_interpolation ba_windowedsinc_interpolation
            caption: Windowed Sinc Interpolation
            description: Windowed sinc interpolation will be used in averaging
        default_value: *ba_linear_interpolation  #shd change
        description: Reserverd for future use. Currently not being used
      stopThreshold: 
        type: float
        caption: Stop Threshold
        default_value: 0.02 #0.0200
        description: stopping threshold for the averaging process (previously averaged baseline versus currently averaged baseline)
      maxIterations: 
        type: integer
        caption: Maximum iteration
        default_value: 2
        description: Maximum number of iterations for which affine registration of baselines are performed
      outputDWIFileNameSuffix: 
        type: string 
        caption: Suffix for the Output DWI Filename
        default_value: null
        description: Output DWI file suffix to the original image filename 

##### Examples


##### Author(s)


- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
- Timothée Teyssier - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
