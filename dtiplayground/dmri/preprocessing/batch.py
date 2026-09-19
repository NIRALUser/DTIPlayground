#   Batch processing of cohorts with dmriprep
#
#   A batch lives in its output directory:
#       <out>/batch/batch.yml            settings (config directory, dmriprep command, version)
#       <out>/batch/manifest.tsv         one row per dataset: id, images, output folder, protocol, overrides
#       <out>/batch/protocols/<id>.yml   protocol of each dataset (with its overrides, e.g. the phase encoding)
#       <out>/batch/skipped.tsv          runs that are not processed, and why
#       <out>/<dataset folder>/          output of `dmriprep run` for the dataset, plus batch_status.yml / batch_log.txt
#
#   The datasets come from a BIDS dataset (plan_bids) or a datasheet (plan_manifest). Each dataset is processed by
#   `dmriprep batch-task <out> <id>` in its own process, locally (run_local, several at a time) or as a task of a
#   SLURM job array (write_slurm).

import copy
import csv
import datetime
import fnmatch
import hashlib
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

import dtiplayground
from dtiplayground.config import INFO as info
from dtiplayground.dmri.common import bids

MANIFEST_COLUMNS = ['id', 'subject', 'session', 'output_dir', 'protocol', 'output_file_base', 'image_1', 'image_2',
                    'overrides']
STATUS_FILE = 'batch_status.yml'
LOG_FILE = 'batch_log.txt'


class BatchError(Exception):
    pass


def _read_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def _write_yaml(data, path):
    with open(path, 'w') as f:
        yaml.safe_dump(data, f, sort_keys=False)


############################## protocols

def parse_protocol_specs(specs):
    """[(pattern, protocol path)] from 'protocol.yml' or 'PATTERN=protocol.yml' arguments (first match wins; a plain
    path matches everything)."""
    result = []
    for spec in specs or []:
        pattern, sep, path = spec.rpartition('=')
        if not sep:
            pattern, path = '*', spec
        path = os.path.abspath(Path(path).expanduser())
        if not Path(path).is_file():
            raise BatchError('Protocol file not found: {}'.format(path))
        result.append((pattern, path))
    return result


def select_protocol(specs, names):
    """First protocol whose pattern matches one of *names* (dataset id, scan names)."""
    for pattern, path in specs:
        if any(fnmatch.fnmatchcase(n, pattern) for n in names):
            return path
    return None


def _module_attributes(module_name, config_dir):
    """process_attributes of a module (system or user module folder)."""
    folders = [Path(dtiplayground.__file__).resolve().parent.joinpath('dmri/preprocessing/modules'),
               Path(config_dir).joinpath('modules/dmriprep')]
    for folder in folders:
        fn = folder.joinpath(module_name, module_name + '.yml')
        if fn.is_file():
            return _read_yaml(fn).get('process_attributes') or []
    return []


class DefaultProtocol:
    """Protocol to generate (dmriprep make-protocols -d MODULES) for each acquisition of the batch; no modules: the
    default pipeline of the protocol template."""

    def __init__(self, modules=None, b0_threshold=10, images=1):
        self.modules = list(modules or [])
        self.b0_threshold = b0_threshold
        self.images = images  # number of input images: the default pipeline of two has SUSCEPTIBILITY_Correct

    def module_names(self):
        if self.modules:
            return self.modules
        from dtiplayground.dmri.common.pipeline import default_pipeline
        template = Path(dtiplayground.__file__).resolve().parent.joinpath('dmri/preprocessing/templates/protocol_template.yml')
        return default_pipeline(_read_yaml(template), self.images)

    def for_pairs(self):
        """The default protocol of the phase encoding pairs (only the default pipeline adapts to two images)."""
        return None if self.modules else DefaultProtocol(None, self.b0_threshold, images=2)

    def __str__(self):
        return 'default protocol ({})'.format(', '.join(self.module_names()))


