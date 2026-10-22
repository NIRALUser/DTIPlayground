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


class TestAgeOfAProfile(unittest.TestCase):
    """The age of a profile column decides its age bin: the table of --age-csv first, then the pattern on the column
    name, the same order as the DTI_Register module and qc-registration."""

    def setUp(self):
        profile_qc.set_age_source()
        self.addCleanup(profile_qc.set_age_source)

    def test_the_column_name_when_there_is_no_table(self):
        self.assertEqual(profile_qc.age_of('sub-1_ses-017m_acq-x'), 17)
        self.assertIsNone(profile_qc.age_of('sub-1_ses-V02_acq-x'))

    def test_the_table_is_used_when_the_session_carries_no_age(self):
        profile_qc.set_age_source({('1', 'v02'): 14})
        self.assertEqual(profile_qc.age_of('sub-1_ses-V02_acq-x'), 14)

    def test_the_table_wins_over_the_column_name(self):
        profile_qc.set_age_source({('1', '017m'): 9})
        self.assertEqual(profile_qc.age_of('sub-1_ses-017m_acq-x'), 9)

    def test_a_scan_that_is_not_in_the_table_falls_back_to_the_column_name(self):
        profile_qc.set_age_source({('9', 'v02'): 14})
        self.assertEqual(profile_qc.age_of('sub-1_ses-017m_acq-x'), 17)
        self.assertIsNone(profile_qc.age_of('sub-1_ses-V02_acq-x'))

    def test_a_subject_level_row_applies_to_every_session(self):
        profile_qc.set_age_source({('1', None): 20})
        self.assertEqual(profile_qc.age_of('sub-1_ses-V01_acq-x'), 20)
        self.assertEqual(profile_qc.age_of('sub-1_ses-V02_acq-x'), 20)

    def test_another_pattern_for_the_column_names(self):
        profile_qc.set_age_source(None, r'age-(\d+)mo')
        self.assertEqual(profile_qc.age_of('sub-1_age-014mo_acq-x'), 14)
        self.assertIsNone(profile_qc.age_of('sub-1_ses-017m_acq-x')) # the default pattern no longer applies

    def test_the_bins_follow_the_table(self):
        bins = profile_qc.parse_bins('0-3,4-9,10-60')
        columns = ['sub-1_ses-V01_acq-x', 'sub-1_ses-V02_acq-x', 'sub-2_ses-V01_acq-x']
        profile_qc.set_age_source({('1', 'v01'): 2, ('1', 'v02'): 14, ('2', 'v01'): 6})
        grouped = profile_qc.bin_columns(columns, bins)
        self.assertEqual(grouped['0-3m'], ['sub-1_ses-V01_acq-x'])
        self.assertEqual(grouped['4-9m'], ['sub-2_ses-V01_acq-x'])
        self.assertEqual(grouped['10-60m'], ['sub-1_ses-V02_acq-x'])

    def test_where_each_age_came_from_is_recorded(self):
        profile_qc.set_age_source({('1', 'v02'): 14})
        profile_qc.age_of('sub-1_ses-V02_acq-x') # the table
        profile_qc.age_of('sub-2_ses-017m_acq-x') # the pattern
        profile_qc.age_of('sub-3_ses-V03_acq-x') # neither
        self.assertEqual({k: len(v) for k, v in profile_qc._AGE_SOURCE.items()},
                         {'table': 1, 'pattern': 1, 'none': 1})


