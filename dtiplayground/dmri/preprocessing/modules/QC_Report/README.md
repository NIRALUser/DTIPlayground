### QC_Report

##### Introduction

QC_Report will generate a report of the Quality Control treatment

It also compares the raw input of the pipeline with the preprocessed image (image QC), so that the effect of the
preprocessing can be read off one table.

##### Protocol Parameters

- generatePDF is a boolean parameter that indicates if the PDF report will be generated

- generateCSV is a boolean parameter that indicates if the CSV report will be generated

- imageQC is a boolean parameter that indicates if the image QC is computed on the raw input and on the preprocessed
  image (neighboring DWI correlation and bad slices)

- bTableCheck is a boolean parameter that adds the fiber coherence index of the b-table to the image QC; it needs a
  tensor fit of each image

##### Outputs

Besides the report (`QC_report.pdf`, `QC_report.csv`), with `imageQC`:

- `<base>_IMAGE_QC.tsv` : one row, the numbers of the raw input (`raw_`) and of the preprocessed image (`qced_`)
  - `ndc` : neighboring DWI correlation (as DSI Studio), the correlation inside the brain mask between each volume and
    the volume of the same shell whose gradient direction is the closest; `ndc_b<shell>` per shell
  - `bad_slices`, `bad_slices_percent`, `bad_slice_volumes` : slices whose correlation with the slice below it, or
    whose mean intensity relative to the median slice of the volume, is more than 3.5 scaled MADs below the same slice
    position in the other volumes of the shell. The correlation finds a corrupted slice, the intensity a signal
    dropout (the normalized correlation doesn't change when a slice is scaled down). They are only counted here, no
    volume is excluded (that is SLICE_Check)
  - `coherence`, `coherence_best`, `coherence_best_flip` (with `bTableCheck`) : fiber coherence index of the b-table
    (Schilling et al. 2019), how well the principal direction of a tensor fit continues into the neighboring voxel it
    points at. It is computed for the b-vectors as given and with the sign of one axis flipped; `coherence_best_flip`
    is `none` when the b-table as given is the most coherent, and names the suspect axis otherwise
- `<base>_IMAGE_ndc.tsv` : per volume (stage, volume, original index, b-value, neighbor, correlation, bad slices)
- `<base>_IMAGE_QC_plot.png` : both stages at their original volume index (in the report)

The summary is also written to the QC_Report CSV and to the batch QC table (`dmriprep batch-report`), which marks a
low `qced_ndc` and a high `qced_bad_slices` compared to the rest of the cohort.

##### Examples


##### Author(s)

