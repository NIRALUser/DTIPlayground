"""dmrifiberprofile qc-registration with batches (--batch-correct, --batch-column, --batch-regex), on a synthetic
cohort: a reference cohort for the normative model, 10 scans of site A, 8 of site B with an MD 15% higher and an FA
0.04 lower (a scanner offset), and one scan of site B also misregistered (shifted by 3 voxels)."""
import os
import tempfile
import unittest

import nibabel as nib
import numpy as np
import pandas as pd

from dtiplayground.dmri.fiberprofile.analysis import registration_qc as rq
from dtiplayground.dmri.fiberprofile.analysis.batches import center_by_batch

def _make(root, seed=0):
    rng = np.random.default_rng(seed)
    n = 24
    x, y, z = np.meshgrid(*[np.arange(n) - n / 2 + 0.5] * 3, indexing='ij')
    r = np.sqrt(x ** 2 + y ** 2 + z ** 2)
    brain = r < 10
    fa0 = np.where(brain, 0.35 + 0.25 * np.sin(x / 2.5) * np.cos(y / 3.0) + 0.1 * np.sin(z / 2.0), 0).clip(0, 0.95)
    md0 = np.where(brain, 0.0010 + 0.0003 * np.cos(x / 3.0) * np.sin(z / 2.5), 0)
    aff = np.diag([2.0, 2.0, 2.0, 1.0])
    os.makedirs(os.path.join(root, 'Atlas'), exist_ok=True)
    nib.save(nib.Nifti1Image(fa0.astype(np.float32), aff), os.path.join(root, 'Atlas', 'Atlas_FA.nii.gz'))
    nib.save(nib.Nifti1Image(md0.astype(np.float32), aff), os.path.join(root, 'Atlas', 'Atlas_MD.nii.gz'))

    def scan(folder, sub, fa_add=0.0, md_mul=1.0, roll=0):
        fa = np.where(brain, fa0 + 0.02 * rng.standard_normal(fa0.shape) + fa_add, 0).clip(0, 0.99)
        md = np.where(brain, md0 * (1 + 0.03 * rng.standard_normal(md0.shape)) * md_mul, 0)
        if roll:
            fa, md = np.roll(fa, roll, axis=0), np.roll(md, roll, axis=0)
        d = os.path.join(root, folder, sub, 'ses-012m')
        os.makedirs(d, exist_ok=True)
        for m, v in (('FA', fa), ('MD', md)):
            nib.save(nib.Nifti1Image(v.astype(np.float32), aff), os.path.join(d, f'{sub}_ses-012m_dwi_Registered_{m}.nii.gz'))

    for i in range(12):
        scan('Reference', f'sub-9{i:02d}')
    rows = []
    for i in range(10):
        scan('Data', f'sub-0{i:02d}'); rows.append((f'sub-0{i:02d}', 'A'))
    for i in range(8):
        scan('Data', f'sub-1{i:02d}', fa_add=-0.04, md_mul=1.15, roll=3 if i == 7 else 0); rows.append((f'sub-1{i:02d}', 'B'))
    with open(os.path.join(root, 'participants.tsv'), 'w') as fh:
        fh.write('participant_id\tsession_id\tage\tsite\n')
        for sub, site in rows:
            fh.write(f'{sub}\tses-012m\t12\t{site}\n')



SITE_B = {'sub-1{:02d}_ses-012m_dwi'.format(i) for i in range(8)}
MISREGISTERED = {'sub-107_ses-012m_dwi'}


