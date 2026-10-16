import hashlib
import json
import os.path
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

import dtiplayground.dmri.common as common
import dtiplayground.dmri.fiberprofile as base
import dtiplayground.dmri.common.fibers as fibers

logger = common.logger.write

TENSOR_PROPERTIES = ['FA', 'MD', 'AD', 'RD']


def property_sources(properties, input_is_dti, parameter_to_col_map):
    """Source of every property: ('tensor', column, scalar name) or ('scalar', column, None).
    With a DTI input, FA, MD, AD, RD are computed from the tensors of 'Original DTI Image', and <prefix>FA, ... from
    the tensors of '<prefix> DTI Image' when the map has that key (e.g. FWFA from 'FW DTI Image'). Every other property
    is sampled from its own scalar image."""
    sources = {}
    for prop in properties:
        name = prop.upper()
        if input_is_dti and len(name) >= 2 and name[-2:] in TENSOR_PROPERTIES:
            prefix = prop[:-2]
            key = 'Original DTI Image' if prefix == '' else f'{prefix} DTI Image'
            if key in parameter_to_col_map:
                sources[prop] = ('tensor', parameter_to_col_map[key], name[-2:])
                continue
        sources[prop] = ('scalar', parameter_to_col_map[prop], None)
    return sources

# protocol parameters a profile depends on (with the images, tract and mask): a profile of a previous run (.fvp) is
# reused only if they and the input files are unchanged (the signature stored next to it, <profile>.json)
PROFILE_SETTINGS = ['inputIsDTI', 'useDisplacementField', 'tensorInterpolation', 'supportBandwidth', 'stepSize',
                    'arcLength', 'planeOfOrigin', 'noNaN', 'maskThreshold']


def file_stamp(path):
    """Identity of an input file for the reuse of results: absolute path, size and modification time."""
    if path is None:
        return None
    p = Path(str(path))
    try:
        st = p.stat()
        return {'path': str(p.resolve()), 'size': st.st_size, 'mtime_ns': st.st_mtime_ns}
    except OSError:
        return {'path': str(p), 'missing': True}


def signature_matches(signature_path, signature):
    """Whether the signature stored at *signature_path* (JSON) equals *signature*."""
    try:
        with open(signature_path, 'r') as f:
            return json.load(f) == json.loads(json.dumps(signature, sort_keys=True, default=str))
    except (OSError, ValueError):
        return False


def write_signature(signature_path, signature):
    with open(signature_path, 'w') as f:
        json.dump(signature, f, sort_keys=True, default=str, indent=1)


def read_fvp(path):
    """Arc lengths and values of a profile written by fibers.write_fvp (4 header lines, a column header, then CSV);
    a plain parse, much faster than pandas for the many small files of a run."""
    with open(path, 'r') as f:
        rows = [line.split(',') for line in f.read().splitlines()[5:] if line.strip() != '']
    return np.array([float(r[0]) for r in rows]), np.array([float(r[2]) for r in rows])


def reuse_fvp(fvp_path, signature, grid):
    """Values of the profile of a previous run (.fvp) if its signature (<profile>.json) matches and its arc lengths
    are the grid, otherwise None."""
    if not signature_matches(fvp_path.with_suffix('.json'), signature):
        return None
    try:
        arcs, values = read_fvp(fvp_path)
    except (OSError, ValueError, IndexError):
        return None
    if len(arcs) == len(grid) and np.allclose(arcs, grid, atol=1e-4):
        return values
    return None


# folder of the records of the subjects (<subject id>.npz): all the profiles of a subject with the hash of their
# signature and grid, written when the subject is done, so that a later run reads one file per subject instead of
# two per profile. Kept by the cleanup.
RECORD_DIR = 'subject_profiles'
READ_THREADS = 16


def record_key(tract_name, prop):
    return f'{tract_name}\t{prop}'


def read_record(path):
    """{key: (hash, profile values)} of the record of a subject, {} if it can't be read (the profiles are then taken
    from the .fvp files or computed)."""
    try:
        with np.load(path, allow_pickle=False) as d:
            keys, hashes, offsets, values = d['keys'], d['hashes'], d['offsets'], d['values']
        return {str(k): (str(h), values[offsets[i]:offsets[i + 1]]) for i, (k, h) in enumerate(zip(keys, hashes))}
    except Exception:
        return {}


