### BRAIN_Mask

##### Introduction

BRAIN_Mask.py create a mask by two defined methods, by antspynet, or by fslbet

##### Protocol Parameters

- protocol:
      method: 
        type: list
        caption: Method
        candidates:
          - value: fsl
            caption: FSL
            description: Use FSL for Brainmasking
          - value: antspynet
            caption: AntsPyNet
            description: AntsPyNet's brain_extraction() method 
        default_value: fsl
        description: Method to extract the brain 
      averagingMethod:
        type: list
        caption: Average Method
        default_value: idwi
        description: Averaging method by which the source image is generated for the mask
        candidates:
          - value: direct_average
            caption: Direct Average
            description: Direct average on baseline images. If no baseline is found then average whole volume
          - value: idwi
            caption: IDWI
            description: Geometric mean of baseline images. If no baseline is found then whole images will be used.
      modality: ## in case of antspynet
        type: list
        candidates:
          - value: t2
            caption: T2
            description: T2 Modality 
          - value: fa
            caption: FA
            description: Fractional Anistropy
        default_value: t2
        description: Modality of the input image

##### Examples


##### Author(s)

- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
- Timothée Teyssier - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France
