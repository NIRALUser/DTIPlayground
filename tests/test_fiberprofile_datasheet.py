#   Tests of the datasheet detection of dmrifiberprofile (file names only):
#       python -m unittest discover -s tests

import tempfile
import unittest
from pathlib import Path

from dtiplayground.dmri.fiberprofile import datasheet as ds

PROTOCOL = {'propertiesToProfile': 'FA, MD, FWFA, FWF, FWf, NDI', 'useDisplacementField': True, 'inputIsDTI': True}
SCAN = 'sub-1_ses-012m_acq-a_run-1'


def touch(root, *names):
    for name in names:
        p = Path(root) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('')


class TestDetection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        touch(self.root,  # IBIS / DTI_Register layout
              f'sub-1/ses-012m/mask/{SCAN}_dwi_QCed_tensor.nrrd',
              f'sub-1/ses-012m/mask/{SCAN}_dwi_QCed_FA.nii.gz',
              f'sub-1/ses-012m/mask/{SCAN}_dwi_QCed_FWFA.nii.gz',
              f'sub-1/ses-012m/mask/{SCAN}_dwi_QCed_FWf.nii.gz',
              f'sub-1/ses-012m/mask/{SCAN}_dwi_QCed_NODDI_FWF.nii.gz',
              f'sub-1/ses-012m/mask/{SCAN}_dwi_QCed_NODDI_NDI.nii.gz',
              f'sub-1/ses-012m/AtlasReg/{SCAN}_dwi_QCed_tensor_DTI_DisplacementField.nrrd',
              f'sub-1/ses-012m/AtlasReg/{SCAN}_dwi_QCed_tensor_DTI_Inverse_DisplacementField.nrrd',
              f'sub-1/ses-012m/AtlasReg/{SCAN}_dwi_QCed_tensor_DTI_Flipped.nrrd',
              f'sub-1/ses-012m/AtlasReg/{SCAN}_dwi_QCed_tensor_DTI_Registered.nrrd',
              f'sub-1/ses-012m/AtlasReg/{SCAN}_dwi_QCed_tensor_Registered_FWFA.nii.gz',
              f'sub-1/ses-012m/AtlasReg/{SCAN}_dwi_QCed_tensor_Registered_NODDI_NDI.nii.gz')

    def tearDown(self):
        self.tmp.cleanup()

    def test_native_space(self):
        columns, rows, pmap, skipped, _ = ds.detect(self.root, PROTOCOL)
        self.assertEqual(skipped, [])
        row = {k: Path(v).name for k, v in rows[0].items()}
        self.assertEqual(row['id'], SCAN)
        self.assertEqual(row['DTI'], f'{SCAN}_dwi_QCed_tensor.nrrd')
        self.assertEqual(row['Deformation field'], f'{SCAN}_dwi_QCed_tensor_DTI_DisplacementField.nrrd')
        self.assertEqual(row['FWFA'], f'{SCAN}_dwi_QCed_FWFA.nii.gz')  # no FW tensor: its map
        self.assertEqual(row['FWF'], f'{SCAN}_dwi_QCed_NODDI_FWF.nii.gz')
        self.assertEqual(row['FWf'], f'{SCAN}_dwi_QCed_FWf.nii.gz')
        self.assertEqual(row['NDI'], f'{SCAN}_dwi_QCed_NODDI_NDI.nii.gz')
        self.assertNotIn('FA', columns)  # FA, MD from the tensors
        self.assertEqual(pmap['Original DTI Image'], 'DTI')
        self.assertEqual(pmap['Deformation Field'], 'Deformation field')
        self.assertEqual(pmap['FWFA'], 'FWFA')
        self.assertNotIn('FW DTI Image', pmap)

    def test_free_water_tensor_used_when_present(self):
        touch(self.root, f'sub-1/ses-012m/mask/{SCAN}_dwi_QCed_FWtensor.nrrd')
        columns, rows, pmap, _, _ = ds.detect(self.root, PROTOCOL)
        self.assertEqual(pmap['FW DTI Image'], 'FW DTI')
        self.assertEqual(Path(rows[0]['FW DTI']).name, f'{SCAN}_dwi_QCed_FWtensor.nrrd')
        self.assertNotIn('FWFA', columns)

    def test_atlas_space(self):
        columns, rows, pmap, _, _ = ds.detect(self.root, dict(PROTOCOL, useDisplacementField=False))
        row = {k: Path(v).name if v else '' for k, v in rows[0].items()}
        self.assertEqual(row['DTI'], f'{SCAN}_dwi_QCed_tensor_DTI_Registered.nrrd')
        self.assertEqual(row['FWFA'], f'{SCAN}_dwi_QCed_tensor_Registered_FWFA.nii.gz')
        self.assertEqual(row['NDI'], f'{SCAN}_dwi_QCed_tensor_Registered_NODDI_NDI.nii.gz')
        self.assertEqual(row['FWF'], '')  # optional, not registered
        self.assertNotIn('Deformation field', columns)
        self.assertNotIn('Deformation Field', pmap)

    def test_dmriprep_names(self):
        touch(self.root, 'out/sub-2_ses-006m_dwi_DTI.nrrd', 'out/sub-2_ses-006m_dwi_DTI_DisplacementField.nrrd',
              'out/sub-2_ses-006m_dwi_DTI_FA.nii.gz', 'out/sub-2_ses-006m_dwi_NODDI_NDI.nii.gz')
        _, rows, _, _, _ = ds.detect(self.root, PROTOCOL)
        row = {r['id']: r for r in rows}['sub-2_ses-006m']
        self.assertEqual(Path(row['DTI']).name, 'sub-2_ses-006m_dwi_DTI.nrrd')
        self.assertEqual(Path(row['Deformation field']).name, 'sub-2_ses-006m_dwi_DTI_DisplacementField.nrrd')
        self.assertEqual(Path(row['NDI']).name, 'sub-2_ses-006m_dwi_NODDI_NDI.nii.gz')

    def test_ambiguous_and_missing(self):
        touch(self.root, f'copy/{SCAN}_dwi_QCed_tensor.nrrd',  # a second tensor of the scan
              'sub-3/sub-3_ses-001m_dwi_QCed_tensor.nrrd')      # no displacement field
        with self.assertRaises(ds.DatasheetError) as e:  # no scan left: error with the reasons
            ds.detect(self.root, PROTOCOL)
        self.assertIn(SCAN + ': 2 files for DTI', str(e.exception))
        self.assertIn('sub-3_ses-001m: no Deformation field file', str(e.exception))
        touch(self.root, 'sub-3/sub-3_ses-001m_dwi_QCed_tensor_DTI_DisplacementField.nrrd')
        _, rows, _, skipped, _ = ds.detect(self.root, PROTOCOL)
        self.assertEqual([r['id'] for r in rows], ['sub-3_ses-001m'])
        self.assertIn('2 files for DTI', dict(skipped)[SCAN])

    def test_linked_folders(self):
        linked = self.root / 'linked'
        linked.mkdir()
        (linked / 'sub-1').symlink_to(self.root / 'sub-1', target_is_directory=True)
        (linked / 'loop').symlink_to(linked, target_is_directory=True)  # followed once only
        _, rows, _, skipped, _ = ds.detect(linked, PROTOCOL)
        self.assertEqual([r['id'] for r in rows], [SCAN])
        self.assertEqual(skipped, [])

    def test_error_when_nothing_matches(self):
        empty = self.root / 'empty'
        touch(empty, 'sub-9/sub-9_ses-001m_dwi.nii.gz')
        with self.assertRaises(ds.DatasheetError) as e:
            ds.detect(empty, PROTOCOL)
        self.assertIn('No scan below', str(e.exception))
        self.assertIn('_DTI_DisplacementField.nrrd', str(e.exception))
        with self.assertRaises(ds.DatasheetError):
            ds.detect(self.root / 'missing', PROTOCOL)


if __name__ == '__main__':
    unittest.main()
