### EDDYMOTION_Correct

##### Introduction
EDDYMOTION_Correct.py helps to correct the EDDY motion artefacts

##### Protocol Parameters

- protocol:
      # susceptibilityCorrection:
      #   type: boolean
      #   caption: Susceptibility Correction
      #   default_value: False 
      #   description: Correcting susceptibility motion, SUSCEPTIBILITY_Correct module is required to be performed before EDDY 
      estimateMoveBySusceptibility:
        type: boolean
        caption: Estimate move by susceptibility
        default_value: True
        description: Estimate move by susceptibility
      interpolateBadData:
        type: boolean
        caption: Interpolate bad data
        default_value: True
        description: Interpolate bad data (--repol)
      dataIsShelled:
        type: boolean
        caption: Data is shelled
        default_value: True
        description: If the data is shelled, check this to be true
      qcReport:
        type: boolean
        caption: Generate QC report
        default_value: False
        description: Generate QC report from FSL

##### Examples


##### Author(s)

- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
- Timothée Teyssier - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
