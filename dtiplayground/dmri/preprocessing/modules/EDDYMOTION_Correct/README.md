### EDDYMOTION_Correct

##### Introduction
EDDYMOTION_Correct.py helps to correct the EDDY motion artefacts in the diffusion images

After SUSCEPTIBILITY_Correct, eddy applies the field of topup and refines it. This is why a baseline-only image is removed at the end of this module and not after topup, see `stripBaselineOnlyImage` of SUSCEPTIBILITY_Correct. The number of volumes removed is written to `stripped_volumes.txt` in the module's folder.

Eddy doesn't run again as long as `output_eddied.nii.gz` is in the module's folder, also with `--overwrite`: delete the folder to recompute it.

##### Protocol Parameters

- estimateMoveBySusceptibility is a boolean parameter with a default value of True that indicates if the move will be estimated by susceptibility

- interpolateBadData is a boolean parameter with a default value of True that indicates if the bad data will be interpolated

- dataIsShelled is a boolean parameter with a default value of True that indicates if the data is shelled

- qcReport is a boolean parameter with a default value of False that generates a QC report from FSL

##### Examples


##### Author(s)

