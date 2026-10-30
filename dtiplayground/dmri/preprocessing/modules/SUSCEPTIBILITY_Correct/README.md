### SUSCEPTIBILITY_Correct

##### Introduction

SUSCEPTIBILITY_Correct.py will correct all the susceptiblity artefacts due to the local magnetical field in the diffusion images by using the FSL's method

##### Protocol Parameters

- phaseEncodingAxis is a list of axis index of phase encoding, its default value is 1 

- phaseEncodingValue is a float, its default value is 0.0924, it characterizes the phase encoding value

- configurationFilePath is a string with the default value of $CONFIG_DIR/parameters/fsl/fsl_regb02b0.cnf, it is the file path of the FSL topup configuration 

- stripBaselineOnlyImage is a boolean, its default value is true. When only one of the images is a full DWI and the other one was acquired for topup (baselines, and at most one dummy volume that isn't a baseline, as scanners have no sequence with baselines only), its volumes are removed at the end of EDDYMOTION_Correct, which uses them to refine the correction. The result has the full DWI only and starts with a baseline; the following modules never see the stripped volumes. With two full DWIs nothing is removed, and without EDDYMOTION_Correct in the pipeline neither

##### Examples


##### Author(s)