class TestFindPriorStats(unittest.TestCase):
    """The age bin stats are written next to the tables they came from, so they are in the layout of those tables: a
    normative set gathered first has them per tract, one computed straight from a run has them per metric."""

    def setUp(self):
        profile_qc._PRIOR_INDEX.clear()
        self.addCleanup(profile_qc._PRIOR_INDEX.clear)

    def test_the_gathered_layout(self):
        with tempfile.TemporaryDirectory() as d:
            want = _write(os.path.join(d, 'CG_L', 'CG_L_fa' + profile_qc.OUTPUT_SUFFIX), 'Arc_Length\n0\n')
            self.assertEqual(profile_qc.find_prior_stats(d, 'CG_L', 'fa'), want)

    def test_the_run_output_layout_and_its_spelling_of_the_metric(self):
        """The run output writes FA, and the QC asks for it as gather names it (fa)."""
        with tempfile.TemporaryDirectory() as d:
            want = _write(os.path.join(d, 'FA', 'CG_L_FA' + profile_qc.OUTPUT_SUFFIX), 'Arc_Length\n0\n')
            self.assertEqual(profile_qc.find_prior_stats(d, 'CG_L', 'fa'), want)

    def test_a_tract_name_with_underscores_in_the_run_layout(self):
        with tempfile.TemporaryDirectory() as d:
            want = _write(os.path.join(d, 'AD', 'Arc_FT_L_AD' + profile_qc.OUTPUT_SUFFIX), 'Arc_Length\n0\n')
            self.assertEqual(profile_qc.find_prior_stats(d, 'Arc_FT_L', 'ad'), want)

    def test_nothing_for_a_tract_that_is_not_there(self):
        with tempfile.TemporaryDirectory() as d:
            _write(os.path.join(d, 'FA', 'CG_L_FA' + profile_qc.OUTPUT_SUFFIX), 'Arc_Length\n0\n')
            self.assertIsNone(profile_qc.find_prior_stats(d, 'CG_R', 'fa'))
            self.assertIsNone(profile_qc.find_prior_stats(d, 'CG_L', 'md'))


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



class TestOutputFolders(unittest.TestCase):
    """The tables of the QC go to --stats-dir, the plot folders hold only plots."""

    @staticmethod
    def _tables(root, n, outlier=None):
        arc = np.linspace(-20, 20, 21)
        rng = np.random.default_rng(0)
        for tract in ('CGH_R', 'UNC_L'):
            for metric, base in (('fa', 0.45), ('md', 0.0011)):
                cols = {}
                for i in range(n):
                    name = 'sub-{:03d}_ses-012m_dwi'.format(i)
                    prof = base * (1 + 0.3 * np.sin(arc / 10) + 0.01 * rng.standard_normal(arc.size))
                    if name == outlier:
                        prof = base * (1 - 0.3 * np.sin(arc / 10))  # mirrored shape
                    cols[name] = prof
                df = pd.DataFrame(cols, index=pd.Index(arc, name='Arc Length'))
                Path(root, tract).mkdir(parents=True, exist_ok=True)
                df.to_csv(Path(root, tract, '{}_{}.csv'.format(tract, metric)))

    def test_the_tables_go_to_the_stats_dir(self):
        with tempfile.TemporaryDirectory() as d:
            norm, data = os.path.join(d, 'norm'), os.path.join(d, 'data')
            self._tables(norm, 12)
            self._tables(data, 8, outlier='sub-003_ses-012m_dwi')
            self.assertEqual(profile_qc.main(['--profiles-dir', norm, '--plots-dir', os.path.join(d, 'normplots'),
                                              '--stats-dir', os.path.join(d, 'normstats'), '--no-plots']), 0)
            stats, plots, clean_plots = (os.path.join(d, n) for n in ('Stats', 'Plots_All', 'Plots_Clean'))
            self.assertEqual(profile_qc.main(['--profiles-dir', data, '--prior-stats-dir', norm,
                                              '--clean-dir', os.path.join(d, 'Clean'), '--stats-dir', stats,
                                              '--plots-dir', plots, '--clean-plots-dir', clean_plots,
                                              '--no-plots']), 0)
            self.assertEqual(sorted(os.listdir(stats)),
                             ['excluded_cases.csv', 'profile_qc_mean.csv',
                              'profile_qc_mean_clean.csv', 'summary_mean.csv', 'summary_mean_all.csv',
                              'summary_median.csv', 'summary_median_all.csv'])
            self.assertFalse(os.path.exists(plots) and os.listdir(plots))
            self.assertFalse(os.path.exists(clean_plots) and os.listdir(clean_plots))
            excluded = pd.read_csv(os.path.join(stats, 'excluded_cases.csv'), dtype=str)
            self.assertEqual(set(excluded['sub']), {'003'})
            self.assertEqual(set(excluded['reason']), {'profile'})
            clean = pd.read_csv(os.path.join(stats, 'summary_mean.csv'))
            everything = pd.read_csv(os.path.join(stats, 'summary_mean_all.csv'))
            self.assertNotIn('sub-003_ses-012m_dwi', set(clean['dataset']))
            self.assertIn('sub-003_ses-012m_dwi', set(everything['dataset']))
            self.assertEqual(len(everything), 2 * 8)

    def test_the_output_folders_are_in_the_out_dir(self):
        with tempfile.TemporaryDirectory() as d:
            norm, data, out = os.path.join(d, 'norm'), os.path.join(d, 'data'), os.path.join(d, 'QC')
            self._tables(norm, 12)
            self._tables(data, 8, outlier='sub-003_ses-012m_dwi')
            self.assertEqual(profile_qc.main(['--profiles-dir', norm, '-o', os.path.join(d, 'normQC'), '--no-plots']), 0)
            elsewhere = os.path.join(d, 'elsewhere', 'Plots_All')
            self.assertEqual(profile_qc.main(['--profiles-dir', data, '--prior-stats-dir', norm, '-o', out,
                                              '--clean-dir', 'Profiles_Clean', '--plots-dir', elsewhere]), 0)
            self.assertEqual(sorted(os.listdir(out)), ['Profiles_Clean', 'Profiles_Stats', 'StatsPlots_Clean'])
            self.assertTrue(os.path.isfile(os.path.join(out, 'Profiles_Stats', 'summary_mean.csv')))
            self.assertTrue(os.path.isfile(os.path.join(out, 'Profiles_Clean', 'CGH_R', 'CGH_R_fa.csv')))
            self.assertTrue(os.listdir(os.path.join(elsewhere, 'Plots')))  # an absolute path is used as given
            self.assertEqual(os.listdir(os.path.join(d, 'normQC')), ['Profiles_Stats'])  # --no-plots: no plot folder