def protocol_modules(protocol):
    """Module names of the pipeline of a protocol file or DefaultProtocol."""
    if isinstance(protocol, DefaultProtocol):
        return protocol.module_names()
    return [name for name, _ in _read_yaml(protocol)['pipeline']]


def protocol_needs_pair(protocol, config_dir):
    """Whether the pipeline of the protocol has a module that needs two input images (e.g. SUSCEPTIBILITY_Correct)."""
    for name in protocol_modules(protocol):
        attributes = _module_attributes(name, config_dir)
        if 'multi_input' in attributes and 'single_input' not in attributes:
            return True
    return False


def apply_overrides(protocol, overrides):
    """Copy of *protocol* with the module parameters of *overrides* ({module: {parameter: value}}) set."""
    protocol = copy.deepcopy(protocol)
    for module_name, parameters in (overrides or {}).items():
        found = False
        for name, entry in protocol['pipeline']:
            if name == module_name:
                entry.setdefault('protocol', {}).update(parameters)
                found = True
        if not found:
            raise BatchError('Override of module {} which is not in the pipeline'.format(module_name))
    return protocol


def _hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


def inputs_hash(dataset):
    """Hash of the inputs of a dataset: its images (in order) and its output file base."""
    return _hash({'images': list(dataset['images']), 'output_file_base': dataset.get('output_file_base') or ''})


def settings_hash(protocol, dataset):
    """Hash of what a dataset's result depends on: the pipeline and the io settings of its protocol, its input images
    (in order) and its output file base. A dataset done with other settings is outdated."""
    io = protocol.get('io', {})
    relevant = {'pipeline': protocol['pipeline'],
                'io': {k: io.get(k) for k in ('baseline_threshold', 'output_format', 'no_output_image')},
                'inputs': inputs_hash(dataset)}
    return _hash(relevant)


############################## image signatures (compatibility check)

def image_signature(image_path):
    """Short description of the acquisition of a DWI: dimensions, voxel size, volumes, shells."""
    import numpy as np
    path = Path(image_path)
    try:
        if path.name.endswith('.nrrd') or path.name.endswith('.nhdr'):
            import nrrd
            header = nrrd.read_header(str(path))
            sizes = [int(s) for s in header['sizes']]
            directions = np.array([[float(x) for x in d] for d in header['space directions'] if d is not None])
            spacing = np.linalg.norm(directions, axis=1)
            bmax = float(header.get('DWMRI_b-value', 0))
            grads = [np.array([float(x) for x in header[k].split()]) for k in sorted(header) if k.startswith('DWMRI_gradient_')]
            bvals = np.array([bmax * float(np.sum(g ** 2)) for g in grads])
            dims = [s for s, d in zip(sizes, header['space directions']) if d is not None]
            volumes = len(bvals)
        else:
            import nibabel as nib
            header = nib.load(str(path)).header
            shape = header.get_data_shape()
            dims, spacing = list(shape[:3]), np.array(header.get_zooms()[:3])
            volumes = shape[3] if len(shape) > 3 else 1
            bval = path.with_name(path.name.split('.')[0] + '.bval')
            bvals = np.loadtxt(str(bval)).ravel() if bval.is_file() else np.array([])
        shells = sorted({int(round(b / 50.0) * 50) for b in bvals}) if len(bvals) else []
        return '{} {}mm {}vol b={}'.format('x'.join(map(str, dims)), 'x'.join('{:g}'.format(round(float(s), 2)) for s in spacing),
                                           volumes, ','.join(map(str, shells)))
    except Exception as e:
        return 'unreadable ({})'.format(e)


############################## planning

def _dataset(ds_id, images, output_dir, protocol, subject='', session='', overrides=None, output_file_base=None):
    return {'id': ds_id, 'subject': subject, 'session': session, 'output_dir': output_dir, 'protocol': protocol,
            'output_file_base': output_file_base or '', 'images': [str(i) for i in images],
            'overrides': overrides or {}}


