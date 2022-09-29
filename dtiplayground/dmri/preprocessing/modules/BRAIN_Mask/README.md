### BRAIN_Mask

##### Introduction

BRAIN_Mask.py create a mask by two defined methods, by antspynet, or by fslbet and then apply the mask to the DWI image

##### Protocol Parameters

- method is a list with a default value of fsl, it will choose the Method to extract the brain between two methods : fsl or antspynet

- averagingMethod is a list with a default value of idwi, it will choose the Averaging method by which the source image is generated for the mask between two methods : direct_average or idwi

- modality is a list with a default value of t2, it will choose the Modality of the input image between two methods : t2 or fa

##### Examples


##### Author(s)