class TestProfilesWithoutAge(unittest.TestCase):
    """A profile without an age is in no age bin, so it is not QC'd: kept by default, excluded with --exclude-no-age."""

    def _run(self, d, *options, plots=False):
        norm, data = os.path.join(d, 'norm'), os.path.join(d, 'data')
        TestOutputFolders._tables(norm, 12)
        TestOutputFolders._tables(data, 8)
        for f in Path(data).glob('*/*.csv'):  # a scan whose session name carries no age
            df = pd.read_csv(f, index_col=0)
            df.rename(columns={'sub-005_ses-012m_dwi': 'sub-005_ses-V1_dwi'}).to_csv(f)
        self.assertEqual(profile_qc.main(['--profiles-dir', norm, '-o', os.path.join(d, 'normQC'), '--no-plots']), 0)
        out = os.path.join(d, 'QC')
        self.assertEqual(profile_qc.main(['--profiles-dir', data, '--prior-stats-dir', norm, '-o', out,
                                          '--clean-dir', 'Profiles_Clean'] + ([] if plots else ['--no-plots'])
                                         + list(options)), 0)
        clean = pd.read_csv(os.path.join(out, 'Profiles_Clean', 'CGH_R', 'CGH_R_fa.csv'), index_col=0)
        stats = os.path.join(out, 'Profiles_Stats')
        return clean, stats

    def test_kept_without_the_option(self):
        with tempfile.TemporaryDirectory() as d:
            clean, stats = self._run(d)
            self.assertIn('sub-005_ses-V1_dwi', clean.columns)
            self.assertFalse(os.path.exists(os.path.join(stats, 'excluded_cases.csv')))

    def test_excluded_with_the_option(self):
        with tempfile.TemporaryDirectory() as d:
            clean, stats = self._run(d, '--exclude-no-age', plots=True)  # the plot of the excluded profiles too
            self.assertNotIn('sub-005_ses-V1_dwi', clean.columns)
            self.assertEqual(len(clean.columns), 7)
            excluded = pd.read_csv(os.path.join(stats, 'excluded_cases.csv'), dtype=str)
            self.assertEqual(excluded[['sub', 'ses', 'prefix', 'reason']].values.tolist(), [['005', 'V1', 'dwi', 'no age']])
            everything = pd.read_csv(os.path.join(stats, 'summary_mean_all.csv'))
            self.assertNotIn('sub-005_ses-V1_dwi', set(everything['dataset']))