def plan_bids(bids_dir, protocol_specs, config_dir, participants=None, sessions=None):
    """Datasets of a BIDS dataset: every DWI run, or the pairs of runs with opposite phase encoding when the protocol
    of the run needs two images. Returns (datasets, skipped [(name, reason)], notes)."""
    scans, skipped = bids.find_dwi(bids_dir, participants, sessions)
    skipped = [(Path(p).name, r) for p, r in skipped]
    notes = []
    groups = {}
    for s in scans:
        groups.setdefault(bids.group_key(s), []).append(s)
    datasets = []
    for group in groups.values():
        names = [s['name'] for s in group]
        protocol = select_protocol(protocol_specs, names)
        if protocol is None:
            skipped += [(n, 'no protocol matches') for n in names]
            continue
        entities = group[0]['entities']
        folder = ['sub-' + entities['sub']] + (['ses-' + entities['ses']] if 'ses' in entities else []) + ['dwi']
        if isinstance(protocol, DefaultProtocol) and protocol.for_pairs() is not None and len(group) > 1:
            ## default pipeline: the runs with opposite phase encodings are processed as pairs with susceptibility
            ## correction, the others on their own
            pairs, problem = bids.make_pairs(group)
            if problem is None:
                protocol = protocol.for_pairs()
            else:
                notes.append('{}: processed as single runs ({})'.format(', '.join(names), problem))
        if not protocol_needs_pair(protocol, config_dir):
            for s in group:
                datasets.append(_dataset(s['name'][:-len('_dwi')], [s['path']], '/'.join(folder + [s['name'][:-len('_dwi')]]),
                                         protocol, entities['sub'], entities.get('ses', '')))
            continue
        pairs, problem = bids.make_pairs(group)
        if problem:
            skipped += [(n, 'protocol needs a phase encoding pair: ' + problem) for n in names]
            continue
        for first, second in pairs:
            ds_id = bids.dataset_id([first, second])
            overrides = {}
            axis = bids.phase_encoding(first)[0]
            readout = bids.readout_time([first, second])
            times = [s['sidecar'].get('TotalReadoutTime') for s in (first, second)]
            if None not in times and abs(times[0] - times[1]) > 0.01 * max(times):
                notes.append('{}: TotalReadoutTime differs between the two runs ({:g}, {:g}), their mean is used'.format(ds_id, *times))
            parameters = {'phaseEncodingAxis': axis}
            if readout is not None:
                parameters['phaseEncodingValue'] = round(readout, 6)
            else:
                notes.append('{}: no TotalReadoutTime in the sidecars, the protocol value is used'.format(ds_id))
            if 'SUSCEPTIBILITY_Correct' in protocol_modules(protocol):
                overrides['SUSCEPTIBILITY_Correct'] = parameters
            datasets.append(_dataset(ds_id, [first['path'], second['path']], '/'.join(folder + [ds_id]), protocol,
                                     entities['sub'], entities.get('ses', ''), overrides, ds_id + '_dwi'))
    _make_unique_ids(datasets)
    datasets.sort(key=lambda d: d['id'])
    return datasets, skipped, notes


def _make_unique_ids(datasets):
    seen = {}
    for d in datasets:
        seen.setdefault(d['id'], []).append(d)
    for ds_id, same in seen.items():
        if len(same) > 1:
            for n, d in enumerate(same, 1):
                d['id'] = '{}_pair-{}'.format(ds_id, n)
                d['output_dir'] = str(Path(d['output_dir']).parent.joinpath(d['id']))
                if d['output_file_base']:
                    d['output_file_base'] = d['id'] + '_dwi'


def read_datasheet(path):
    """Rows of a datasheet (TSV or CSV) as dicts."""
    text = Path(path).read_text()
    dialect = 'excel-tab' if (Path(path).suffix.lower() == '.tsv' or '\t' in text.splitlines()[0]) else 'excel'
    return list(csv.DictReader(text.splitlines(), dialect=dialect))


