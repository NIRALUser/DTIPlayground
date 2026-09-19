#   Cohort report of a dmriprep batch (dmriprep bids ... group / dmriprep batch-report)
#
#   <out>/batch/qc_table.tsv                  one row per dataset: state, run time, volumes in/out, mask volume, mean FA,
#                                             motion, eddy outlier slices, SNR/CNR and tensor fit (when these modules ran)
#   <out>/batch/qc_report.html                the same table, with values far from the cohort median marked
#   <out>/batch/fiberprofile_datasheet.csv    datasheet for dmrifiberprofile (column names of
#                                             examples/normative_profiles), for the datasets with a DTI

import csv
import html
from pathlib import Path

import numpy as np

from dtiplayground.dmri.preprocessing import batch

# datasheet column -> output name of the dmriprep module (file <base>_<name>.<ext> in the dataset folder)
FIBERPROFILE_COLUMNS = [('DTI', 'DTI'), ('FW DTI', 'FWDTI'), ('Deformation field', 'DTI_DisplacementField'),
                        ('FWF', 'NODDI_FWF'), ('NDI', 'NODDI_NDI'), ('ODI', 'NODDI_ODI')]
# column -> direction of the unusual values that are marked (0: both sides, 1: high values, -1: low values)
# mask volume, FA, SNR and CNR change with age and acquisition: not marked
OUTLIER_COLUMNS = {'excluded_volumes': 0, 'mean_fd': 1, 'outlier_slices_percent': 1, 'fit_r2_mean': -1,
                   'poor_fit_slices': 1}
# columns of the summaries written by the modules (<base>_<name>.tsv), in this order; SNR/CNR columns are added
QC_SUMMARIES = [('DENOISE_QC', ['noise_sigma', 'snr_b0_mppca', 'noise_residual_rms']),
                ('EDDY_QC', ['mean_fd', 'max_fd', 'max_translation', 'max_rotation', 'outlier_slices_percent']),
                ('DTI_fit_QC', ['fit_r2_mean', 'fit_r2_min', 'poor_fit_slices'])]


def _output(folder, base, name):
    """Output <base>_<name>.(nrrd|nii.gz|nii) of a dataset, None if it isn't there."""
    for ext in ('.nrrd', '.nii.gz', '.nii'):
        p = folder.joinpath('{}_{}{}'.format(base, name, ext))
        if p.is_file():
            return p
    return None


def _volumes(path):
    """Number of volumes of a DWI (NIfTI or NRRD), None if unreadable."""
    try:
        if str(path).endswith('.nrrd'):
            import nrrd
            header = nrrd.read_header(str(path))
            return sum(1 for k in header if k.startswith('DWMRI_gradient_'))
        import nibabel as nib
        shape = nib.load(str(path)).header.get_data_shape()
        return shape[3] if len(shape) > 3 else 1
    except Exception:
        return None


def _load(path):
    import nibabel as nib
    if str(path).endswith('.nrrd'):
        import nrrd
        data, header = nrrd.read(str(path))
        directions = np.array([d for d in header['space directions'] if d is not None], dtype=float)
        return data, abs(float(np.linalg.det(directions[:3, :3])))
    image = nib.load(str(path))
    return np.asanyarray(image.dataobj), float(np.prod(image.header.get_zooms()[:3]))


def dataset_row(out, dataset, state, status):
    folder = Path(out).joinpath(dataset['output_dir'])
    base = dataset.get('output_file_base') or Path(dataset['images'][0]).name.split('.')[0]
    row = {'id': dataset['id'], 'subject': dataset.get('subject', ''), 'session': dataset.get('session', ''),
           'state': state, 'minutes': round(float(status['seconds']) / 60, 1) if status.get('seconds') not in (None, '') else '',
           'input_volumes': '', 'output_volumes': '', 'excluded_volumes': '', 'mask_ml': '', 'mean_fa': '',
           'output_dir': dataset['output_dir']}
    inputs = [_volumes(i) for i in dataset['images']]
    if all(v is not None for v in inputs):
        row['input_volumes'] = sum(inputs)
    qced = next((p for p in (folder.joinpath(base + '_QCed' + e) for e in ('.nii.gz', '.nrrd', '.nii')) if p.is_file()), None)
    if qced is not None:
        row['output_volumes'] = _volumes(qced)
        if row['input_volumes'] != '' and row['output_volumes'] is not None:
            row['excluded_volumes'] = row['input_volumes'] - row['output_volumes']
    mask_path, fa_path = _output(folder, base, 'Mask'), _output(folder, base, 'DTI_FA')
    try:
        mask = None
        if mask_path is not None:
            data, voxel = _load(mask_path)
            mask = np.squeeze(data) > 0
            row['mask_ml'] = round(float(mask.sum()) * voxel / 1000.0, 1)
        if fa_path is not None:
            fa = np.squeeze(_load(fa_path)[0]).astype(float)
            inside = mask if mask is not None and mask.shape == fa.shape else fa > 0
            row['mean_fa'] = round(float(np.nanmean(fa[inside])), 4)
    except Exception:
        pass
    for name, columns in QC_SUMMARIES:
        path = folder.joinpath('{}_{}.tsv'.format(base, name))
        summary = {}
        if path.is_file():
            try:
                with open(path, newline='') as f:
                    summary = next(csv.DictReader(f, dialect='excel-tab'), {}) or {}
            except Exception:
                summary = {}
        for c in columns + [k for k in summary if k.startswith(('snr_', 'cnr_'))]:
            row[c] = summary.get(c, '')
    sheet = {'id': dataset['id']}
    for column, name in FIBERPROFILE_COLUMNS:
        p = _output(folder, base, name)
        sheet[column] = str(p) if p is not None else ''
    return row, sheet


