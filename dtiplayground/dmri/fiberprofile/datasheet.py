#   Datasheet of EXTRACT_Profile detected from a folder (dmrifiberprofile run -i <folder>, make-datasheet)
#
#   The files are found anywhere below the folder and grouped by case id, the part of the file name before '_dwi'
#   (e.g. sub-100619_ses-017m_acq-dir79select_dir_run-004). Known names, after <id>_dwi[...]:
#
#     native space (useDisplacementField: true; the atlas fibers are mapped to the scan with the displacement field)
#       tensor              _dwi[_QCed]_tensor.nrrd, _dwi[_QCed]_DTI.nrrd                  (IBIS mask/, dmriprep)
#       displacement field  ..._GlobalDisplacementField.nrrd, ..._DTI_DisplacementField.nrrd  (DTI-Reg, dmriprep
#                           DTI_Register; never an inverse field)
#       free-water tensor   ..._FWtensor.nrrd, ..._FWDTI.nrrd
#       scalar map P        ..._P.nii[.gz], ..._DTI_P.nii[.gz], ..._NODDI_P.nii[.gz]          (e.g. _FA, _DTI_FA, _NODDI_NDI)
#     atlas space (useDisplacementField: false; images already registered to the atlas)
#       tensor              ..._DeformedDTI.nrrd, ..._DTI_Registered.nrrd
#       scalar map P        ..._DeformedP.nii[.gz], ..._Registered_[DTI_|NODDI_]P.nii[.gz]
#
#   Property names are case sensitive: FWF is the NODDI free-water fraction (_NODDI_FWF), FWf the free-water fraction
#   of the free-water DTI model (_FWf). FA, MD, AD, RD are computed from the tensors (inputIsDTI), <prefix>FA, ... from
#   the '<prefix>' tensors when there are any (e.g. FW tensors for FWFA), from their scalar maps otherwise.

import csv
import os
import re
from collections import defaultdict
from pathlib import Path

TENSOR_PROPERTIES = ['FA', 'MD', 'AD', 'RD']
IMAGE_SUFFIXES = ('.nrrd', '.nhdr', '.nii.gz', '.nii')
DEFAULT_ID_REGEX = r'^(.+?)_dwi(?=[_.])'
TENSOR_PREFIXES = {'FW': r'_(?:FWtensor|FWDTI)'}  # tensors of the prefixed properties (native space)
# column names of the generated datasheet (examples/normative_profiles)
ID_COLUMN, DTI_COLUMN, FIELD_COLUMN = 'id', 'DTI', 'Deformation field'


class DatasheetError(Exception):
    pass


def _stem(name):
    for suffix in IMAGE_SUFFIXES:
        if name.endswith(suffix):
            return name[:-len(suffix)], suffix
    return None, None


def role_pattern(role, space):
    """Regex on the rest of a file name after the case id (e.g. '_dwi_QCed_tensor.nrrd') for a role: 'dti', 'field',
    'tensor:<prefix>' or 'scalar:<property>'."""
    if role == 'dti':
        return r'^_dwi(?:_QCed)?_(?:tensor|DTI)\.nrrd$' if space == 'native' else r'^_dwi.*_(?:DeformedDTI|DTI_Registered)\.nrrd$'
    if role == 'field':
        return r'^_dwi(?!.*Inverse).*_(?:GlobalDisplacementField|DTI_DisplacementField)\.nrrd$'
    kind, _, name = role.partition(':')
    if kind == 'tensor':
        return r'^_dwi(?!.*(?:Registered|Deformed)).*{}\.nrrd$'.format(TENSOR_PREFIXES[name]) if space == 'native' else None
    prop = re.escape(name)
    if space == 'native':
        return r'^_dwi(?!.*(?:_Registered_|_Deformed))(?:_[^.]*)?_(?:DTI_|NODDI_)?{}\.nii(?:\.gz)?$'.format(prop)
    return r'^_dwi.*_(?:Deformed|Registered_(?:DTI_|NODDI_)?){}\.nii(?:\.gz)?$'.format(prop)


def role_description(role, space):
    """Readable file names of a role, as in the error messages."""
    if role == 'dti':
        return '<id>_dwi[_QCed]_tensor.nrrd, <id>_dwi[_QCed]_DTI.nrrd' if space == 'native' else \
               '<id>_dwi*_DeformedDTI.nrrd, <id>_dwi*_DTI_Registered.nrrd'
    if role == 'field':
        return '<id>_dwi*_GlobalDisplacementField.nrrd, <id>_dwi*_DTI_DisplacementField.nrrd (not inverse)'
    kind, _, name = role.partition(':')
    if kind == 'tensor':
        return '<id>_dwi*_FWtensor.nrrd, <id>_dwi*_FWDTI.nrrd' if space == 'native' else 'none (atlas space)'
    if space == 'native':
        return '<id>_dwi*_{0}.nii[.gz], <id>_dwi*_DTI_{0}.nii[.gz], <id>_dwi*_NODDI_{0}.nii[.gz]'.format(name)
    return '<id>_dwi*_Deformed{0}.nii[.gz], <id>_dwi*_Registered_[DTI_|NODDI_]{0}.nii[.gz]'.format(name)