def plan_manifest(datasheet, protocol_specs):
    """Datasets of a datasheet with the columns id, image_1 and optionally image_2, protocol, output_dir,
    output_file_base, overrides (JSON: {module: {parameter: value}}). Relative paths are relative to the datasheet."""
    base = Path(os.path.abspath(datasheet)).parent
    resolve = lambda p: os.path.normpath(str(base / Path(p).expanduser())) if p else ''
    datasets, skipped = [], []
    for n, row in enumerate(read_datasheet(datasheet), 2):
        row = {k.strip(): (v or '').strip() for k, v in row.items() if k}
        if not row.get('id') or not row.get('image_1'):
            raise BatchError('{} line {}: id and image_1 are required'.format(datasheet, n))
        images = [resolve(row['image_1'])] + ([resolve(row['image_2'])] if row.get('image_2') else [])
        missing = [i for i in images if not Path(i).exists()]
        if missing:
            skipped.append((row['id'], 'missing ' + ', '.join(missing)))
            continue
        protocol = resolve(row['protocol']) if row.get('protocol') else select_protocol(protocol_specs, [row['id']])
        if protocol is None:
            skipped.append((row['id'], 'no protocol matches'))
            continue
        overrides = json.loads(row['overrides']) if row.get('overrides') else {}
        datasets.append(_dataset(row['id'], images, row.get('output_dir') or row['id'], protocol,
                                 row.get('subject', ''), row.get('session', ''), overrides, row.get('output_file_base')))
    ids = [d['id'] for d in datasets]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise BatchError('Duplicate ids in {}: {}'.format(datasheet, ', '.join(duplicates)))
    return datasets, skipped, []


def generate_default_protocols(out, datasets, config_dir, echo=print):
    """Replaces the DefaultProtocol of the datasets by protocol files generated with make-protocols, one per
    acquisition (default parameters can depend on the image, e.g. the voxel size), from one dataset of each."""
    from dtiplayground.dmri.preprocessing.app import DMRIPrepApp
    folder = batch_dir(out).joinpath('default_protocols')
    groups = {}
    for d in datasets:
        if isinstance(d['protocol'], DefaultProtocol):
            key = (tuple(d['protocol'].module_names()), d['protocol'].b0_threshold,
                   tuple(image_signature(i) for i in d['images']))
            groups.setdefault(key, []).append(d)
    for n, (key, members) in enumerate(sorted(groups.items(), key=lambda kv: kv[1][0]['id']), 1):
        folder.mkdir(parents=True, exist_ok=True)
        fn = folder.joinpath('protocol_{}.yml'.format(n))
        default = members[0]['protocol']
        echo('Generating {} for {} dataset(s) from {}'.format(default, len(members), members[0]['id']))
        DMRIPrepApp(config_dir).makeProtocols({'input_images': members[0]['images'], 'module_list': default.modules,
                                               'output': str(fn), 'b0_threshold': default.b0_threshold,
                                               'output_format': None, 'no_output_image': False,
                                               'global_variables': {}})
        for d in members:
            d['protocol'] = str(fn)


############################## batch folder

def batch_dir(out):
    return Path(out).joinpath('batch')


def write_batch(out, datasets, skipped, settings):
    """Writes the manifest, the protocols of the datasets, the skipped runs and the batch settings."""
    out = Path(os.path.abspath(out))
    bdir = batch_dir(out)
    bdir.joinpath('protocols').mkdir(parents=True, exist_ok=True)
    for d in datasets:
        protocol = apply_overrides(_read_yaml(d['protocol']), d['overrides'])
        protocol_fn = bdir.joinpath('protocols', d['id'] + '.yml')
        _write_yaml(protocol, protocol_fn)
    with open(bdir.joinpath('manifest.tsv'), 'w', newline='') as f:
        w = csv.writer(f, dialect='excel-tab')
        w.writerow(MANIFEST_COLUMNS)
        for d in datasets:
            w.writerow([d['id'], d['subject'], d['session'], d['output_dir'], d['protocol'], d['output_file_base'],
                        d['images'][0], d['images'][1] if len(d['images']) > 1 else '',
                        json.dumps(d['overrides']) if d['overrides'] else ''])
    with open(bdir.joinpath('skipped.tsv'), 'w', newline='') as f:
        w = csv.writer(f, dialect='excel-tab')
        w.writerow(['name', 'reason'])
        w.writerows(skipped)
    settings = dict(settings, dmriprep_version=info['dmriprep']['version'], created=_now())
    _write_yaml(settings, bdir.joinpath('batch.yml'))


