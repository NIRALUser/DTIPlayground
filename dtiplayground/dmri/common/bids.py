#   BIDS discovery of diffusion weighted images for batch processing
#
#   Finds sub-<label>/[ses-<label>/]dwi/*_dwi.nii[.gz] with their .bval/.bvec (and .json sidecar), parses the BIDS
#   entities, and groups the runs into datasets: every run on its own, or pairs of runs with opposite phase encoding
#   (e.g. dir-AP / dir-PA) for the susceptibility correction. The phase encoding comes from the sidecar
#   (PhaseEncodingDirection, TotalReadoutTime), or from the dir entity (AP, PA, LR, RL, SI, IS) when there is none.
#   The two runs of a pair are ordered as dmriprep expects for SUSCEPTIBILITY_Correct: first the run encoded towards
#   posterior, left or inferior (AP, RL, SI), then the opposite one.

import json
import os
import re
from pathlib import Path

ENTITY_ORDER = ['sub', 'ses', 'task', 'acq', 'ce', 'rec', 'dir', 'run', 'echo', 'part', 'chunk']
PAIR_VARYING = ('dir', 'run')  # entities that may differ between the two runs of a phase encoding pair
AXES = {'i': 0, 'j': 1, 'k': 2}
OPPOSITE = {'L': 'R', 'R': 'L', 'A': 'P', 'P': 'A', 'S': 'I', 'I': 'S'}
FIRST_OF_PAIR = ('P', 'L', 'I')  # the run encoded towards these directions comes first (dir-AP, dir-RL, dir-SI)
_ENTITY = re.compile(r'^([a-zA-Z0-9]+)-([a-zA-Z0-9+]+)$')


def parse_name(filename):
    """(entities, suffix) of a BIDS file name, e.g. sub-01_ses-1_dir-AP_dwi.nii.gz -> ({sub: 01, ses: 1, dir: AP},
    'dwi'); None if it is not a BIDS name."""
    stem = Path(filename).name.split('.')[0]
    parts = stem.split('_')
    entities = {}
    for p in parts[:-1]:
        m = _ENTITY.match(p)
        if not m:
            return None
        entities[m.group(1)] = m.group(2)
    if 'sub' not in entities:
        return None
    return entities, parts[-1]


def build_name(entities, suffix=None):
    """BIDS name from entities in the standard order (unknown entities after them), with an optional suffix."""
    keys = [k for k in ENTITY_ORDER if k in entities] + [k for k in entities if k not in ENTITY_ORDER]
    parts = ['{}-{}'.format(k, entities[k]) for k in keys]
    if suffix:
        parts.append(suffix)
    return '_'.join(parts)


def _read_sidecar(image_path, root):
    """Sidecar of *image_path* with the BIDS inheritance: the .json files with the same suffix whose entities are a
    subset of the image's, from the dataset *root* down to the image folder, the deeper and more specific winning."""
    image_path, root = Path(image_path), Path(root)
    entities, suffix = parse_name(image_path.name)
    folders = [image_path.parent]
    while folders[-1] != root and root in folders[-1].parents:
        folders.append(folders[-1].parent)
    sidecar = {}
    for folder in reversed(folders):
        applicable = []
        for candidate in folder.glob('*{}.json'.format(suffix)):
            name = candidate.name[:-len('.json')]
            if name == suffix:
                applicable.append((0, candidate))
                continue
            parsed = parse_name(candidate.name) if name.startswith('sub-') else None
            if parsed is None:  # dataset level sidecar without sub (e.g. acq-x_dwi.json)
                parts = name.split('_')
                pairs = [p.split('-', 1) for p in parts[:-1]]
                if parts[-1] != suffix or any(len(p) != 2 for p in pairs):
                    continue
                parsed = (dict(pairs), parts[-1])
            ents, suf = parsed
            if suf == suffix and all(entities.get(k) == v for k, v in ents.items()):
                applicable.append((len(ents), candidate))
        for _, candidate in sorted(applicable, key=lambda x: x[0]):
            try:
                sidecar.update(json.loads(candidate.read_text()))
            except (OSError, ValueError):
                pass
    return sidecar