def find_images(base_dir, id_regex=DEFAULT_ID_REGEX):
    """{case id: [(file name rest after the id, path)]} of the images below *base_dir* (hidden folders skipped)."""
    id_re = re.compile(id_regex)
    found = defaultdict(list)
    for folder, dirs, files in os.walk(base_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for name in sorted(files):
            if _stem(name)[0] is None:
                continue
            m = id_re.search(name)
            if m:
                found[m.group(1)].append((name[m.end(1):], os.path.join(folder, name)))
    return found


def property_columns(properties, input_is_dti, tensor_prefixes_found):
    """Source of each property: ('tensor', role, column) or ('scalar', role, column)."""
    sources = {}
    for prop in properties:
        name = prop.upper()
        if input_is_dti and len(prop) >= 2 and name[-2:] in TENSOR_PROPERTIES:
            prefix = prop[:-2]
            if prefix == '':
                sources[prop] = ('tensor', 'dti', DTI_COLUMN)
                continue
            if prefix in tensor_prefixes_found:
                sources[prop] = ('tensor', 'tensor:' + prefix, prefix + ' DTI')
                continue
        sources[prop] = ('scalar', 'scalar:' + prop, prop)
    return sources


def detect(base_dir, protocol, id_regex=DEFAULT_ID_REGEX):
    """Datasheet rows of the scans below *base_dir* for the EXTRACT_Profile *protocol* (dict of its parameters).
    Returns (columns, rows, parameter map for the protocol, skipped [(id, reason)], notes); raises DatasheetError
    if no scan has the files the protocol needs."""
    if not Path(base_dir).is_dir():
        raise DatasheetError('Not a folder: {}'.format(base_dir))
    properties = [p.strip() for p in str(protocol.get('propertiesToProfile') or '').split(',') if p.strip()]
    if not properties:
        raise DatasheetError('The protocol has no propertiesToProfile')
    use_field = bool(protocol.get('useDisplacementField', True))
    input_is_dti = bool(protocol.get('inputIsDTI', True))
    space = 'native' if use_field else 'atlas'
    images = find_images(base_dir, id_regex)

    def matches(role, files):
        pattern = role_pattern(role, space)
        return [] if pattern is None else [p for rest, p in files if re.search(pattern, rest)]

    ## tensors of prefixed properties (e.g. FW for FWFA) are used when some scan has them, else their scalar maps
    prefixes = {p[:-2] for p in properties if input_is_dti and len(p) > 2 and p[-2:].upper() in TENSOR_PROPERTIES}
    found_prefixes = {pre for pre in prefixes if pre in TENSOR_PREFIXES
                      and any(matches('tensor:' + pre, files) for files in images.values())}
    sources = property_columns(properties, input_is_dti, found_prefixes)
    columns = [ID_COLUMN]
    roles = []  # (column, role, required)
    if use_field:
        roles.append((FIELD_COLUMN, 'field', True))
    for prop, (kind, role, column) in sources.items():
        if column not in [c for c, _, _ in roles]:
            roles.append((column, role, role == 'dti'))
    columns += [c for c, _, _ in roles]

    rows, skipped, counts = [], [], defaultdict(int)
    for case_id in sorted(images):
        files = images[case_id]
        row, problem = {ID_COLUMN: case_id}, None
        hits_of = {column: matches(role, files) for column, role, _ in roles}
        for column in hits_of:
            counts[column] += bool(hits_of[column])
        for column, role, required in roles:
            hits = hits_of[column]
            if len(hits) > 1:
                problem = '{} files for {}: {}'.format(len(hits), column, ', '.join(hits))
                break
            if not hits and required:
                problem = 'no {} file'.format(column)
                break
            row[column] = os.path.abspath(hits[0]) if hits else ''
        if problem is None and not any(row[c] for c, role, _ in roles if role != 'field'):
            problem = 'no image of the properties to profile'
        if problem:
            skipped.append((case_id, problem))
        else:
            rows.append(row)

    if not rows:
        lines = ['No scan below {} has the files needed by the protocol ({} space, useDisplacementField: {}).'.format(
                 base_dir, space, str(use_field).lower()),
                 'Known file names (<id>: case id, the part of the file name before _dwi; *: any text):']
        for column, role, required in roles:
            lines.append('  {:<18} {} ({} of {} case id(s) with a match): {}'.format(
                column, 'required' if required else 'optional', counts[column], len(images), role_description(role, space)))
        lines.append('{} case id(s) found with an image: {}'.format(len(images), ', '.join(sorted(images)[:5]) + (' ...' if len(images) > 5 else '')))
        lines += ['  {}: {}'.format(i, r) for i, r in skipped[:10]]
        raise DatasheetError('\n'.join(lines))

    parameter_map = {'Case ID': ID_COLUMN, 'Original DTI Image': DTI_COLUMN}
    if use_field:
        parameter_map['Deformation Field'] = FIELD_COLUMN
    for prop, (kind, role, column) in sources.items():
        if kind == 'tensor' and role != 'dti':
            parameter_map[column + ' Image'] = column  # e.g. 'FW DTI Image': 'FW DTI'
        elif kind == 'scalar':
            parameter_map[prop] = column
    notes = []
    for column, role, required in roles:
        empty = sum(1 for r in rows if not r[column])
        if empty:
            notes.append('{}: no file for {} of {} scan(s)'.format(column, empty, len(rows)))
    for prop, (kind, role, column) in sources.items():
        notes.append('{}: {}'.format(prop, 'computed from the tensors of column {}'.format(column) if kind == 'tensor'
                                      else 'sampled from the images of column {}'.format(column)))
    no_age = [r[ID_COLUMN] for r in rows if not re.search(r'ses-\d+m', r[ID_COLUMN])]
    if no_age:
        notes.append('{} case id(s) have no age (ses-<months>m), needed by qc-profiles: {}'.format(len(no_age), ', '.join(no_age[:5])))
    return columns, rows, parameter_map, skipped, notes


def write_datasheet(path, columns, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def extract_profile_protocol(protocol):
    """Parameters of the EXTRACT_Profile module of a protocol (dict of a protocol file)."""
    for name, entry in protocol.get('pipeline', []):
        if name == 'EXTRACT_Profile':
            return entry.setdefault('protocol', {})
    raise DatasheetError('The protocol has no EXTRACT_Profile module')
