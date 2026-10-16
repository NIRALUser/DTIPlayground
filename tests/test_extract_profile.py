#   Tests of the EXTRACT_Profile module of dmrifiberprofile (synthetic tract and images):
#       python -m unittest discover -s tests

import shutil
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


def run_extract(tmp, rows, properties, cleanup='noCleanup'):
    """Runs EXTRACT_Profile on a datasheet of *rows* (id, '<prop> from original' columns), two straight tracts; a
    second run in the same *tmp* reuses the atlas and the output folder."""
    tmp = Path(tmp)
    atlas = tmp / 'atlas'
    if not atlas.exists():
        atlas.mkdir()
        for name, z in (('cc', 0.0), ('cst', 2.0)):
            points, offsets = [], [0]
            for dy in (-1.0, 0.0, 1.0):
                points += [[x, dy, z] for x in np.arange(-10.0, 10.5, 0.5)]
                offsets.append(len(points))
            fibers.write_fibers(fibers.FiberBundle(points, offsets), str(atlas / f'{name}.vtk'))
    datasheet = tmp / 'datasheet.csv'
    pd.DataFrame(rows).to_csv(datasheet, index=False)
    out = tmp / '00_EXTRACT_Profile'
    out.mkdir(exist_ok=True)
    module = EXTRACT_Profile.__new__(EXTRACT_Profile)
    module.protocol = {'tracts': None, 'atlas': str(atlas), 'propertiesToProfile': ', '.join(properties),
                       'resultCaseColumnwise': True, 'inputIsDTI': False, 'useDisplacementField': False,
                       'stepSize': 1, 'planeOfOrigin': 'Median', 'arcLength': 'compute', 'supportBandwidth': 3,
                       'noNaN': False, 'writeFiberFiles': False, 'mask': None, 'cleanup': cleanup,
                       'parameterToColumnHeaderMap': None}
    module.options = {'overwrite': False}
    module.output_dir = str(out)
    module.result = {'output': {}}
    module.getPreviousResult = lambda: {'output': {'file_path': str(datasheet)}}
    with mock.patch.object(base.modules.DTIFiberProfileModule, 'process', lambda self, *a, **k: None):
        result = module.process({'software_info': {'softwares': {}}})
    return out, result


def scalar_image(path, value, slope=0.0):
    data = np.full((30, 10, 6), value, dtype=np.float32) + np.arange(30, dtype=np.float32)[:, None, None] * slope  # slope: along the tracts
    nib.save(nib.Nifti1Image(data, np.diag([1.0, 1.0, 1.0, 1.0])), str(path))
    return str(path)


def tables(out, properties):
    return {(prop, name): pd.read_csv(out / prop / f'{name}_{prop}.csv') for prop in properties for name in ('cc', 'cst')}


def no_sampling():
    """Patches the sampling of the images: a run that would compute a profile fails."""
    return mock.patch.object(fibers, 'sample_scalar', side_effect=AssertionError('profile recomputed'))


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


class TestResume(unittest.TestCase):
    """A run into the output folder of a previous (e.g. interrupted) run reuses its unchanged profiles: from the
    record of each subject (subject_profiles/<id>.npz), or, without one, from the .fvp files, giving the same tables."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.rows = {'id': ['s1', 's2'],
                     'FA from original': [scalar_image(tmp / 'fa1.nii.gz', 0.5, 0.01), scalar_image(tmp / 'fa2.nii.gz', 0.4, 0.01)],
                     'MD from original': [scalar_image(tmp / 'md1.nii.gz', 0.8, 0.01), scalar_image(tmp / 'md2.nii.gz', 0.9, 0.01)]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_reuse_from_records(self):
        out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        first = tables(out, ['FA', 'MD'])
        self.assertEqual(sorted(p.name for p in (out / 'subject_profiles').iterdir()), ['s1.npz', 's2.npz'])
        with no_sampling(), mock.patch('dtiplayground.dmri.fiberprofile.modules.EXTRACT_Profile.EXTRACT_Profile.reuse_fvp',
                                       side_effect=AssertionError('.fvp read')):
            out, result = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        self.assertTrue(result['output']['success'])
        for k, table in tables(out, ['FA', 'MD']).items():
            pd.testing.assert_frame_equal(table, first[k])

    def test_reuse_from_fvp_without_records(self):
        out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        first = tables(out, ['FA', 'MD'])
        shutil.rmtree(out / 'subject_profiles')  # e.g. an output of an earlier version
        with no_sampling():
            out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        for k, table in tables(out, ['FA', 'MD']).items():
            pd.testing.assert_frame_equal(table, first[k])
        self.assertEqual(sorted(p.name for p in (out / 'subject_profiles').iterdir()), ['s1.npz', 's2.npz'])

    def test_interrupted_subject(self):
        """A subject without a record whose profiles are partly on disk: the others are computed."""
        out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        first = tables(out, ['FA', 'MD'])
        (out / 'subject_profiles' / 's2.npz').unlink()
        for f in (out / 'MD' / 'cst').glob('s2_*'):
            f.unlink()
        calls = []
        sample = fibers.sample_scalar
        with mock.patch.object(fibers, 'sample_scalar', side_effect=lambda *a: calls.append(1) or sample(*a)):
            out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        self.assertEqual(len(calls), 1)  # MD of s2 along cst
        for k, table in tables(out, ['FA', 'MD']).items():
            pd.testing.assert_frame_equal(table, first[k])

    def test_changed_image_is_recomputed(self):
        out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        first = tables(out, ['FA'])[('FA', 'cc')]
        scalar_image(self.rows['FA from original'][0], 0.7, 0.01)
        out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        fa = tables(out, ['FA'])[('FA', 'cc')]
        self.assertTrue(np.allclose(fa['s1'] - first['s1'], 0.2, atol=1e-5))
        pd.testing.assert_series_equal(fa['s2'], first['s2'])

    def test_records_keep_other_properties(self):
        run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        with no_sampling():
            run_extract(self.tmp.name, self.rows, ['FA'])
            out, _ = run_extract(self.tmp.name, self.rows, ['FA', 'MD'])
        self.assertEqual(list(tables(out, ['MD'])[('MD', 'cc')].columns), ['Arc Length', 's1', 's2'])

    def test_cleanup_keeps_records(self):
        out, _ = run_extract(self.tmp.name, self.rows, ['FA'], cleanup='duringProcessing')
        first = tables(out, ['FA'])
        self.assertFalse((out / 'FA' / 'cc').exists())
        with no_sampling():
            out, _ = run_extract(self.tmp.name, self.rows, ['FA'], cleanup='duringProcessing')
        for k, table in tables(out, ['FA']).items():
            pd.testing.assert_frame_equal(table, first[k])

    def test_damaged_record(self):
        out, _ = run_extract(self.tmp.name, self.rows, ['FA'])
        first = tables(out, ['FA'])
        (out / 'subject_profiles' / 's1.npz').write_bytes(b'not a record')
        with no_sampling():  # from the .fvp files
            out, _ = run_extract(self.tmp.name, self.rows, ['FA'])
        for k, table in tables(out, ['FA']).items():
            pd.testing.assert_frame_equal(table, first[k])


if __name__ == '__main__':
    unittest.main()