class TestOneQCTable(unittest.TestCase):
    """profile_qc_<ref>.csv holds every profile compared with the prior and the decision of its tract and scan."""

    def test_the_decision_is_in_the_profile_qc_table(self):
        with tempfile.TemporaryDirectory() as d:
            norm, data, out = os.path.join(d, 'norm'), os.path.join(d, 'data'), os.path.join(d, 'QC')
            TestOutputFolders._tables(norm, 12)
            TestOutputFolders._tables(data, 8, outlier='sub-003_ses-012m_dwi')
            self.assertEqual(profile_qc.main(['--profiles-dir', norm, '-o', os.path.join(d, 'normQC'), '--no-plots']), 0)
            stale = os.path.join(out, 'Profiles_Stats', 'outliers_mean.csv')  # the table of earlier versions
            os.makedirs(os.path.dirname(stale))
            Path(stale).write_text('tract,subject_session,is_outlier\n')
            self.assertEqual(profile_qc.main(['--profiles-dir', data, '--prior-stats-dir', norm, '-o', out,
                                              '--no-plots']), 0)
            self.assertFalse(os.path.exists(stale))
            qc = pd.read_csv(os.path.join(out, 'Profiles_Stats', 'profile_qc_mean.csv'))
            self.assertEqual(len(qc), 2 * 2 * 8)  # tracts x metrics x scans
            self.assertEqual(list(qc.columns)[-6:], ['joint_frac_inside', 'joint_frac_valid', 'shape_r',
                                                     'is_value_outlier', 'is_shape_outlier', 'is_outlier'])
            flagged = qc[qc['is_outlier']]
            self.assertEqual(set(flagged['subject_session']), {'sub-003_ses-012m_dwi'})
            self.assertEqual(len(flagged), 4)  # the decision of a tract is on all its metrics
            self.assertTrue((qc['joint_frac_valid'] == 1.0).all())


class TestReportedAges(unittest.TestCase):
    """The ages in the tables of Profiles_Stats are floats in --age-units (months by default)."""

    def _run(self, d, *options):
        norm, data = os.path.join(d, 'norm'), os.path.join(d, 'data')
        TestOutputFolders._tables(norm, 12)
        TestOutputFolders._tables(data, 8, outlier='sub-003_ses-012m_dwi')
        ages = os.path.join(d, 'ages.csv')
        with open(ages, 'w') as f:  # sub-001 from the table (13.5 months), the others from the column names
            f.write('participant_id,session_id,age\nsub-001,ses-012m,{}\n'.format(1.125 if 'years' in options else 13.5))
        self.assertEqual(profile_qc.main(['--profiles-dir', norm, '-o', os.path.join(d, 'normQC'), '--no-plots']), 0)
        out = os.path.join(d, 'QC')
        self.assertEqual(profile_qc.main(['--profiles-dir', data, '--prior-stats-dir', norm, '-o', out,
                                          '--clean-dir', 'Profiles_Clean', '--no-plots', '--age-csv', ages]
                                         + list(options)), 0)
        return os.path.join(out, 'Profiles_Stats')

    def _ages(self, stats, name, column):
        t = pd.read_csv(os.path.join(stats, name))
        key = 'dataset' if 'dataset' in t.columns else 'subject_session' if 'subject_session' in t.columns else 'sub'
        return t, dict(zip(t[key].astype(str), t[column]))

    def test_months_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            stats = self._run(d)
            for name in ('summary_mean_all.csv', 'summary_median.csv', 'profile_qc_mean.csv',
                         'profile_qc_mean_clean.csv'):
                t, ages = self._ages(stats, name, 'age_months')
                self.assertNotIn('age', t.columns)
                self.assertEqual(ages['sub-001_ses-012m_dwi'], 13.5, name)
                self.assertEqual(ages['sub-000_ses-012m_dwi'], 12.0, name)
            excluded = pd.read_csv(os.path.join(stats, 'excluded_cases.csv'))
            self.assertEqual(list(excluded['age_months']), [12.0, 12.0])  # sub-003, in both tracts

    def test_the_age_units_of_the_table_are_those_of_the_output(self):
        with tempfile.TemporaryDirectory() as d:
            stats = self._run(d, '--age-units', 'years')
            for name in ('summary_mean_all.csv', 'profile_qc_mean.csv'):
                t, ages = self._ages(stats, name, 'age_years')
                self.assertEqual(ages['sub-001_ses-012m_dwi'], 1.125, name)
                self.assertEqual(ages['sub-000_ses-012m_dwi'], 1.0, name)
            self.assertEqual(list(pd.read_csv(os.path.join(stats, 'excluded_cases.csv'))['age_years']), [1.0, 1.0])


