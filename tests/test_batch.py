#   Tests of the BIDS discovery and the batch planning of dmriprep (no processing):
#       python -m unittest discover -s tests

import json
import tempfile
import unittest
from pathlib import Path

import nibabel as nib
import numpy as np
import yaml

from dtiplayground.dmri.common import bids
from dtiplayground.dmri.preprocessing import batch

RAS = np.diag([2.0, 2.0, 2.0, 1.0])
LAS = np.diag([-2.0, 2.0, 2.0, 1.0])


def write_dwi(folder, name, affine=RAS, sidecar=None, volumes=3, gradients=True):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(np.zeros((4, 4, 4, volumes), dtype=np.float32), affine), str(folder / (name + '.nii.gz')))
    if gradients:
        (folder / (name + '.bval')).write_text(' '.join(['0'] + ['1000'] * (volumes - 1)) + '\n')
        (folder / (name + '.bvec')).write_text('\n'.join(' '.join(['0'] + ['1'] * (volumes - 1)) for _ in range(3)) + '\n')
    if sidecar is not None:
        (folder / (name + '.json')).write_text(json.dumps(sidecar))
    return folder / (name + '.nii.gz')


def write_protocol(path, modules):
    protocol = {'version': 0.1, 'io': {'baseline_threshold': 10, 'num_threads': 1, 'output_format': None,
                                       'no_output_image': False},
                'pipeline': [[m, {'options': {'overwrite': False, 'skip': False, 'write_image': False},
                                  'protocol': {'phaseEncodingAxis': 1, 'phaseEncodingValue': 0.0924}
                                  if m == 'SUSCEPTIBILITY_Correct' else {'method': 'fsl'}}] for m in modules]}
    with open(path, 'w') as f:
        yaml.safe_dump(protocol, f)
    return str(path)


class TestBidsNames(unittest.TestCase):
    def test_parse_and_build(self):
        entities, suffix = bids.parse_name('sub-01_ses-02_acq-x_dir-AP_run-1_dwi.nii.gz')
        self.assertEqual(entities, {'sub': '01', 'ses': '02', 'acq': 'x', 'dir': 'AP', 'run': '1'})
        self.assertEqual(suffix, 'dwi')
        self.assertEqual(bids.build_name({'run': '1', 'sub': '01', 'dir': 'PA'}, 'dwi'), 'sub-01_dir-PA_run-1_dwi')
        self.assertIsNone(bids.parse_name('dwi_scan.nii.gz'))
        self.assertIsNone(bids.parse_name('ses-1_dwi.nii.gz'))


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'study'

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_filters_and_skips(self):
        write_dwi(self.root / 'sub-01/ses-1/dwi', 'sub-01_ses-1_dwi')
        write_dwi(self.root / 'sub-02/dwi', 'sub-02_dwi')  # no session level
        write_dwi(self.root / 'sub-03/ses-1/dwi', 'sub-03_ses-1_dwi', gradients=False)
        (self.root / 'sub-04/ses-1/fmap').mkdir(parents=True)  # session without dwi
        scans, skipped = bids.find_dwi(self.root)
        self.assertEqual(sorted(s['name'] for s in scans), ['sub-01_ses-1_dwi', 'sub-02_dwi'])
        self.assertEqual([r for _, r in skipped], ['no .bval/.bvec'])
        scans, _ = bids.find_dwi(self.root, participants=['sub-02'])
        self.assertEqual([s['name'] for s in scans], ['sub-02_dwi'])
        scans, _ = bids.find_dwi(self.root, sessions=['1'])
        self.assertEqual([s['name'] for s in scans], ['sub-01_ses-1_dwi'])

    def test_sidecar_inheritance(self):
        (self.root).mkdir(parents=True)
        (self.root / 'dwi.json').write_text(json.dumps({'TotalReadoutTime': 0.05, 'Manufacturer': 'X'}))
        (self.root / 'acq-b_dwi.json').write_text(json.dumps({'TotalReadoutTime': 0.07}))
        write_dwi(self.root / 'sub-01/dwi', 'sub-01_acq-b_dwi', sidecar={'PhaseEncodingDirection': 'j-'})
        write_dwi(self.root / 'sub-01/dwi', 'sub-01_acq-c_dwi')
        scans = {s['name']: s for s in bids.find_dwi(self.root)[0]}
        self.assertEqual(scans['sub-01_acq-b_dwi']['sidecar'],
                         {'TotalReadoutTime': 0.07, 'Manufacturer': 'X', 'PhaseEncodingDirection': 'j-'})
        self.assertEqual(scans['sub-01_acq-c_dwi']['sidecar'], {'TotalReadoutTime': 0.05, 'Manufacturer': 'X'})


