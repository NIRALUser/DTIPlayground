# Normative profiles of an atlas

Example protocol and datasheet to compute the normative profiles (`normProfiles`) of the DTI_IBISEP_Feb26 atlas from
its reference dataset: the profiles of all reference scans, and their statistics per age bin.

| File | Content |
|---|---|
| `protocol.yml` | EXTRACT_Profile protocol: FA, MD, AD, RD, FWFA, FWMD, FWAD, FWRD, FWF, NDI, ODI |
| `reference.csv` | Datasheet for `protocol.yml` (3 example rows) |
| `make_datasheet.py` | Writes the datasheet of all scans from the reference dataset folders |

## Sampling in native space

The fibers of the atlas are mapped to each scan with its deformation field (`useDisplacementField: true`), and the
images are sampled in the native space of the scan. The tensors are therefore not deformed to the atlas, which would
need a reorientation model; images already deformed to the atlas (`AtlasReg/*_DeformedDTI.nrrd`) are not used.

| Metrics | Source (datasheet column) | Sampling |
|---|---|---|
| FA, MD, AD, RD | `DTI`: `mask/<scan>_dwi_QCed_tensor.nrrd` | tensors interpolated along the fibers (log-Euclidean), metrics computed from them |
| FWFA, FWMD, FWAD, FWRD | `FW DTI`: `mask/<scan>_dwi_QCed_FWtensor.nrrd` (free-water corrected tensor) | same as DTI |
| FWF, NDI, ODI | `FWF`, `NDI`, `ODI`: `mask/<scan>_dwi_QCed_NODDI_<metric>.nii.gz` | scalar maps interpolated along the fibers |
| (all) | `Deformation field`: `AtlasReg/<scan>_dwi_QCed_tensor_DeformedDTI_GlobalDisplacementField.nrrd` | maps the atlas fibers to the scan |

In the protocol, `parameterToColumnHeaderMap` gives the column of each source. The tensor metrics with a prefix (FWFA, ...)
are computed from the tensor column mapped as `<prefix> DTI Image` (here `FW DTI Image`). The file names are those
written by `dti_analysis.py` (FiberProfileAnalysis); adapt the paths if your files are named differently. FWF is the
NODDI free-water fraction; use `<scan>_dwi_QCed_FWf.nii.gz` for the fraction of the free-water DTI model instead.

Free water and NODDI need multi-shell data. For scans without them, leave the cells empty: EXTRACT_Profile then only
profiles FA, MD, AD, RD for these scans, and their cells stay empty in the gathered tables of the other metrics.

## Other requirements

- **Case ids** contain the age as `ses-<months>m`; `qc-profiles` bins the profiles by age with it. The ids here are the
  scan names (`sub-011228_ses-012m_acq-dir79select_dir_run-001`), so a session with two scans gives two profiles.
- **Parametrized fibers**: `atlas` is the folder written by `parametrize-fibers`; with `arcLength: stored` all profiles
  use the arc lengths stored in the fibers.

Change the paths (`atlas` in the protocol, the image paths in the datasheet) for your system.

## Steps

```
A=/tools/atlas/DTI/DTI_IBISEP_Feb26

## 1. parametrized fibers (once per atlas)
dmrifiberprofile parametrize-fibers $A/FibersRaw -o $A/FibersParam_dtiplayground

## 2. datasheet of all reference scans
python make_datasheet.py $A/ReferenceDataset -o reference.csv \
    --column "DTI=mask/*_dwi_QCed_tensor.nrrd" \
    --column "Deformation field=AtlasReg/{id}_dwi_QCed_tensor_DeformedDTI_GlobalDisplacementField.nrrd" \
    --optional-column "FW DTI=mask/{id}_dwi_QCed_FWtensor.nrrd" \
    --optional-column "FWF=mask/{id}_dwi_QCed_NODDI_FWF.nii.gz" \
    --optional-column "NDI=mask/{id}_dwi_QCed_NODDI_NDI.nii.gz" \
    --optional-column "ODI=mask/{id}_dwi_QCed_NODDI_ODI.nii.gz"

## 3. profiles
dmrifiberprofile run -i reference.csv -p protocol.yml -o ReferenceProfiles

## 4. one table per tract and metric, then the age-bin statistics
dmrifiberprofile gather --profiles-dir ReferenceProfiles --fibers-dir $A/FibersParam_dtiplayground --out-dir normProfiles
dmrifiberprofile qc-profiles --profiles-dir normProfiles --plots-dir normProfiles_plots
```

In `make_datasheet.py`, the first `--column` defines the scans and the case id (the file name before `_dwi`). `{id}` in
the other patterns is replaced by the case id, so each file is matched to its own scan. Scans without exactly one file
for a `--column` are left out and listed; `--optional-column` cells are left empty when there is no file.

`qc-profiles` writes `normProfiles/<tract>/<tract>_<metric>_agebinstats.csv` (age bins 0-3, 4-9, 10-60 months; `--bins`)
next to the gathered tables `<tract>_<metric>.csv`. Use `normProfiles` as `--prior-stats-dir` for the profile QC of
new datasets. The DTI metrics are written in lower case (`fa`, `md`, `ad`, `rd`), the others keep their names.

## Docker

Mount the atlas and the data at the same paths as in the datasheet, and run the commands with the `dmrifiberprofile`
entrypoint. The protocol, the datasheet and the output folder must be inside a mounted folder too (here the current
folder under `$HOME`):

```
docker run --rm -it -u $(id -u):$(id -g) -e HOME=$HOME -v $HOME:$HOME -w $PWD \
    -v /tools/atlas/DTI/DTI_IBISEP_Feb26:/tools/atlas/DTI/DTI_IBISEP_Feb26 \
    --entrypoint dmrifiberprofile niraluser/dtiplayground:0.7.2 \
    run -i reference.csv -p protocol.yml -o ReferenceProfiles
```

`make_datasheet.py` only needs Python 3; run it in the container with `--entrypoint python3` if the host has none.
The FW DTI tensor source and empty datasheet cells need dtiplayground 0.7.1 or later.