def phase_encoding(scan):
    """(voxel axis index, sign, anatomical direction the encoding goes towards) of *scan*, from the
    PhaseEncodingDirection of its sidecar (voxel axes i, j, k) or its dir entity (e.g. AP: from anterior towards
    posterior) with the orientation of the image; None if unknown."""
    codes = scan.get('axcodes')
    ped = scan['sidecar'].get('PhaseEncodingDirection')
    if ped and ped[0] in AXES:
        axis, sign = AXES[ped[0]], (-1 if ped.endswith('-') else 1)
        if not codes:
            return axis, sign, None
        return axis, sign, codes[axis] if sign > 0 else OPPOSITE[codes[axis]]
    label = str(scan['entities'].get('dir', '')).upper()
    if len(label) != 2 or not codes or label[0] not in OPPOSITE or OPPOSITE[label[0]] != label[1]:
        return None
    towards = label[1]
    for axis, code in enumerate(codes):
        if code == towards:
            return axis, 1, towards
        if code == OPPOSITE[towards]:
            return axis, -1, towards
    return None


def find_dwi(bids_dir, participants=None, sessions=None):
    """DWI runs of a BIDS dataset: list of dicts with path, bval, bvec, entities, sidecar; runs without bval/bvec are
    returned in a second list (path, reason)."""
    root = Path(os.path.abspath(bids_dir))  # absolute, symbolic links kept (paths must work on other hosts)
    participants = {str(p).replace('sub-', '') for p in participants} if participants else None
    sessions = {str(s).replace('ses-', '') for s in sessions} if sessions else None
    scans, skipped = [], []
    images = sorted(set(root.glob('sub-*/dwi/*_dwi.nii*')) | set(root.glob('sub-*/ses-*/dwi/*_dwi.nii*')))
    for image in images:
        if not (image.name.endswith('.nii') or image.name.endswith('.nii.gz')):
            continue
        parsed = parse_name(image.name)
        if parsed is None:
            skipped.append((str(image), 'not a BIDS file name'))
            continue
        entities, _ = parsed
        if participants is not None and entities['sub'] not in participants:
            continue
        if sessions is not None and entities.get('ses') not in sessions:
            continue
        stem = image.name.split('.')[0]
        bval, bvec = image.with_name(stem + '.bval'), image.with_name(stem + '.bvec')
        if not bval.is_file() or not bvec.is_file():
            skipped.append((str(image), 'no .bval/.bvec'))
            continue
        try:
            import nibabel as nib
            axcodes = nib.aff2axcodes(nib.load(str(image)).affine)
        except Exception:
            axcodes = None
        scans.append({'path': str(image), 'bval': str(bval), 'bvec': str(bvec), 'entities': entities,
                      'name': stem, 'sidecar': _read_sidecar(image, root), 'axcodes': axcodes})
    return scans, skipped


def group_key(scan):
    """Scans with the same key are candidates for a phase encoding pair."""
    return tuple(sorted((k, v) for k, v in scan['entities'].items() if k not in PAIR_VARYING))


def make_pairs(scans):
    """Pairs (first, second) of scans with opposite phase encoding along the same axis, in run order, the first
    encoded towards posterior, left or inferior. Returns (pairs, problem): problem describes why the scans can't be
    paired (None if they can)."""
    encodings = [phase_encoding(s) for s in scans]
    if any(e is None or e[2] is None for e in encodings):
        unknown = [s['name'] for s, e in zip(scans, encodings) if e is None or e[2] is None]
        return [], 'unknown phase encoding direction of {}'.format(', '.join(unknown))
    if len({e[0] for e in encodings}) != 1:
        return [], 'phase encoding along different axes'
    run = lambda s: (int(s['entities']['run']) if str(s['entities'].get('run', '')).isdigit() else 0, s['name'])
    first = sorted([s for s, e in zip(scans, encodings) if e[2] in FIRST_OF_PAIR], key=run)
    second = sorted([s for s, e in zip(scans, encodings) if e[2] not in FIRST_OF_PAIR], key=run)
    if not first or not second:
        towards = sorted({e[2] for e in encodings})
        return [], 'no opposite phase encoding ({} run(s), all towards {})'.format(len(scans), '/'.join(towards))
    if len(first) != len(second):
        return [], '{} and {} runs in the two phase encoding directions'.format(len(first), len(second))
    return list(zip(first, second)), None


def dataset_id(scans):
    """Identifier of a dataset of one or two scans: the BIDS name of the scan without the _dwi suffix, without the
    entities that differ between the two scans of a pair."""
    if len(scans) == 1:
        entities = scans[0]['entities']
    else:
        entities = {k: v for k, v in scans[0]['entities'].items()
                    if all(s['entities'].get(k) == v for s in scans[1:])}
    return build_name(entities)


def readout_time(scans):
    """Total readout time common to *scans* (from the sidecars), None if unknown."""
    values = [s['sidecar'].get('TotalReadoutTime') for s in scans]
    if any(v is None for v in values):
        return None
    return float(sum(values)) / len(values)
