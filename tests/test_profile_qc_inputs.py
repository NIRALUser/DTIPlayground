import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from dtiplayground.dmri.fiberprofile.analysis import profile_qc


def _write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text)
    return str(path)


COLUMNS = ['sub-100619_ses-017m_acq-dir79select_dir_run-004', 'sub-105040_ses-012m_acq-dir79select_dir_run-001']
CASE_ROWS = 'case_id,-28,-14,0\n{},0.1,0.2,0.3\n{},0.4,0.5,0.6\n'.format(*COLUMNS)
ARC_ROWS = 'Arc Length,{},{}\n-28,0.1,0.4\n-14,0.2,0.5\n0,0.3,0.6\n'.format(*COLUMNS)


class TestTractAndMetric(unittest.TestCase):
    """The tract is the folder in the gathered layout and the file name in the EXTRACT_Profile output of a run."""

    def test_gathered_layout(self):
        self.assertEqual(profile_qc.tract_and_metric('/x/Profiles/AC_olfactory/AC_olfactory_FWFA.csv'),
                         ('AC_olfactory', 'FWFA'))
        self.assertFalse(profile_qc.is_run_output_table('/x/Profiles/AC_olfactory/AC_olfactory_FWFA.csv'))

    def test_run_output_layout(self):
        self.assertEqual(profile_qc.tract_and_metric('/x/00_EXTRACT_Profile/FWFA/AC_olfactory_FWFA.csv'),
                         ('AC_olfactory', 'FWFA'))
        self.assertTrue(profile_qc.is_run_output_table('/x/00_EXTRACT_Profile/FWFA/AC_olfactory_FWFA.csv'))

    def test_a_tract_name_with_underscores(self):
        self.assertEqual(profile_qc.tract_and_metric('/x/00_EXTRACT_Profile/AD/Arc_FrontoParietal_L_AD.csv'),
                         ('Arc_FrontoParietal_L', 'ad'))
        self.assertEqual(profile_qc.tract_and_metric('/x/P/Arc_FrontoParietal_L/Arc_FrontoParietal_L_ad.csv'),
                         ('Arc_FrontoParietal_L', 'ad'))

    def test_the_metric_is_named_as_gather_writes_it(self):
        """The run output has the property in upper case (AD, FA), gather lowercases fa/md/ad/rd: the prior stats of
        a gathered normative set have to be found for either layout."""
        for layout in ('/x/00_EXTRACT_Profile/FA/CGH_R_FA.csv', '/x/P/CGH_R/CGH_R_fa.csv'):
            self.assertEqual(profile_qc.tract_and_metric(layout)[1], 'fa')
        self.assertEqual(profile_qc.tract_and_metric('/x/00_EXTRACT_Profile/NDI/CGH_R_NDI.csv')[1], 'NDI')


class TestSelectInputs(unittest.TestCase):
    def test_both_layouts_are_read(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, '00_EXTRACT_Profile', 'FA', 'CGH_R_FA.csv'), ARC_ROWS)
            _write(os.path.join(d, '00_EXTRACT_Profile', 'MD', 'CGH_R_MD.csv'), ARC_ROWS)
            inputs = profile_qc.select_inputs(d)
            self.assertEqual(sorted(profile_qc.tract_and_metric(f) for f in inputs),
                             [('CGH_R', 'fa'), ('CGH_R', 'md')])

    def test_gathered_wins_when_the_root_holds_both(self):
        """A run folder with the gathered tables written inside it offers the same profiles twice."""
        with tempfile.TemporaryDirectory() as d:
            run = _write(os.path.join(d, '00_EXTRACT_Profile', 'FA', 'CGH_R_FA.csv'), ARC_ROWS)
            gathered = _write(os.path.join(d, 'Gathered', 'CGH_R', 'CGH_R_fa.csv'), ARC_ROWS)
            only_run = _write(os.path.join(d, '00_EXTRACT_Profile', 'ODI', 'CGH_R_ODI.csv'), ARC_ROWS)
            inputs = profile_qc.select_inputs(d)
            self.assertIn(gathered, inputs)
            self.assertNotIn(run, inputs)
            self.assertIn(only_run, inputs) # no gathered table for it
            self.assertEqual(len(inputs), 2)

    def test_the_computed_stats_are_not_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, '00_EXTRACT_Profile', 'FA', 'CGH_R_FA.csv'), ARC_ROWS)
            _write(os.path.join(d, '00_EXTRACT_Profile', 'FA', 'CGH_R_FA' + profile_qc.OUTPUT_SUFFIX), ARC_ROWS)
            self.assertEqual(len(profile_qc.select_inputs(d)), 1)


