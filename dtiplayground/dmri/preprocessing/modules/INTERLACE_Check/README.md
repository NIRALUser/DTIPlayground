### INTERLACE_Check

##### Introduction

INTERLACE_Check.py will help to the treatment between slices by rule out weird volumes with statistical condition

##### Protocol Parameters

- protocol:
      correlationThresholdBaseline: 
        type: float
        caption: Correlation Threshold For the Baselines
        default_value: 0.9500
        description: TBD
      correlationThresholdGradient: 
        type: float
        caption: Correlation Threshold for the Gradients
        default_value: 0.7702
        description: TBD
      correlationDeviationBaseline: 
        type: float
        caption: Correlation Deviation for the Baselines
        default_value: 2.5000
        description: TBD
      correlationDeviationGradient: 
        type: float
        caption: Correlation Deviation for the Gradients
        default_value: 3.0000
        description: TBD
      translationThreshold: 
        type: float
        caption: Translation Threshold
        default_value: 1.5000
        description: TBD
      rotationThreshold: 
        type: float
        caption: Rotation Threshold
        default_value: 0.5000
        description: TBD

##### Examples


##### Author(s)

- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
- Timothée Teyssier - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