def write_dataset_description(out, bids_dir):
    """dataset_description.json of the BIDS derivatives folder."""
    fn = Path(out).joinpath('dataset_description.json')
    description = {'Name': 'dmriprep outputs of {}'.format(Path(bids_dir).resolve().name),
                   'BIDSVersion': '1.9.0', 'DatasetType': 'derivative',
                   'GeneratedBy': [{'Name': 'dmriprep', 'Version': info['dmriprep']['version'],
                                    'CodeURL': 'https://github.com/NIRALUser/DTIPlayground'}],
                   'SourceDatasets': [{'URL': 'file://' + os.path.abspath(bids_dir)}]}
    fn.write_text(json.dumps(description, indent=2) + '\n')


def load_manifest(out):
    fn = batch_dir(out).joinpath('manifest.tsv')
    if not fn.is_file():
        raise BatchError('No batch in {} (no batch/manifest.tsv)'.format(out))
    datasets = []
    for row in read_datasheet(fn):
        row['images'] = [row['image_1']] + ([row['image_2']] if row.get('image_2') else [])
        row['overrides'] = json.loads(row['overrides']) if row.get('overrides') else {}
        datasets.append(row)
    return datasets


def load_settings(out):
    return _read_yaml(batch_dir(out).joinpath('batch.yml'))


def dataset_protocol(out, ds_id):
    return batch_dir(out).joinpath('protocols', ds_id + '.yml')


############################## status

def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def read_status(out, dataset):
    fn = Path(out).joinpath(dataset['output_dir'], STATUS_FILE)
    if not fn.is_file():
        return {'state': 'pending'}
    try:
        return _read_yaml(fn) or {'state': 'pending'}
    except Exception:
        return {'state': 'pending'}