class TestLoadProfileTable(unittest.TestCase):
    def test_a_table_with_one_row_per_case_is_transposed(self):
        """EXTRACT_Profile with resultCaseColumnwise false writes the cases as rows."""
        with tempfile.TemporaryDirectory() as d:
            arc = profile_qc.load_profile_table(_write(os.path.join(d, 'a.csv'), ARC_ROWS))
            case = profile_qc.load_profile_table(_write(os.path.join(d, 'b.csv'), CASE_ROWS))
        self.assertEqual(list(case.columns), COLUMNS)
        self.assertEqual(list(case.index), [-28, -14, 0])
        pd.testing.assert_frame_equal(arc, case, check_names=False, check_dtype=False)

    def test_excluded_columns_are_dropped_in_both_orientations(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (('a.csv', ARC_ROWS), ('b.csv', CASE_ROWS)):
                df = profile_qc.load_profile_table(_write(os.path.join(d, name), text), exclude_full={COLUMNS[0]})
                self.assertEqual(list(df.columns), [COLUMNS[1]])


class TestCleanedTablesBlankOutsideBrain(unittest.TestCase):
    """The cleaned tables hold what the QC used: the locations sampled outside the brain are written empty instead of
    keeping the zeros that were ignored."""

    ARC_LAYOUT = 'Arc_Length,subA_ses-012m,subB_ses-012m\n-1,0.40,0.40\n0,0.40,0.00\n1,0.40,0.40\n'
    CASE_LAYOUT = 'case_id,-1,0,1\nsubA_ses-012m,0.40,0.40,0.40\nsubB_ses-012m,0.40,0.00,0.40\n'
    FWF_ARC = 'Arc_Length,subA_ses-012m,subB_ses-012m\n-1,0.10,0.10\n0,0.10,0.11\n1,0.10,0.10\n'

    def setUp(self):
        profile_qc.set_outside_brain({})
        self.addCleanup(profile_qc.set_outside_brain, {})

    def _clean(self, d, tables, drop=()):
        paths = [_write(os.path.join(d, tract, name), text) for tract, name, text in tables]
        profile_qc.set_outside_brain(profile_qc.find_outside_brain(sorted(paths)))
        out = {}
        for f in paths:
            target = os.path.join(d, 'clean', os.path.relpath(f, d))
            n = profile_qc.write_without_columns(f, target, set(drop))
            out[os.path.basename(f)] = (target, n)
        return out

    def test_the_zero_is_blanked_with_arc_lengths_as_rows(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._clean(d, [('CG_L', 'CG_L_fa.csv', self.ARC_LAYOUT)])
            target, n = out['CG_L_fa.csv']
            self.assertEqual(n, 1)
            self.assertEqual(open(target).read(), 'Arc_Length,subA_ses-012m,subB_ses-012m\n'
                                                  '-1,0.40,0.40\n0,0.40,\n1,0.40,0.40\n')
            self.assertTrue(np.isnan(profile_qc.read_profile_table(target).loc[0, 'subB_ses-012m']))

    def test_the_zero_is_blanked_with_cases_as_rows(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._clean(d, [('CG_R', 'CG_R_fa.csv', self.CASE_LAYOUT)])
            target, n = out['CG_R_fa.csv']
            self.assertEqual(n, 1)
            self.assertEqual(open(target).read(), 'case_id,-1,0,1\nsubA_ses-012m,0.40,0.40,0.40\n'
                                                  'subB_ses-012m,0.40,,0.40\n')

    def test_the_location_is_blanked_on_the_other_metrics_too(self):
        """FWF held a valid 0.11 there, but the location itself was outside the brain."""
        with tempfile.TemporaryDirectory() as d:
            out = self._clean(d, [('CG_L', 'CG_L_fa.csv', self.ARC_LAYOUT),
                                  ('CG_L', 'CG_L_FWF.csv', self.FWF_ARC)])
            target, n = out['CG_L_FWF.csv']
            self.assertEqual(n, 1)
            self.assertEqual(open(target).read().splitlines()[2], '0,0.10,')

    def test_the_kept_cells_are_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._clean(d, [('CG_L', 'CG_L_fa.csv', self.ARC_LAYOUT)])
            lines = open(out['CG_L_fa.csv'][0]).read().splitlines()
        self.assertEqual(lines[1], '-1,0.40,0.40') # the decimals as they were written
        self.assertEqual(lines[3], '1,0.40,0.40')

    def test_dropping_a_scan_and_blanking_work_together(self):
        with tempfile.TemporaryDirectory() as d:
            out = self._clean(d, [('CG_L', 'CG_L_fa.csv', self.ARC_LAYOUT)], drop=['subA_ses-012m'])
            target, n = out['CG_L_fa.csv']
            df = profile_qc.read_profile_table(target)
        self.assertEqual(list(df.columns), ['subB_ses-012m'])
        self.assertEqual(n, 1)
        self.assertTrue(np.isnan(df.loc[0, 'subB_ses-012m']))

    def test_nothing_is_blanked_when_the_check_is_off(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(os.path.join(d, 'CG_L', 'CG_L_fa.csv'), self.ARC_LAYOUT)
            profile_qc.set_outside_brain({}) # --keep-outside-brain
            target = os.path.join(d, 'clean', 'CG_L_fa.csv')
            self.assertEqual(profile_qc.write_without_columns(src, target, set()), 0)
            self.assertEqual(open(target).read(), self.ARC_LAYOUT)


class TestWriteWithoutColumns(unittest.TestCase):
    def test_cases_as_rows_are_dropped_by_row(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(os.path.join(d, 'b.csv'), CASE_ROWS)
            out = os.path.join(d, 'clean', 'b.csv')
            profile_qc.write_without_columns(src, out, {COLUMNS[0]})
            df = profile_qc.load_profile_table(out)
        self.assertEqual(list(df.columns), [COLUMNS[1]])

    def test_cases_as_columns_are_dropped_by_column(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(os.path.join(d, 'a.csv'), ARC_ROWS)
            out = os.path.join(d, 'clean', 'a.csv')
            profile_qc.write_without_columns(src, out, {COLUMNS[0]})
            df = profile_qc.load_profile_table(out)
        self.assertEqual(list(df.columns), [COLUMNS[1]])


ARC = [-2, -1, 0, 1, 2]


def _table(path, values):
    """A profile table: {identifier: [value per arc position]}."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(values, index=ARC).rename_axis("Arc_Length").to_csv(path)
    return str(path)


class TestOutsideBrain(unittest.TestCase):
    """A metric that cannot be 0 in tissue is 0 where the fibers left the brain mask: that location is dropped from
    every metric of the same tract and case, because it is the location that is wrong, not the metric."""

    def setUp(self):
        profile_qc.set_outside_brain({})
        self.addCleanup(profile_qc.set_outside_brain, {})

    def _tree(self, d, tables):
        paths = {}
        for (tract, metric), values in tables.items():
            paths[(tract, metric)] = _table(os.path.join(d, tract, '{}_{}.csv'.format(tract, metric)), values)
        return paths

    def test_a_zero_in_one_metric_drops_the_location_from_all_of_them(self):
        good, holed = [0.4] * 5, [0.4, 0.4, 0.0, 0.4, 0.4]
        with tempfile.TemporaryDirectory() as d:
            paths = self._tree(d, {
                ('CG_L', 'fa'): {'a_ses-012m': good, 'b_ses-012m': holed},
                ('CG_L', 'md'): {'a_ses-012m': good, 'b_ses-012m': good},   # md is fine at that position
                ('CG_L', 'FWF'): {'a_ses-012m': good, 'b_ses-012m': good},  # FWF too
            })
            profile_qc.set_outside_brain(profile_qc.find_outside_brain(sorted(paths.values())))
            for metric in ('fa', 'md', 'FWF'):
                df = profile_qc.load_profile_table(paths[('CG_L', metric)])
                self.assertTrue(np.isnan(df.loc[0, 'b_ses-012m']), metric)   # dropped everywhere
                self.assertFalse(df['a_ses-012m'].isna().any(), metric)      # the other case is untouched
                self.assertEqual(int(df['b_ses-012m'].notna().sum()), 4, metric)

    def test_a_zero_in_a_metric_where_zero_is_valid_drops_nothing(self):
        """FWF = 0 means no free water, not a location outside the brain."""
        with tempfile.TemporaryDirectory() as d:
            paths = self._tree(d, {
                ('CG_L', 'fa'): {'a_ses-012m': [0.4] * 5},
                ('CG_L', 'FWF'): {'a_ses-012m': [0.1, 0.0, 0.0, 0.1, 0.1]},
            })
            outside = profile_qc.find_outside_brain(sorted(paths.values()))
            self.assertEqual(outside, {})
            profile_qc.set_outside_brain(outside)
            self.assertFalse(profile_qc.load_profile_table(paths[('CG_L', 'FWF')]).isna().any().any())

    def test_other_tracts_are_not_affected(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._tree(d, {
                ('CG_L', 'fa'): {'a_ses-012m': [0.4, 0.0, 0.4, 0.4, 0.4]},
                ('CG_R', 'fa'): {'a_ses-012m': [0.4] * 5},
            })
            profile_qc.set_outside_brain(profile_qc.find_outside_brain(sorted(paths.values())))
            self.assertEqual(int(profile_qc.load_profile_table(paths[('CG_L', 'fa')]).isna().sum().sum()), 1)
            self.assertEqual(int(profile_qc.load_profile_table(paths[('CG_R', 'fa')]).isna().sum().sum()), 0)

    def test_a_negative_value_counts_as_well(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._tree(d, {('CG_L', 'md'): {'a_ses-012m': [1e-3, -1e-4, 1e-3, 1e-3, 1e-3]}})
            profile_qc.set_outside_brain(profile_qc.find_outside_brain(sorted(paths.values())))
            self.assertTrue(np.isnan(profile_qc.load_profile_table(paths[('CG_L', 'md')]).loc[-1, 'a_ses-012m']))

    def test_nothing_is_dropped_when_it_is_switched_off(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._tree(d, {('CG_L', 'fa'): {'a_ses-012m': [0.4, 0.0, 0.4, 0.4, 0.4]}})
            profile_qc.set_outside_brain({}) # --keep-outside-brain
            df = profile_qc.load_profile_table(paths[('CG_L', 'fa')])
            self.assertEqual(df.loc[-1, 'a_ses-012m'], 0.0)


class TestTooLittleLeftToJudge(unittest.TestCase):
    """A profile that is missing (or outside the brain) nearly everywhere cannot be compared with the prior: it is an
    outlier, not a clean profile."""

    def _qc(self, n_valid, n_positions=10, r=0.9, frac_inside=1.0, n_present=None):
        return pd.DataFrame([{
            'tract': 'CG_L', 'metric': 'fa', 'subject_session': 'a_ses-012m', 'age': 12, 'bin': '10-60m',
            'r': r, 'frac_inside': frac_inside, 'n_valid': n_valid,
            'n_inside': 0 if np.isnan(frac_inside) else int(frac_inside * n_valid),
            'n_present': n_valid if n_present is None else n_present, 'n_positions': n_positions}])

    def _flags(self, qc, min_valid_frac=0.75):
        g = profile_qc.detect_group_outliers(qc, value_min_inside=0.9, shape_method='fixed', corr_min=0.5,
                                             corr_iqr_k=1.5, shape_metric='fa', min_valid_frac=min_valid_frac)
        return g.iloc[0]

    def test_a_profile_without_any_valid_position_is_flagged(self):
        row = self._flags(self._qc(n_valid=0, r=np.nan, frac_inside=np.nan))
        self.assertEqual(row['frac_valid'], 0.0)
        self.assertTrue(row['is_value_outlier'])
        self.assertTrue(row['is_outlier'])

    def test_a_mostly_empty_profile_is_flagged_although_what_is_left_fits(self):
        row = self._flags(self._qc(n_valid=2)) # 2 of 10 positions, all inside the envelope
        self.assertEqual(row['joint_frac_inside'], 1.0)
        self.assertTrue(row['is_value_outlier'])

    def test_a_profile_with_enough_left_is_not_flagged(self):
        row = self._flags(self._qc(n_valid=8))
        self.assertFalse(row['is_value_outlier'])
        self.assertFalse(row['is_outlier'])

    def test_the_default_flags_a_profile_that_lost_a_quarter_of_its_positions(self):
        """Losing that much of a tract to locations outside the brain is itself a sign of a failure."""
        self.assertTrue(self._flags(self._qc(n_valid=6))['is_value_outlier'])   # 0.6 of the positions
        self.assertFalse(self._flags(self._qc(n_valid=6), min_valid_frac=0.5)['is_value_outlier'])

    def test_the_check_can_be_switched_off(self):
        row = self._flags(self._qc(n_valid=0, r=np.nan, frac_inside=np.nan), min_valid_frac=0)
        self.assertFalse(row['is_value_outlier'])

    def test_a_complete_profile_without_an_envelope_is_not_flagged(self):
        """An age bin holding a single subject has no std, so the prior defines no envelope and nothing can be
        compared (n_valid = 0). That says nothing about the profile, which is there in full."""
        row = self._flags(self._qc(n_valid=0, n_present=10, r=np.nan, frac_inside=np.nan))
        self.assertEqual(row['frac_valid'], 1.0)
        self.assertFalse(row['is_value_outlier'])
        self.assertFalse(row['is_outlier'])


if __name__ == '__main__':
    unittest.main()