def write_record(path, entries):
    """Writes the record of a subject ({key: (hash, profile values)}) atomically: an interrupted run leaves no
    partial record."""
    keys = sorted(entries)
    values = [np.asarray(entries[k][1], dtype=np.float64) for k in keys]
    offsets = np.concatenate([[0], np.cumsum([len(v) for v in values])]).astype(np.int64)
    tmp = Path(str(path) + '.tmp')
    with open(tmp, 'wb') as f:
        np.savez(f, keys=np.array(keys, dtype=str), hashes=np.array([entries[k][0] for k in keys], dtype=str),
                 offsets=offsets, values=np.concatenate(values) if values else np.zeros(0))
    os.replace(tmp, path)


class CleanupMethod():
    DURING = 'duringProcessing'
    END = 'endOfProcessing'
    NONE = 'noCleanup'
class EXTRACT_Profile(base.modules.DTIFiberProfileModule):
    def __init__(self, config_dir, *args, **kwargs):
        super().__init__(config_dir)

    def generateDefaultProtocol(self, image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    """
    Main function called by the pipeline when this module runs.
    """

    def process(self, *args, **kwargs):
        super().process()
        inputParams = self.getPreviousResult()['output']
        protocol_options = args[0]
        self.software_info = protocol_options['software_info']['softwares']

        # Reading some parameters
        try:
            path_to_csv: str = inputParams["file_path"]
            output_base_dir: str = self.output_dir  # output directory string

            tracts_string = self.protocol["tracts"]
            atlas_path: str = self.protocol["atlas"]
            if tracts_string is not None and not isinstance(tracts_string, str):
                raise ValueError("Tracts must be a string of comma delimited tracts to profile")
            tracts: List[str] = [tract.strip() for tract in (tracts_string or '').split(',') if tract.strip() != '']
            if len(tracts) == 0:  # no tracts given: all the tracts of the atlas
                if not isinstance(atlas_path, str) or not os.path.isdir(atlas_path):
                    raise ValueError("No tracts to profile: give the tracts, or an atlas folder to profile all its tracts "
                                     f"(atlas: {atlas_path})")
                tracts = sorted(f for f in os.listdir(atlas_path) if f.endswith('.vtk'))
                if len(tracts) == 0:
                    raise ValueError(f"No tracts to profile: no .vtk file in the atlas folder {atlas_path}")
                logger(f"No tracts given: the {len(tracts)} tracts of the atlas {atlas_path} are profiled")
            if not isinstance(atlas_path, str):
                for tract in tracts:
                    if not os.path.isabs(tract):
                        raise ValueError(
                            f"Tract paths must all be absolute if no atlas path is provided. Atlas path current value: {atlas_path}. Either provide atlas dir or convert this path to absolute: {tract}")
            properties_to_profile: List[str] = [x.strip() for x in self.protocol["propertiesToProfile"].split(',') if x.strip() != '']
            result_case_columnwise: bool = self.protocol["resultCaseColumnwise"]
            input_is_dti: bool = self.protocol["inputIsDTI"]
            overwrite: bool = self.options['overwrite']
            use_displacement_field: bool = self.protocol["useDisplacementField"]
            step_size: float = float(self.protocol["stepSize"])
            plane_of_origin: str = self.protocol["planeOfOrigin"]
            arc_length_source: str = self.protocol.get("arcLength", "stored")
            if arc_length_source not in ['stored', 'compute']:
                raise ValueError(f"Invalid arc length: {arc_length_source} (stored or compute)")
            support_bandwidth: float = float(self.protocol["supportBandwidth"])
            noNaN: bool = self.protocol["noNaN"]
            write_fiber_files: bool = bool(self.protocol.get("writeFiberFiles", False))
            mask: str = self.protocol["mask"]
            mask_threshold: float = float(self.protocol.get("maskThreshold", 0.5))
            tensor_interpolation: str = self.protocol.get("tensorInterpolation", "logEuclidean")
            cleanupMethod: str = self.protocol["cleanup"]
            if cleanupMethod not in [CleanupMethod.DURING, CleanupMethod.NONE, CleanupMethod.END]:
                raise ValueError(f"Invalid cleanup method: {cleanupMethod}")
        except KeyError as e:
            self.result['output']['success'] = False
            self.result['output']['error'] = f"Missing parameter {e}"
            logger(f"Missing parameter: {e}")
            exit(1)
        except ValueError as e:
            self.result['output']['success'] = False
            self.result['output']['error'] = f"Invalid parameter {e}"
            logger(f"Invalid parameter: {e}")
            exit(1)

        df = pd.read_csv(path_to_csv)

        # Get parameter to col map, overriding with user inputs if necessary
        # Generate default map
        parameter_to_col_map = {'Case ID': 'id', 'Original DTI Image': 'Original DTI image',
                                'Deformation Field': 'Concatenated Deformation field'}
        for scalar in ['FA', 'MD', 'AD', 'RD']:
            scalar_col = f'{scalar} from original'
            parameter_to_col_map[scalar] = scalar_col
        for scalar in properties_to_profile:
            scalar_col = f'{scalar} from original'
            parameter_to_col_map[scalar] = scalar_col

        # Update defaults with user overrides
        user_parameter_to_col_map = self.protocol['parameterToColumnHeaderMap']
        if user_parameter_to_col_map is not None:
            parameter_to_col_map.update(user_parameter_to_col_map)

        # tensor properties are computed from the tensors interpolated along the fibers, the others sampled from their image
        sources = property_sources(properties_to_profile, input_is_dti, parameter_to_col_map)
        for prop, (kind, column, _) in sources.items():
            logger(f"Property {prop}: " + (f"computed from the tensors of column '{column}'" if kind == 'tensor' else f"image of column '{column}'"))
        needed_columns = [parameter_to_col_map['Case ID']] + sorted({column for _, column, _ in sources.values()})
        if use_displacement_field:
            needed_columns.append(parameter_to_col_map['Deformation Field'])
        missing = [column for column in needed_columns if column not in df.columns]
        if len(missing) > 0:
            raise Exception(f"Columns {missing} are not in the datasheet {path_to_csv}")

        # tract geometry (atlas space) is the same for all subjects: mask, plane, arc lengths and sample positions
        parameterized_fibers_path = Path(output_base_dir).joinpath('parameterized_fibers')
        parameterized_fibers_path.mkdir(parents=True, exist_ok=True)
        use_mask = mask is not None and str(mask).strip() != ''
        tract_infos = []
        for tract in tracts:
            tract_name_stem: str = Path(tract).stem
            if os.path.isabs(tract):
                tract_absolute_filename = Path(tract)
            else:
                tract_absolute_filename = Path(atlas_path).joinpath(tract)  # concatenate the atlas path with the tract name
            logger(f"Preparing tract {tract_absolute_filename}")
            bundle = fibers.read_fibers(tract_absolute_filename)
            if use_mask:
                keep = fibers.fiber_mask_average(bundle, mask) > mask_threshold
                logger(f"Mask {mask}: {int(np.sum(keep))} of {bundle.number_of_fibers} fibers have an average mask value above {mask_threshold}")
                if not np.any(keep):
                    raise Exception(f"No fiber of tract {tract} is inside the mask {mask}")
                bundle = bundle.select(keep)
            arcs = fibers.stored_arc_lengths(bundle) if arc_length_source == 'stored' else None
            if arcs is not None:
                logger(f"Using the arc lengths stored in the tract ({fibers.STORED_ARC_LENGTH})")
                grid = fibers.profile_grid(arcs, step_size, rounded=True)
            else:
                if arc_length_source == 'stored':
                    logger(f"Tract has no stored arc lengths ({fibers.STORED_ARC_LENGTH}), computing them", common.Color.WARNING)
                origin, normal = fibers.find_plane(bundle, plane_of_origin)
                logger(f"Plane of origin ({plane_of_origin}) : origin {origin.tolist()}, normal {normal.tolist()}")
                arcs = fibers.arc_lengths(bundle, origin, normal)
                grid = fibers.profile_grid(arcs, step_size)

            parameterized_fiber_output_path: Path = parameterized_fibers_path.joinpath(tract_name_stem + "_parameterized.vtk")
            tract_signature = {'tract': file_stamp(tract_absolute_filename), 'mask': file_stamp(mask) if use_mask else None,
                               'settings': {k: self.protocol.get(k) for k in ('stepSize', 'arcLength', 'planeOfOrigin', 'maskThreshold')}}
            tract_signature_path = parameterized_fiber_output_path.with_suffix('.json')
            if parameterized_fiber_output_path.exists() and not overwrite and signature_matches(tract_signature_path, tract_signature):
                logger(f"Skipping parameterized fiber generation of tract {tract}")
            else:
                logger(f"Generating parameterized fibers for tract {tract}")
                fibers.write_parameterized_fibers(bundle, arcs, grid, parameterized_fiber_output_path)
                write_signature(tract_signature_path, tract_signature)
            tract_infos.append({'tract': tract, 'name': tract_name_stem, 'bundle': bundle, 'arcs': arcs, 'grid': grid,
                                'signature': tract_signature})

        profiles = {(info['name'], prop): {} for info in tract_infos for prop in properties_to_profile}  # subject id -> profile values
        settings_text = json.dumps({k: self.protocol.get(k) for k in PROFILE_SETTINGS}, sort_keys=True, default=str)
        for info in tract_infos:  # the part of the record hash shared by all subjects
            info['record_text'] = json.dumps([info['signature'], ['{:.6g}'.format(a) for a in info['grid']]], sort_keys=True, default=str)
        record_dir = Path(output_base_dir).joinpath(RECORD_DIR)
        record_dir.mkdir(parents=True, exist_ok=True)
        record_names = set(os.listdir(record_dir))  # listed once: the records of the subjects of a previous run
        listings = {}  # folder of the .fvp of a tract and property -> names of its files, listed once

        def listing(folder):
            if folder not in listings:
                folder.mkdir(parents=True, exist_ok=True)
                listings[folder] = set(os.listdir(folder))
            return listings[folder]

        pool = ThreadPoolExecutor(READ_THREADS)  # the .fvp of a subject are read in parallel (network file systems)
        for row_index, row in df.iterrows():
            subject_id = str(row[parameter_to_col_map['Case ID']])
            displacement_field = None
            images = {}  # images of this subject, read once for all tracts
            subject_properties = []  # properties with an image for this subject (empty datasheet cell: not profiled)
            for prop in properties_to_profile:
                image_path = row[sources[prop][1]]
                if isinstance(image_path, str) and image_path.strip() != '':
                    subject_properties.append(prop)
                else:
                    logger(f"No image for {prop} of subject {subject_id} (column '{sources[prop][1]}' is empty), {prop} is not profiled", common.Color.WARNING)
            if len(subject_properties) == 0:
                continue
            # input files of the subject, stat'ed once for all tracts and properties
            stamps = {}
            for prop in subject_properties:
                column = sources[prop][1]
                if column not in stamps:
                    stamps[column] = file_stamp(row[column])
            displacement_stamp = file_stamp(row[parameter_to_col_map['Deformation Field']]) if use_displacement_field else None
            stamp_texts = {column: json.dumps(s, sort_keys=True) for column, s in stamps.items()}
            displacement_text = json.dumps(displacement_stamp, sort_keys=True)

            record_path = record_dir.joinpath(f'{subject_id}.npz')
            record = read_record(record_path) if not overwrite and record_path.name in record_names else {}
            entries = {}  # record key -> (hash, profile values) of the profiles of this subject
            pending = []  # profiles not in the record: from the .fvp of a previous run, or computed
            for info in tract_infos:
                for prop in subject_properties:
                    kind, column, scalar_name = sources[prop]
                    key = record_key(info['name'], prop)
                    profile_hash = hashlib.sha1('\n'.join([prop, kind, column, str(scalar_name), stamp_texts[column], displacement_text,
                                                           info['record_text'], settings_text]).encode()).hexdigest()
                    stored = record.get(key)
                    if stored is not None and stored[0] == profile_hash and len(stored[1]) == len(info['grid']):
                        entries[key] = stored
                        profiles[(info['name'], prop)][subject_id] = stored[1]
                    else:
                        pending.append((info, prop, key, profile_hash))
            number_from_record = len(entries)

            candidates, todo_by_tract = [], {}
            for info, prop, key, profile_hash in pending:
                tract = info['tract']
                tract_output_path: Path = Path(output_base_dir).joinpath(prop).joinpath(info['name'])
                profile_name = f'{subject_id}_' + Path(tract).name.replace('_extracted_done', f'_{prop}_profile')  ## file name only, tract may be an absolute path
                fiber_output_path = tract_output_path.joinpath(profile_name)
                fvp_output_path = tract_output_path.joinpath(Path(profile_name).stem + '.fvp')
                kind, column, scalar_name = sources[prop]
                signature = {'property': prop, 'source': [kind, column, scalar_name], 'image': stamps[column],
                             'displacement_field': displacement_stamp,
                             'tract': info['signature'],
                             'settings': {k: self.protocol.get(k) for k in PROFILE_SETTINGS}}
                item = (info, prop, key, profile_hash, fiber_output_path, fvp_output_path, signature)
                if not overwrite and fvp_output_path.name in listing(tract_output_path):
                    candidates.append(item)
                else:
                    todo_by_tract.setdefault(info['name'], []).append(item)
            number_from_fvp = 0
            for item, values in zip(candidates, pool.map(lambda c: reuse_fvp(c[5], c[6], c[0]['grid']), candidates)):
                info, prop, key, profile_hash = item[:4]
                if values is not None:
                    entries[key] = (profile_hash, values)
                    profiles[(info['name'], prop)][subject_id] = values
                    number_from_fvp += 1
                else:
                    logger(f"Recomputing the profile of {prop} for subject {subject_id} and tract {info['tract']}: its settings or input files changed since {item[5]} was computed")
                    todo_by_tract.setdefault(info['name'], []).append(item)

            for info in tract_infos:
                todo = todo_by_tract.get(info['name'], [])
                if len(todo) == 0:
                    continue
                tract = info['tract']
                if use_displacement_field and displacement_field is None:
                    displacement_field_path = row[parameter_to_col_map['Deformation Field']]
                    if not isinstance(displacement_field_path, str) or displacement_field_path.strip() == '':
                        raise Exception(f"No deformation field for subject {subject_id} (column '{parameter_to_col_map['Deformation Field']}')")
                    displacement_field = fibers.Image(displacement_field_path)
                logger(f"Sampling {', '.join(item[1] for item in todo)} of subject {subject_id} along tract {tract}")
                sampled = {}
                tensor_scalars = {}  # column -> scalars of the tensors sampled along this tract
                for item in todo:
                    prop = item[1]
                    kind, column, scalar_name = sources[prop]
                    if (kind, column) not in images:
                        images[(kind, column)] = fibers.TensorImage(row[column]) if kind == 'tensor' else fibers.Image(row[column])
                    if kind == 'tensor':
                        if column not in tensor_scalars:
                            tensors = fibers.sample_tensors(info['bundle'], images[(kind, column)], displacement_field, tensor_interpolation)
                            tensor_scalars[column] = fibers.tensor_scalars(tensors)
                        sampled[prop] = tensor_scalars[column][scalar_name]
                    else:
                        sampled[prop] = fibers.sample_scalar(info['bundle'], images[(kind, column)], displacement_field)

                for _, prop, key, profile_hash, fiber_output_path, fvp_output_path, signature in todo:
                    subject_bundle = fibers.FiberBundle(info['bundle'].points, info['bundle'].offsets, {prop: sampled[prop], 'ArcLength': info['arcs']})
                    if noNaN:
                        keep = fibers.fibers_without_nan(info['bundle'], sampled[prop])
                        if not np.all(keep):
                            logger(f"Removing {int(np.sum(~keep))} fibers with NaN {prop} values for subject {subject_id} and tract {tract}")
                        subject_bundle = subject_bundle.select(keep)
                    if write_fiber_files:
                        fibers.write_fibers(subject_bundle, fiber_output_path)
                    profile = fibers.gaussian_profile(subject_bundle.point_data['ArcLength'], subject_bundle.point_data[prop], info['grid'], support_bandwidth)
                    fibers.write_fvp(fvp_output_path, profile, prop, step_size, support_bandwidth)
                    write_signature(fvp_output_path.with_suffix('.json'), signature)
                    entries[key] = (profile_hash, profile['mean'])
                    profiles[(info['name'], prop)][subject_id] = profile['mean']
                    if cleanupMethod == CleanupMethod.DURING:
                        if write_fiber_files:
                            fiber_output_path.unlink()
                        fvp_output_path.unlink()
                        fvp_output_path.with_suffix('.json').unlink()

            number_computed = len(entries) - number_from_record - number_from_fvp
            if number_from_record < len(entries):  # profiles of other tracts or properties of a previous run are kept
                write_record(record_path, {**record, **entries})
            logger(f"Subject {subject_id}: {number_from_record} profiles reused from {RECORD_DIR}, {number_from_fvp} from .fvp files, {number_computed} computed")
        pool.shutdown()

        # save the profiles of all subjects (same arc length samples) to a csv per tract and property
        for prop in properties_to_profile:
            if not any(profiles[(info['name'], prop)] for info in tract_infos):
                logger(f"No subject has an image for {prop}, no profile table is written for {prop}", common.Color.WARNING)
                continue
            Path(output_base_dir).joinpath(prop).mkdir(parents=True, exist_ok=True)
            for info in tract_infos:
                subject_profiles = profiles[(info['name'], prop)]
                if result_case_columnwise:
                    tract_stat_df = pd.DataFrame({"Arc Length": info['grid'], **subject_profiles})
                else:
                    tract_stat_df = pd.DataFrame([[subject_id] + list(values) for subject_id, values in subject_profiles.items()],
                                                 columns=['case_id'] + ['{:g}'.format(a) for a in info['grid']])
                tract_stat_df.to_csv(Path(output_base_dir).joinpath(prop).joinpath(f"{info['name']}_{prop}.csv"), index=False, float_format='%.6g')  ## same precision as the .fvp files

        if cleanupMethod == CleanupMethod.END or cleanupMethod == CleanupMethod.DURING:  # the records are kept
            for prop in properties_to_profile:
                for info in tract_infos:
                    d = Path(output_base_dir).joinpath(prop).joinpath(info['name'])
                    if d.exists():
                        shutil.rmtree(d)
        self.result['output']['success'] = True
        return self.result