class TestRegistrationQCBatches(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = cls.tmp.name
        _make(cls.root)
        cls.common = ['--data-dir', os.path.join(cls.root, 'Data'), '--atlas-dir', os.path.join(cls.root, 'Atlas'),
                      '--normative-dir', os.path.join(cls.root, 'norm'), '--scalar-metrics', 'FA,MD']
        assert rq.main(cls.common + ['--reference-dir', os.path.join(cls.root, 'Reference'), '--build-normative']) == 0
        cls.table = os.path.join(cls.root, 'participants.tsv')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _run(self, *options):
        out = os.path.join(self.root, 'qc{}'.format(len(os.listdir(self.root))))
        self.assertEqual(rq.main(self.common + ['--out-dir', out] + list(options)), 0)
        df = pd.read_csv(os.path.join(out, 'registration_qc.csv'), keep_default_na=False, dtype={'batch': str})
        shifts = os.path.join(out, 'batch_shifts.csv')
        shifts = pd.read_csv(shifts, dtype={'batch': str}, keep_default_na=False) if os.path.exists(shifts) else None
        return set(df.loc[df['is_outlier'].astype(str) == 'True', 'id']), df, shifts

    def test_without_batches_the_whole_site_is_flagged(self):
        flagged, df, shifts = self._run()
        self.assertEqual(flagged, SITE_B)
        self.assertIsNone(shifts)
        self.assertEqual(set(df['batch']), {''})
        ## one shift for the cohort, site A the majority: site B stays off
        flagged, _, shifts = self._run('--batch-correct')
        self.assertEqual(flagged, SITE_B)
        self.assertEqual(set(shifts['batch']), {''})

    def test_batches_flag_the_misregistered_scan_only(self):
        for options in (['--age-csv', self.table, '--batch-column', 'site'],
                        ['--batch-csv', self.table, '--batch-column', 'site', '--batch-correct'],
                        ['--batch-regex', r'sub-(\d)\d\d_', '--batch-correct'],
                        ['--age-csv', self.table, '--batch-column', 'site', '--batch-correct',
                         '--combine', 'mahalanobis']):
            with self.subTest(options=options):
                flagged, df, _ = self._run(*options)
                self.assertEqual(flagged, MISREGISTERED)
                self.assertIn(set(df['batch']), ({'A', 'B'}, {'0', '1'}))

    def test_the_shifts_of_the_sites(self):
        _, df, shifts = self._run('--age-csv', self.table, '--batch-column', 'site', '--batch-correct')
        s = shifts.set_index(['batch', 'metric'])['shift']
        self.assertAlmostEqual(s[('B', 'FA')], -0.04, delta=0.005)
        self.assertAlmostEqual(s[('B', 'MD')], 1.15, delta=0.01)
        self.assertAlmostEqual(s[('A', 'FA')], 0.0, delta=0.005)
        self.assertAlmostEqual(s[('A', 'MD')], 1.0, delta=0.01)
        self.assertEqual(set(shifts['source']), {'batch'})
        ## the corrected z-scores of site B are those of site A
        z = df.groupby('batch')['MD_meanAbsZ'].median()
        self.assertAlmostEqual(z['B'], z['A'], delta=0.1)

    def test_a_small_site_gets_the_cohort_shift(self):
        _, _, shifts = self._run('--age-csv', self.table, '--batch-column', 'site', '--batch-correct',
                                 '--batch-min-scans', '9')
        b = shifts[shifts['batch'] == 'B'].set_index('metric')
        self.assertEqual(set(b['source']), {'cohort'})
        self.assertEqual(set(b['n_scans']), {8})

    def test_options_need_a_table(self):
        with self.assertRaises(SystemExit):
            rq.main(self.common + ['--out-dir', os.path.join(self.root, 'x'), '--batch-column', 'site'])
        with self.assertRaises(SystemExit):
            rq.main(self.common + ['--out-dir', os.path.join(self.root, 'x'), '--batch-csv', self.table])


class TestCenterByBatch(unittest.TestCase):

    def test_center(self):
        x = np.array([1.0, 2.0, 3.0, 11.0, 12.0, 13.0, 50.0])
        b = ['a', 'a', 'a', 'b', 'b', 'b', 'c']
        out, info = center_by_batch(x, b, 3)
        med = np.median(x)
        np.testing.assert_allclose(out[:6], [med - 1, med, med + 1, med - 1, med, med + 1])
        self.assertAlmostEqual(out[6], 50.0)  # a batch of one: centred on the cohort median, unchanged
        self.assertIsNone(info['c'][1])
        X = np.column_stack([x, 2 * x])
        out2, _ = center_by_batch(X, b, 3)
        np.testing.assert_allclose(out2[:, 0], out)


if __name__ == '__main__':
    unittest.main()
