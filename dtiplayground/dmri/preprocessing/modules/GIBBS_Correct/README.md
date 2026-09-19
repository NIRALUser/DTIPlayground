### GIBBS_Correct

##### Introduction

Removes Gibbs ringing with DIPY (local subvoxel shifts, Kellner et al. 2016, the method of MRtrix `mrdegibbs`), slice by
slice in the plane of acquisition. The method is meant for full Fourier acquisitions; with partial Fourier it removes
only part of the ringing. Use it after DWI_Denoise and before any interpolation (EDDYMOTION_Correct,
SUSCEPTIBILITY_Correct, BASELINE_Average).

##### Protocol Parameters

- sliceAxis: voxel axis (0, 1 or 2) along which the slices were acquired; 2 (default) for the usual axial acquisitions.
- nPoints: number of neighbour points used to find the subvoxel shift with the least ringing (default 3).

The module uses the number of threads of the configuration (num_max_threads).

##### Outputs

- The corrected image (float) for the next module.
- `gibbs_qc.tsv` (`<base>_GIBBS_QC.tsv`): mean absolute change in the brain, in % of the mean intensity.
- `gibbs.png`: middle slice of a b=0 and of a highest shell volume, before, after and their difference (also in the
  module report and QC_Report).
