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


class TestBatchNote(unittest.TestCase):
    """The batch of a session and the shift its maps got, in its 'scored' log line."""

    def test_note(self):
        shifts = {('A', 'FA', '10-60m'): ('add', -0.01, 10, 'batch'), ('B', 'FA', '10-60m'): ('add', -0.01, 3, 'cohort')}
        a, b, c = {'batch': 'A'}, {'batch': 'B'}, {'batch': 'C'}
        self.assertEqual(rq.batch_note(a, '10-60m', False, None, 5), '')
        self.assertEqual(rq.batch_note(a, '10-60m', True, None, 5), ', batch A')
        self.assertEqual(rq.batch_note(a, '10-60m', True, shifts, 5), ', batch A, own batch shift')
        self.assertEqual(rq.batch_note(b, '10-60m', True, shifts, 5),
                         ', batch B, cohort shift: batch of fewer than 5 scans')
        self.assertEqual(rq.batch_note(c, '10-60m', True, shifts, 5),
                         ', batch C, not batch corrected: fewer than 5 scans with a shift')
        self.assertEqual(rq.batch_note({'batch': ''}, '10-60m', False, {('', 'FA', '10-60m'): ('add', 0, 9, 'batch')}, 5),
                         ', cohort shift')


class TestBatchRowsOfASession(unittest.TestCase):
    """A batch table with rows of different batches for the same subject and session (two scans from different
    scanners or protocols): each scan gets the row whose values appear in its name."""

    def _table(self, d, text):
        path = os.path.join(d, 'scans.tsv')
        with open(path, 'w') as fh:
            fh.write(text)
        return path

    def test_resolve(self):
        from dtiplayground.dmri.fiberprofile.analysis.batches import resolve_batch_rows
        rows = [('Prisma', {'age': '12', 'acq': 'dir79', 'scanner': 'Prisma'}),
                ('Skyra', {'age': '12', 'acq': 'dir42', 'scanner': 'Skyra'})]
        self.assertEqual(resolve_batch_rows(rows, 'sub-1_ses-2_acq-dir79_dwi'), ('Prisma', ['acq']))
        self.assertEqual(resolve_batch_rows(rows, 'sub-1_ses-2_acq-dir42_dwi_Registered_FA.nii.gz'), ('Skyra', ['acq']))
        self.assertEqual(resolve_batch_rows(rows, '999434_VSA_Skyra_tensor'), ('Skyra', ['scanner']))  # the batch itself
        self.assertIsNone(resolve_batch_rows(rows, 'sub-1_ses-2_acq-dir6_dwi')[0])     # no row
        self.assertIsNone(resolve_batch_rows(rows, 'sub-1_ses-2_acq-dir797_dwi')[0])   # not a whole token
        self.assertIsNone(resolve_batch_rows(rows, 'sub-1_dir79_dir42_dwi')[0])         # both rows
        # the age is the same in both rows, so it can't match by accident ('12' in 'ses-12')
        self.assertIsNone(resolve_batch_rows(rows, 'sub-1_ses-12_dwi')[0])
        # a value with an underscore (IBIS prefixes), any case
        rows = [('A', {'protocol': 'CMRR_APPA'}), ('B', {'protocol': 'CMRR_PAAP'})]
        self.assertEqual(resolve_batch_rows(rows, '999434_VSA-CVD_cmrr_paap_tensor')[0], 'B')

    def test_assigner(self):
        from dtiplayground.dmri.common.age_table import load_batch_table
        from dtiplayground.dmri.fiberprofile.analysis.batches import BatchAssigner
        with tempfile.TemporaryDirectory() as d:
            path = self._table(d, 'participant_id\tsession_id\tacq\tscanner\n'
                                  'sub-1\tses-1\tdir79\tPrisma\nsub-1\tses-1\tdir42\tSkyra\n'
                                  'sub-2\tses-1\tdir79\tPrisma\nsub-2\tses-1\tdir42\tPrisma\n')
            table = load_batch_table(path, 'scanner')
            self.assertEqual(table[('2', '1')], 'Prisma')  # the same batch twice: no conflict
            assign = BatchAssigner(table)
            self.assertEqual(assign('sub-1', 'ses-1', '/x/sub-1_ses-1_acq-dir42_dwi_FA.nii.gz'), 'Skyra')
            self.assertEqual(assign('sub-1', 'ses-1', '/x/a', name='sub-1_ses-1_acq-dir79_dwi'), 'Prisma')
            self.assertEqual(assign('sub-1', 'ses-1', 'sub-1_ses-1_dwi'), '')  # can't tell
            self.assertEqual(assign('sub-2', 'ses-1', 'sub-2_ses-1_dwi'), 'Prisma')
            self.assertEqual(set(assign.unresolved), {'sub-1_ses-1_dwi'})
            with self.assertLogs('batches', level='WARNING'):
                assign.report()
            ## the pattern gives the batch of the scans the rows don't tell apart
            assign = BatchAssigner(table, r'acq-(\w+?)_')
            self.assertEqual(assign('sub-1', 'ses-1', '/x/sub-1_ses-1_acq-dir6_dwi', name='sub-1_ses-1_acq-dir6_dwi'),
                             'dir6')

    def test_end_to_end(self):
        """Two scans per session in the synthetic cohort, of two scanners: one table row per scan."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        _make(tmp.name)
        data = os.path.join(tmp.name, 'Data')
        lines = ['participant_id\tsession_id\tage\tacquisition\tscanner']
        for sub in sorted(os.listdir(data)):
            d = os.path.join(data, sub, 'ses-012m')
            for f in os.listdir(d):  # a second scan of every session, acq-std, from another scanner: the original
                os.rename(os.path.join(d, f), os.path.join(d, f.replace('_dwi_', '_acq-std_dwi_')))
            lines += ['{}\tses-012m\t12\tacq-std\tPrisma'.format(sub), '{}\tses-012m\t12\tacq-alt\tSkyra'.format(sub)]
            for f in os.listdir(d):  # acq-alt: the same maps with the offset of site B
                img = nib.load(os.path.join(d, f))
                v = np.asarray(img.dataobj, dtype=np.float32)
                v = np.where(v > 0, v - 0.04, 0) if f.endswith('_FA.nii.gz') else v * 1.15
                nib.save(nib.Nifti1Image(v, img.affine), os.path.join(d, f.replace('acq-std', 'acq-alt')))
        table = self._table(tmp.name, '\n'.join(lines) + '\n')
        common = ['--data-dir', data, '--atlas-dir', os.path.join(tmp.name, 'Atlas'),
                  '--normative-dir', os.path.join(tmp.name, 'norm'), '--scalar-metrics', 'FA,MD']
        self.assertEqual(rq.main(common + ['--reference-dir', os.path.join(tmp.name, 'Reference'), '--build-normative']), 0)
        out = os.path.join(tmp.name, 'qc')
        self.assertEqual(rq.main(common + ['--out-dir', out, '--age-csv', table, '--batch-column', 'scanner',
                                           '--batch-correct']), 0)
        df = pd.read_csv(os.path.join(out, 'registration_qc.csv'), keep_default_na=False)
        self.assertEqual(dict(zip(df['prefix'], df['batch'])), {'acq-std_dwi': 'Prisma', 'acq-alt_dwi': 'Skyra'})
        s = pd.read_csv(os.path.join(out, 'batch_shifts.csv')).set_index(['batch', 'metric'])['shift']
        self.assertAlmostEqual(s[('Skyra', 'MD')] / s[('Prisma', 'MD')], 1.15, delta=0.01)


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