class TestPhaseEncoding(unittest.TestCase):
    def scan(self, ped=None, dir_label=None, axcodes=('R', 'A', 'S'), run='1'):
        entities = {'sub': '01', 'run': run}
        if dir_label:
            entities['dir'] = dir_label
        return {'name': bids.build_name(entities, 'dwi'), 'entities': entities, 'axcodes': axcodes,
                'sidecar': {'PhaseEncodingDirection': ped} if ped else {}}

    def test_sidecar_and_dir_label(self):
        self.assertEqual(bids.phase_encoding(self.scan('j-')), (1, -1, 'P'))
        self.assertEqual(bids.phase_encoding(self.scan('j')), (1, 1, 'A'))
        self.assertEqual(bids.phase_encoding(self.scan('i', axcodes=('L', 'A', 'S'))), (0, 1, 'L'))
        self.assertEqual(bids.phase_encoding(self.scan(dir_label='AP')), (1, -1, 'P'))
        self.assertEqual(bids.phase_encoding(self.scan(dir_label='RL', axcodes=('L', 'A', 'S'))), (0, 1, 'L'))
        self.assertEqual(bids.phase_encoding(self.scan(dir_label='RL')), (0, -1, 'L'))
        self.assertIsNone(bids.phase_encoding(self.scan(dir_label='fmap')))

    def test_pairs_ordered_ap_first(self):
        ap, pa = self.scan('j-', 'AP', run='1'), self.scan('j', 'PA', run='2')
        pairs, problem = bids.make_pairs([pa, ap])
        self.assertIsNone(problem)
        self.assertEqual(pairs, [(ap, pa)])
        self.assertEqual(bids.dataset_id([ap, pa]), 'sub-01')

    def test_pairs_problems(self):
        self.assertIn('no opposite', bids.make_pairs([self.scan('j-'), self.scan('j-', run='2')])[1])
        self.assertIn('different axes', bids.make_pairs([self.scan('j-'), self.scan('i', run='2')])[1])
        self.assertIn('unknown', bids.make_pairs([self.scan('j-'), self.scan(run='2')])[1])
        self.assertIn('2 and 1', bids.make_pairs([self.scan('j-'), self.scan('j-', run='2'), self.scan('j', run='3')])[1])