class TestPriorArcLengths(unittest.TestCase):
    """The prior is compared at the arc lengths of the profiles: the same up to rounding, or interpolated."""

    prior = pd.DataFrame({'a_mean': [0.0, 1.0, 2.0, np.nan, 4.0]}, index=pd.Index([0.0, 1.0, 2.0, 3.0, 4.0]))

    def _on(self, arcs):
        grid, how, n_outside = profile_qc.prior_on_grid(self.prior, pd.Index(arcs))
        return list(grid['a_mean']), how, n_outside

    def test_the_same_arc_lengths(self):
        self.assertEqual(self._on([1.0, 2.0]), ([1.0, 2.0], 'exact', 0))

    def test_arc_lengths_rounded_otherwise(self):
        self.assertEqual(self._on([0.0001, 1.0004, 1.9999]), ([0.0, 1.0, 2.0], 'rounding', 0))

    def test_another_sampling_is_interpolated(self):
        values, how, n_outside = self._on([0.5, 1.25, 2.5, 4.5])
        self.assertEqual(values[:2], [0.5, 1.25])
        self.assertTrue(np.isnan(values[2]))  # next to a position without prior
        self.assertTrue(np.isnan(values[3]))  # beyond the prior
        self.assertEqual((how, n_outside), ('interpolated', 1))

    def test_nothing_in_common(self):
        values, how, n_outside = self._on([10.0, 11.0])
        self.assertTrue(np.isnan(values).all())
        self.assertEqual((how, n_outside), ('none', 2))


class TestQCAtOtherArcLengths(unittest.TestCase):
    """End to end: profiles sampled at other arc lengths than the prior are still checked, and a run where no profile
    can be compared stops."""

    @staticmethod
    def _move(root, offset):
        for f in Path(root).glob('*/*.csv'):
            df = pd.read_csv(f, index_col=0)
            df.index = pd.Index(np.round(df.index.to_numpy() + offset, 4), name=df.index.name)
            df.to_csv(f)

    def _run(self, offset):
        d = self.tmp.name
        norm, data = os.path.join(d, 'norm'), os.path.join(d, 'data')
        TestOutputFolders._tables(norm, 12)
        TestOutputFolders._tables(data, 8, outlier='sub-003_ses-012m_dwi')
        self.assertEqual(profile_qc.main(['--profiles-dir', norm, '-o', os.path.join(d, 'normQC'), '--no-plots']), 0)
        self._move(data, offset)
        code = profile_qc.main(['--profiles-dir', data, '--prior-stats-dir', norm, '-o', os.path.join(d, 'QC'),
                                '--no-plots', '--envelope-batch-correct'])
        return code, os.path.join(d, 'QC', 'Profiles_Stats')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_rounded_and_interpolated_arc_lengths(self):
        for offset in (1e-4, 0.7):  # the grid spacing is 2
            with self.subTest(offset=offset):
                code, stats = self._run(offset)
                self.assertEqual(code, 0)
                shifts = pd.read_csv(os.path.join(stats, 'batch_shifts_mean.csv'))
                self.assertEqual(sorted(shifts['metric']), ['fa', 'md'])
                qc = pd.read_csv(os.path.join(stats, 'profile_qc_mean.csv'))
                self.assertTrue(qc['r'].notna().all())
                self.assertEqual(set(qc[qc['is_outlier']]['subject_session']), {'sub-003_ses-012m_dwi'})
                self.tearDown()
                self.setUp()

    def test_no_arc_length_in_common_stops(self):
        code, stats = self._run(100.0)
        self.assertEqual(code, 1)
        self.assertEqual(list(pd.read_csv(os.path.join(stats, 'batch_shifts_mean.csv')).columns),
                         ['metric', 'bin', 'kind', 'shift', 'n_profiles'])
        self.assertFalse(os.path.exists(os.path.join(stats, 'profile_qc_mean.csv')))


if __name__ == '__main__':
    unittest.main()