def write_status(out, dataset, **status):
    folder = Path(out).joinpath(dataset['output_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder.joinpath(STATUS_FILE + '.tmp')
    _write_yaml(status, tmp)
    tmp.replace(folder.joinpath(STATUS_FILE))


def _running_elsewhere(status):
    """Whether a 'running' status belongs to a process that is still alive (this host: pid check; SLURM: squeue)."""
    if status.get('slurm_job_id'):
        try:
            r = subprocess.run(['squeue', '-h', '-j', str(status['slurm_job_id'])], capture_output=True, text=True, timeout=30)
            return r.returncode == 0 and bool(r.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            return True  # can't tell: assume it is running
    if status.get('host') == socket.gethostname() and status.get('pid'):
        try:
            os.kill(int(status['pid']), 0)
            return True
        except (OSError, ValueError):
            return False
    return True


def current_state(out, dataset):
    """State of a dataset: pending, running, done, failed, interrupted, or outdated (done with other settings: protocol,
    input images)."""
    status = read_status(out, dataset)
    state = status.get('state', 'pending')
    expected = settings_hash(_read_yaml(dataset_protocol(out, dataset['id'])), dataset)
    if state == 'done' and status.get('settings_hash') != expected:
        return 'outdated', status
    if state == 'running' and not _running_elsewhere(status):
        return 'interrupted', status
    return state, status


def summarize(out):
    """(rows, counts): state of every dataset of the batch."""
    rows, counts = [], {}
    for d in load_manifest(out):
        state, status = current_state(out, d)
        counts[state] = counts.get(state, 0) + 1
        rows.append({'id': d['id'], 'state': state, 'started': status.get('started', ''),
                     'finished': status.get('finished', ''), 'seconds': status.get('seconds', ''),
                     'host': status.get('host', ''), 'slurm_job_id': status.get('slurm_job_id', ''),
                     'error': status.get('error', ''), 'output_dir': d['output_dir']})
    with open(batch_dir(out).joinpath('status.tsv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ['id'], dialect='excel-tab')
        w.writeheader()
        w.writerows(rows)
    return rows, counts


def select_datasets(out, only=None, rerun=False):
    """Datasets to process: those not done (or all with *rerun*), restricted to the ids of *only*; datasets running in
    another process are left out, unless *only* names them. Returns (selected, running)."""
    selected, running = [], []
    only = set(only) if only else None
    for d in load_manifest(out):
        if only is not None and d['id'] not in only:
            continue
        state, _ = current_state(out, d)
        if state == 'running' and only is None:
            running.append(d)
        elif rerun or state != 'done':
            selected.append(d)
    return selected, running


############################## execution

def task_command(out, ds_id, threads=None, overwrite=False):
    """Command line of `dmriprep batch-task` for a dataset, with the dmriprep of the batch settings."""
    settings = load_settings(out)
    command = list(settings['command']) + ['--config-dir', settings['config_dir'], '--no-verbosity',
                                           'batch-task', os.path.abspath(out), ds_id]
    if threads:
        command += ['-t', str(threads)]
    if overwrite:
        command.append('--overwrite')
    return command


def run_task(out, ds_id, config_dir, threads=None, overwrite=False):
    """Processes one dataset of the batch in this process (dmriprep batch-task); returns the exit code."""
    from dtiplayground.dmri.preprocessing.app import DMRIPrepApp
    out = Path(os.path.abspath(out))
    dataset = next((d for d in load_manifest(out) if d['id'] == ds_id), None)
    if dataset is None:
        raise BatchError('No dataset {} in the batch {}'.format(ds_id, out))
    protocol_fn = dataset_protocol(out, ds_id)
    ## the results of the modules are reused when their protocol is unchanged, but that does not check the input
    ## images: recompute everything when the inputs changed since the previous run of the dataset
    previous = read_status(out, dataset)
    if previous.get('state', 'pending') != 'pending' and previous.get('inputs_hash') != inputs_hash(dataset) and not overwrite:
        print('The input images of {} changed since its previous run: all modules are recomputed'.format(ds_id))
        overwrite = True
    status = {'state': 'running', 'settings_hash': settings_hash(_read_yaml(protocol_fn), dataset),
              'inputs_hash': inputs_hash(dataset), 'started': _now(), 'host': socket.gethostname(), 'pid': os.getpid()}
    if os.environ.get('SLURM_JOB_ID'):
        status['slurm_job_id'] = os.environ['SLURM_JOB_ID']
    write_status(out, dataset, **status)
    t0 = time.time()
    options = {
        'config_dir': config_dir,
        'input_image_paths': dataset['images'],
        'protocol_path': str(protocol_fn),
        'output_dir': str(out.joinpath(dataset['output_dir'])),
        'default_protocols': None,
        'num_threads': threads,
        'execution_id': ds_id,
        'baseline_threshold': _read_yaml(protocol_fn)['io'].get('baseline_threshold', 10),
        'output_format': None,
        'output_file_base': dataset.get('output_file_base') or None,
        'no_output_image': False,
        'overwrite': overwrite,
        'global_variables': {},
    }
    code, error = 0, ''
    try:
        DMRIPrepApp(config_dir).run(options)
    except SystemExit as e:  # the pipeline exits on a failure
        code = e.code if isinstance(e.code, int) else 1
        error = 'pipeline failed (see log.txt)' if code else ''
    except BaseException as e:
        code, error = 1, '{}: {}'.format(type(e).__name__, e)
    status.update(state='done' if code == 0 else 'failed', finished=_now(), seconds=int(time.time() - t0),
                  exit_code=code)
    if error:
        status['error'] = error[-500:]
    write_status(out, dataset, **status)
    return code


def run_local(out, datasets, jobs=1, threads=None, overwrite=False, echo=print):
    """Runs the datasets locally, *jobs* at a time, each in its own dmriprep process. Returns the counts of states."""
    out = Path(os.path.abspath(out))
    total, finished, counts = len(datasets), [0], {}

    def work(d):
        folder = out.joinpath(d['output_dir'])
        folder.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        with open(folder.joinpath(LOG_FILE), 'w') as log:
            code = subprocess.run(task_command(out, d['id'], threads, overwrite), stdout=log,
                                  stderr=subprocess.STDOUT).returncode
        state = 'done' if code == 0 else 'failed'
        finished[0] += 1
        counts[state] = counts.get(state, 0) + 1
        echo('[{}/{}] {} {} ({:.0f} s){}'.format(finished[0], total, state, d['id'], time.time() - t0,
                                                 '' if code == 0 else ' - see ' + str(folder.joinpath(LOG_FILE))))
        return state

    with ThreadPoolExecutor(max_workers=max(1, int(jobs))) as pool:
        list(pool.map(work, datasets))
    return counts


def write_slurm(out, datasets, threads=None, overwrite=False, time_limit='24:00:00', memory='16G', partition=None,
                setup=None, extra=None, max_parallel=None, submit=False, echo=print):
    """SLURM job array script with one task per dataset (the dataset ids are in batch/slurm_ids.txt); submitted with
    sbatch when *submit*. Returns the script path."""
    out = Path(os.path.abspath(out))
    bdir = batch_dir(out)
    bdir.joinpath('slurm_logs').mkdir(parents=True, exist_ok=True)
    ids_fn = bdir.joinpath('slurm_ids.txt')
    ids_fn.write_text(''.join(d['id'] + '\n' for d in datasets))
    if not threads:  # the largest num_threads of the protocols of the datasets
        threads = max([int(_read_yaml(dataset_protocol(out, d['id']))['io'].get('num_threads') or 1) for d in datasets] + [1])
    threads = int(threads)
    command = task_command(out, '"$ID"', threads, overwrite)
    command_str = ' '.join(c if c == '"$ID"' else shlex.quote(c) for c in command)
    array = '1-{}'.format(len(datasets)) + ('%{}'.format(int(max_parallel)) if max_parallel else '')
    lines = ['#!/bin/bash',
             '#SBATCH --job-name=dmriprep-batch',
             '#SBATCH --array={}'.format(array),
             '#SBATCH --ntasks=1',
             '#SBATCH --cpus-per-task={}'.format(threads),
             '#SBATCH --mem={}'.format(memory),
             '#SBATCH --time={}'.format(time_limit),
             '#SBATCH --output={}/slurm_logs/%A_%a.log'.format(bdir)]
    if partition:
        lines.append('#SBATCH --partition={}'.format(partition))
    lines += ['#SBATCH {}'.format(e) for e in (extra or [])]
    lines += ['', '## generated by dmriprep {} on {}'.format(info['dmriprep']['version'], _now())]
    lines += [setup] if setup else []
    lines += ['ID=$(sed -n "${SLURM_ARRAY_TASK_ID}p" ' + shlex.quote(str(ids_fn)) + ')',
              'echo "dataset $ID on $(hostname)"',
              command_str, '']
    script = bdir.joinpath('slurm_array.sh')
    script.write_text('\n'.join(lines))
    script.chmod(0o755)
    echo('SLURM job array script: {} ({} task(s))'.format(script, len(datasets)))
    if submit:
        r = subprocess.run(['sbatch', str(script)], capture_output=True, text=True)
        if r.returncode != 0:
            raise BatchError('sbatch failed: {}{}'.format(r.stdout, r.stderr))
        echo(r.stdout.strip())
    else:
        echo('Submit it with: sbatch {}'.format(script))
    return script


def dmriprep_command():
    """Command running the dmriprep of this process (installed script or source tree)."""
    return [sys.executable, os.path.abspath(sys.argv[0])]
