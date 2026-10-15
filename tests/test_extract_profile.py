#   Tests of the EXTRACT_Profile module of dmrifiberprofile (synthetic tract and images):
#       python -m unittest discover -s tests

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nibabel as nib
import numpy as np
import pandas as pd

import dtiplayground.dmri.fiberprofile as base
import dtiplayground.dmri.fiberprofile.modules  # noqa: F401  (the module package, as dmrifiberprofile loads it)
import dtiplayground.dmri.common.fibers as fibers
from dtiplayground.dmri.fiberprofile.modules.EXTRACT_Profile.EXTRACT_Profile import EXTRACT_Profile


def run_extract(tmp, rows, properties):
    """Runs EXTRACT_Profile on a datasheet of *rows* (id, '<prop> from original' columns), one straight tract."""
    tmp = Path(tmp)
    atlas = tmp / 'atlas'
    atlas.mkdir()
    points, offsets = [], [0]
    for dy in (-1.0, 0.0, 1.0):
        points += [[x, dy, 0.0] for x in np.arange(-10.0, 10.5, 0.5)]
        offsets.append(len(points))
    fibers.write_fibers(fibers.FiberBundle(points, offsets), str(atlas / 'cc.vtk'))
    datasheet = tmp / 'datasheet.csv'
    pd.DataFrame(rows).to_csv(datasheet, index=False)
    out = tmp / '00_EXTRACT_Profile'
    out.mkdir()
    module = EXTRACT_Profile.__new__(EXTRACT_Profile)
    module.protocol = {'tracts': None, 'atlas': str(atlas), 'propertiesToProfile': ', '.join(properties),
                       'resultCaseColumnwise': True, 'inputIsDTI': False, 'useDisplacementField': False,
                       'stepSize': 1, 'planeOfOrigin': 'Median', 'arcLength': 'compute', 'supportBandwidth': 3,
                       'noNaN': False, 'writeFiberFiles': False, 'mask': None, 'cleanup': 'noCleanup',
                       'parameterToColumnHeaderMap': None}
    module.options = {'overwrite': False}
    module.output_dir = str(out)
    module.result = {'output': {}}
    module.getPreviousResult = lambda: {'output': {'file_path': str(datasheet)}}
    with mock.patch.object(base.modules.DTIFiberProfileModule, 'process', lambda self, *a, **k: None):
        result = module.process({'software_info': {'softwares': {}}})
    return out, result


def scalar_image(path, value):
    nib.save(nib.Nifti1Image(np.full((30, 10, 6), value, dtype=np.float32), np.diag([1.0, 1.0, 1.0, 1.0])), str(path))
    return str(path)


class TestPropertyWithoutImages(unittest.TestCase):
    """A property whose datasheet column is empty for every subject (e.g. FWFA without free-water data) is not
    profiled; its profile table was still written into a folder that did not exist (OSError, 0.8.17)."""

    def test_no_table_for_a_property_without_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            fa = scalar_image(Path(tmp) / 'fa.nii.gz', 0.5)
            rows = {'id': ['s1', 's2'], 'FA from original': [fa, fa], 'FWFA from original': [None, None]}
            out, result = run_extract(tmp, rows, ['FA', 'FWFA'])
            self.assertTrue(result['output']['success'])
            table = pd.read_csv(out / 'FA' / 'cc_FA.csv')
            self.assertEqual(list(table.columns), ['Arc Length', 's1', 's2'])
            self.assertTrue(np.allclose(table[['s1', 's2']].to_numpy(), 0.5))
            self.assertFalse((out / 'FWFA').exists())

    def test_property_with_images_for_some_subjects(self):
        with tempfile.TemporaryDirectory() as tmp:
            fa = scalar_image(Path(tmp) / 'fa.nii.gz', 0.5)
            fwfa = scalar_image(Path(tmp) / 'fwfa.nii.gz', 0.6)
            rows = {'id': ['s1', 's2'], 'FA from original': [fa, fa], 'FWFA from original': [fwfa, None]}
            out, _ = run_extract(tmp, rows, ['FA', 'FWFA'])
            self.assertEqual(list(pd.read_csv(out / 'FWFA' / 'cc_FWFA.csv').columns), ['Arc Length', 's1'])


if __name__ == '__main__':
    unittest.main()
