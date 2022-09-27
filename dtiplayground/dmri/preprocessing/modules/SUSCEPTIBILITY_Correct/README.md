### SUSCEPTIBILITY_Correct

##### Introduction

SUSCEPTIBILITY_Correct.py will correct all the susceptiblity artefacts due to the local magnetical field

##### Protocol Parameters

- protocol:
      phaseEncodingAxis: 
        type: list
        caption: 0 - rl, 1 - ap(fh), 2  - si 
        default_value: 
          - 1
        description: Phase encoding axis (list of axis index of phase encoding (0,1,2))
      phaseEncodingValue: 
        type: float
        caption: Phase Encoding Value 
        default_value: 0.0924
        description: Phase encoding value (real number)
      configurationFilePath: 
        type: string
        caption: FSL topup configuration file path 
        default_value: $CONFIG_DIR/parameters/fsl/fsl_regb02b0.cnf 
        description: FSL topup configuration file path 

##### Examples


##### Author(s)

- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
- Timothée Teyssier - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