class TestPlanning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.root = self.dir / 'study'
        self.config = self.dir / 'config'
        dwi = self.root / 'sub-01/ses-1/dwi'
        write_dwi(dwi, 'sub-01_ses-1_acq-a_dir-AP_run-1_dwi', LAS, {'PhaseEncodingDirection': 'j-', 'TotalReadoutTime': 0.09})
        write_dwi(dwi, 'sub-01_ses-1_acq-a_dir-PA_run-2_dwi', LAS, {'PhaseEncodingDirection': 'j', 'TotalReadoutTime': 0.1})
        write_dwi(self.root / 'sub-02/ses-1/dwi', 'sub-02_ses-1_acq-b_dwi', LAS, {'PhaseEncodingDirection': 'j-'})
        self.single = write_protocol(self.dir / 'single.yml', ['BRAIN_Mask'])
        self.paired = write_protocol(self.dir / 'paired.yml', ['SUSCEPTIBILITY_Correct', 'BRAIN_Mask'])

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_protocol_processes_every_run(self):
        specs = batch.parse_protocol_specs([self.single])
        datasets, skipped, _ = batch.plan_bids(self.root, specs, self.config)
        self.assertEqual(skipped, [])
        self.assertEqual([d['id'] for d in datasets], ['sub-01_ses-1_acq-a_dir-AP_run-1', 'sub-01_ses-1_acq-a_dir-PA_run-2',
                                                      'sub-02_ses-1_acq-b'])
        self.assertEqual(datasets[2]['output_dir'], 'sub-02/ses-1/dwi/sub-02_ses-1_acq-b')
        self.assertEqual(datasets[2]['output_file_base'], '')

    def test_paired_protocol_pairs_and_overrides(self):
        specs = batch.parse_protocol_specs(['*acq-a*=' + self.paired, self.single])
        datasets, skipped, _ = batch.plan_bids(self.root, specs, self.config)
        self.assertEqual(skipped, [])
        pair = next(d for d in datasets if d['id'] == 'sub-01_ses-1_acq-a')
        self.assertEqual([Path(i).name for i in pair['images']],
                         ['sub-01_ses-1_acq-a_dir-AP_run-1_dwi.nii.gz', 'sub-01_ses-1_acq-a_dir-PA_run-2_dwi.nii.gz'])
        self.assertEqual(pair['output_file_base'], 'sub-01_ses-1_acq-a_dwi')
        self.assertEqual(pair['overrides'], {'SUSCEPTIBILITY_Correct': {'phaseEncodingAxis': 1, 'phaseEncodingValue': 0.095}})
        self.assertEqual(next(d for d in datasets if d['id'] == 'sub-02_ses-1_acq-b')['protocol'], self.single)

    def test_unpaired_run_with_paired_protocol_is_skipped(self):
        datasets, skipped, _ = batch.plan_bids(self.root, batch.parse_protocol_specs([self.paired]), self.config)
        self.assertEqual([d['id'] for d in datasets], ['sub-01_ses-1_acq-a'])
        self.assertEqual(skipped[0][0], 'sub-02_ses-1_acq-b_dwi')
        self.assertIn('no opposite phase encoding', skipped[0][1])

    def test_no_matching_protocol(self):
        specs = batch.parse_protocol_specs(['*acq-a*=' + self.single])
        datasets, skipped, _ = batch.plan_bids(self.root, specs, self.config)
        self.assertEqual(len(datasets), 2)
        self.assertEqual(skipped, [('sub-02_ses-1_acq-b_dwi', 'no protocol matches')])

    def test_datasheet(self):
        sheet = self.dir / 'sheet.tsv'
        sheet.write_text('id\timage_1\timage_2\toverrides\n'
                         'x\tstudy/sub-02/ses-1/dwi/sub-02_ses-1_acq-b_dwi.nii.gz\t\t\n'
                         'y\tmissing.nii.gz\t\t\n'
                         'z\tstudy/sub-01/ses-1/dwi/sub-01_ses-1_acq-a_dir-AP_run-1_dwi.nii.gz\t'
                         'study/sub-01/ses-1/dwi/sub-01_ses-1_acq-a_dir-PA_run-2_dwi.nii.gz\t'
                         '{"SUSCEPTIBILITY_Correct": {"phaseEncodingValue": 0.08}}\n')
        datasets, skipped, _ = batch.plan_manifest(sheet, batch.parse_protocol_specs(['z=' + self.paired, self.single]))
        self.assertEqual([d['id'] for d in datasets], ['x', 'z'])
        self.assertEqual(skipped[0][0], 'y')
        self.assertEqual(len(datasets[1]['images']), 2)
        self.assertEqual(datasets[1]['protocol'], self.paired)
        self.assertTrue(Path(datasets[0]['images'][0]).is_absolute())

    def test_batch_folder_and_states(self):
        out = self.dir / 'out'
        specs = batch.parse_protocol_specs([self.paired, self.single])
        datasets, skipped, _ = batch.plan_bids(self.root, specs, self.config)
        batch.write_batch(out, datasets, skipped, {'config_dir': str(self.config), 'command': ['dmriprep']})
        protocol = batch._read_yaml(batch.dataset_protocol(out, 'sub-01_ses-1_acq-a'))
        self.assertEqual(protocol['pipeline'][0][1]['protocol']['phaseEncodingValue'], 0.095)
        manifest = batch.load_manifest(out)
        self.assertEqual(len(manifest), 1)
        d = manifest[0]
        self.assertEqual(batch.current_state(out, d)[0], 'pending')
        batch.write_status(out, d, state='done', settings_hash=batch.settings_hash(protocol, d))
        self.assertEqual(batch.current_state(out, d)[0], 'done')
        self.assertEqual(batch.select_datasets(out)[0], [])
        batch.write_status(out, d, state='done', settings_hash=batch.settings_hash(protocol, dict(d, images=d['images'][::-1])))
        self.assertEqual(batch.current_state(out, d)[0], 'outdated')  # other image order
        batch.write_status(out, d, state='running', host='another-host', pid=1)
        self.assertEqual(batch.select_datasets(out), ([], [d]))
        self.assertEqual(batch.select_datasets(out, only=[d['id']])[0], [d])

    def test_default_protocol_planning(self):
        default = batch.DefaultProtocol()
        self.assertEqual(default.module_names(), ['SLICE_Check', 'INTERLACE_Check', 'EDDYMOTION_Correct', 'QC_Report'])
        self.assertEqual(default.for_pairs().module_names(),
                         ['SLICE_Check', 'INTERLACE_Check', 'SUSCEPTIBILITY_Correct', 'EDDYMOTION_Correct', 'QC_Report'])
        ## default pipeline: the AP/PA runs are a pair with susceptibility correction, the other run is on its own
        datasets, skipped, _ = batch.plan_bids(self.root, [('*', default)], self.config)
        self.assertEqual(skipped, [])
        self.assertEqual([d['id'] for d in datasets], ['sub-01_ses-1_acq-a', 'sub-02_ses-1_acq-b'])
        self.assertIn('SUSCEPTIBILITY_Correct', datasets[0]['protocol'].module_names())
        self.assertIn('SUSCEPTIBILITY_Correct', datasets[0]['overrides'])
        self.assertIs(datasets[1]['protocol'], default)
        ## explicit modules without susceptibility correction: every run
        explicit = batch.DefaultProtocol(['BRAIN_Mask'])
        datasets, _, _ = batch.plan_bids(self.root, [('*', explicit)], self.config)
        self.assertEqual(len(datasets), 3)
        paired = batch.DefaultProtocol(['SUSCEPTIBILITY_Correct', 'BRAIN_Mask'])
        datasets, skipped, _ = batch.plan_bids(self.root, [('*', paired)], self.config)
        self.assertEqual([d['id'] for d in datasets], ['sub-01_ses-1_acq-a'])
        self.assertIn('SUSCEPTIBILITY_Correct', datasets[0]['overrides'])
        self.assertEqual(len(skipped), 1)

    def test_override_of_missing_module(self):
        with self.assertRaises(batch.BatchError):
            batch.apply_overrides(batch._read_yaml(self.single), {'SUSCEPTIBILITY_Correct': {'phaseEncodingAxis': 1}})


if __name__ == '__main__':
    unittest.main()