def mark_outliers(rows, columns=OUTLIER_COLUMNS, limit=3.0):
    """{(row index, column)} of the values more than *limit* scaled MADs from the median of the column, on the side
    given by the column direction (0: both, 1: above, -1: below)."""
    marked = set()
    for c, side in (columns.items() if isinstance(columns, dict) else [(c, 0) for c in columns]):
        values = [(i, float(r[c])) for i, r in enumerate(rows) if r.get(c) not in ('', None)]
        if len(values) < 5:
            continue
        v = np.array([x for _, x in values])
        median = np.median(v)
        mad = 1.4826 * np.median(np.abs(v - median))
        deviation = {i: (x - median) * (side if side else 1) for i, x in values}
        if mad == 0:
            marked |= {(i, c) for i, x in values if (deviation[i] > 0 if side else x != median)}
            continue
        marked |= {(i, c) for i, x in values if (deviation[i] if side else abs(deviation[i])) > limit * mad}
    return marked


def write_report(out, echo=print):
    out = Path(out)
    datasets = batch.load_manifest(out)
    rows, sheets = [], []
    for d in datasets:
        state, status = batch.current_state(out, d)
        row, sheet = dataset_row(out, d, state, status)
        rows.append(row)
        if state == 'done' and sheet['DTI']:
            sheets.append(sheet)
    bdir = batch.batch_dir(out)
    columns = []
    for r in rows: # the SNR/CNR columns depend on the shells of each dataset
        columns += [c for c in r if c not in columns]
    columns = columns or ['id']
    for r in rows:
        for c in columns:
            r.setdefault(c, '')
    with open(bdir.joinpath('qc_table.tsv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, dialect='excel-tab')
        w.writeheader()
        w.writerows(rows)
    sheet_columns = ['id'] + [c for c, _ in FIBERPROFILE_COLUMNS if any(s[c] for s in sheets)]
    with open(bdir.joinpath('fiberprofile_datasheet.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=sheet_columns, extrasaction='ignore')
        w.writeheader()
        w.writerows(sheets)
    marked = mark_outliers(rows)
    counts = {}
    for r in rows:
        counts[r['state']] = counts.get(r['state'], 0) + 1
    _write_html(bdir.joinpath('qc_report.html'), out, rows, columns, marked, counts)
    echo('{} dataset(s): {}'.format(len(rows), ', '.join('{} {}'.format(v, k) for k, v in sorted(counts.items()))))
    echo('QC table: {}'.format(bdir.joinpath('qc_table.tsv')))
    echo('QC report: {}'.format(bdir.joinpath('qc_report.html')))
    echo('dmrifiberprofile datasheet ({} dataset(s) with a DTI): {}'.format(len(sheets), bdir.joinpath('fiberprofile_datasheet.csv')))
    if marked:
        echo('{} value(s) far from the cohort median are marked in the report ({})'.format(
            len(marked), ', '.join(sorted({c for _, c in marked}))))


def _write_html(path, out, rows, columns, marked, counts):
    esc = html.escape
    head = ''.join('<th>{}</th>'.format(esc(c)) for c in columns if c != 'output_dir')
    body = []
    for i, r in enumerate(rows):
        cells = []
        for c in columns:
            if c == 'output_dir':
                continue
            value = esc(str(r[c]))
            if c == 'id':
                value = '<a href="../{}/">{}</a>'.format(esc(r['output_dir']), value)
            cls = ' class="flag"' if (i, c) in marked else (' class="{}"'.format(esc(r['state'])) if c == 'state' else '')
            cells.append('<td{}>{}</td>'.format(cls, value))
        body.append('<tr>{}</tr>'.format(''.join(cells)))
    summary = ', '.join('{} {}'.format(v, esc(k)) for k, v in sorted(counts.items()))
    path.write_text("""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>dmriprep batch QC</title>
<style>
body {{ font-family: sans-serif; margin: 16px; }}
table {{ border-collapse: collapse; font-size: 13px; }}
th, td {{ border: 1px solid #ccc; padding: 3px 8px; text-align: right; }}
th {{ background: #eee; }} td:first-child {{ text-align: left; }}
td.flag {{ background: #ffd8a8; font-weight: bold; }}
td.failed, td.interrupted {{ background: #ffc9c9; }} td.outdated, td.pending {{ background: #fff3bf; }}
</style></head><body>
<h2>dmriprep batch: {folder}</h2>
<p>{n} dataset(s): {summary}. Orange: more than 3 scaled MADs from the cohort median: number of excluded volumes (either side),
mean framewise displacement, eddy outlier slices and poorly fitted slices of the tensor fit (high side), mean tensor fit R2 (low side).
Motion in mm and degrees; outlier slices in % of the slices. Details: batch/status.tsv and the batch_log.txt / log.txt of each dataset,
and the per volume tables &lt;base&gt;_EDDY_motion.tsv and &lt;base&gt;_DTI_fit.tsv.</p>
<table><tr>{head}</tr>
{body}
</table></body></html>
""".format(folder=esc(str(Path(out).name)), n=len(rows), summary=summary, head=head, body='\n'.join(body)))