class TestScansMissingMostTracts(unittest.TestCase):
    """A scan with most of its tracts gone after the profile QC (absent, or outliers) is removed from the cleaned
    profiles altogether."""

    def test_absent_and_outlier_tracts_count(self):
        scans = {'T1': ['A', 'B', 'C', 'D'], 'T2': ['A', 'C', 'D'], 'T3': ['A', 'C'], 'T4': ['A']}
        with tempfile.TemporaryDirectory() as d:
            inputs = []
            for tract, cases in scans.items():
                header = 'Arc Length,' + ','.join('sub-{}_ses-010m_dwi'.format(c) for c in cases)
                row = '0,' + ','.join('0.5' for _ in cases)
                inputs.append(_write(os.path.join(d, tract, tract + '_fa.csv'), header + '\n' + row + '\n'))
            outliers = {'T2': {'sub-C_ses-010m_dwi'}, 'T3': {'sub-C_ses-010m_dwi'}}
            got = profile_qc.scans_missing_most_tracts(inputs, outliers, max_share=0.5)
            # B: 1 of 4 tracts (3 missing); C: 3 tracts, 2 of them outliers (3 missing); D: 2 of 4 (not more than half)
            self.assertEqual(got, {'sub-B_ses-010m_dwi': (3, 4), 'sub-C_ses-010m_dwi': (3, 4)})
            self.assertEqual(profile_qc.scans_missing_most_tracts(inputs, outliers, exclude_ids={'sub-B_ses-010m'},
                                                                  max_share=0.5), {'sub-C_ses-010m_dwi': (3, 4)})

    def test_the_cases_of_both_orientations(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(profile_qc.table_cases(_write(os.path.join(d, 'a.csv'), ARC_ROWS)), COLUMNS)
            self.assertEqual(profile_qc.table_cases(_write(os.path.join(d, 'b.csv'), CASE_ROWS)), COLUMNS)


class TestDiffusivityRange(unittest.TestCase):
    """A diffusivity above that of free water (failed fit) is read as missing: that value only, not the location on the
    other metrics nor the whole profile."""

    def setUp(self):
        profile_qc.set_outside_brain({})
        profile_qc.set_out_of_range({})
        self.addCleanup(profile_qc.set_out_of_range, {})

    def _tree(self, d, tables):
        return {key: _table(os.path.join(d, key[0], '{}_{}.csv'.format(*key)), values) for key, values in tables.items()}

    def test_only_the_values_above_the_limit_are_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._tree(d, {
                ('CG_L', 'FWAD'): {'a_ses-012m': [1.2e-3] * 5, 'b_ses-012m': [1.2e-3, 7.0, 1.3e-3, 4e-3, 1.2e-3]},
                ('CG_L', 'FWFA'): {'a_ses-012m': [0.4] * 5, 'b_ses-012m': [0.4] * 5},
                ('CG_L', 'md'): {'a_ses-012m': [1.1e-3] * 5, 'b_ses-012m': [3.4e-3] * 5},  # high: a lesion
            })
            masks, rows = profile_qc.find_out_of_range(sorted(paths.values()))
            self.assertEqual(list(masks), [('CG_L', 'FWAD')])
            self.assertEqual(profile_qc.set_out_of_range(masks), 2)
            fwad = profile_qc.load_profile_table(paths[('CG_L', 'FWAD')])
            self.assertEqual(list(fwad.index[fwad['b_ses-012m'].isna()]), [-1, 1])
            self.assertFalse(fwad['a_ses-012m'].isna().any())
            self.assertFalse(profile_qc.load_profile_table(paths[('CG_L', 'FWFA')]).isna().any().any())
            self.assertFalse(profile_qc.load_profile_table(paths[('CG_L', 'md')]).isna().any().any())
            r = rows.iloc[0]
            self.assertEqual((r['case'], r['metric'], r['n_out_of_range'], r['max_value']), ('b_ses-012m', 'FWAD', 2, 7.0))
            self.assertEqual((r['arc_from'], r['arc_to']), (-1.0, 1.0))
            target = os.path.join(d, 'clean', 'CG_L_FWAD.csv')
            self.assertEqual(profile_qc.write_without_columns(paths[('CG_L', 'FWAD')], target, set()), 2)
            self.assertEqual(int(profile_qc.read_profile_table(target)['b_ses-012m'].isna().sum()), 2)

    def test_tables_in_micrometers_and_the_lower_limit(self):
        with tempfile.TemporaryDirectory() as d:
            paths = self._tree(d, {('CG_L', 'rd'): {'a_ses-012m': [0.5, 0.6, 3.8, 1e-6, 0.0]}})  # 10^-3 mm^2/s
            masks, _ = profile_qc.find_out_of_range(sorted(paths.values()))
            self.assertEqual(list(masks[('CG_L', 'rd')]['a_ses-012m']), [False, False, True, False, False])
            masks, rows = profile_qc.find_out_of_range(sorted(paths.values()), min_value=5e-5)
            self.assertEqual(list(masks[('CG_L', 'rd')]['a_ses-012m']), [False, False, True, True, False])
            self.assertAlmostEqual(rows.iloc[0]['max_value'], 3.8e-3)
            masks, _ = profile_qc.find_out_of_range(sorted(paths.values()), max_value=0)
            self.assertEqual(masks, {})
