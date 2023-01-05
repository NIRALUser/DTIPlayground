### IMAGE_Filter

##### Introduction

IMAGE_Filter.py will filter your image by b-values, you can for example filter between two b-values (b_lower and b_upper) or above, or below a certain b-value.

##### Protocol Parameters

- tresholding_mode is a string with a default value of one_treshold_below, it will choose the tresholding mode. The options are one_treshold_below, one_treshold_above, two_tresholds_within, two_tresholds_outside.

- b_tresh is a float with a default value of 1500, it will choose the b-value treshold for the one_treshold_below and one_treshold_above modes.

- b_lower is a float with a default value of 0, it will choose the lower b-value treshold for the two_tresholds_within and two_tresholds_outside modes.

- b_upper is a float with a default value of 1500, it will choose the upper b-value treshold for the two_tresholds_within and two_tresholds_outside modes.


##### Examples


##### Author(s)

