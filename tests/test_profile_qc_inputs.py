import os
import tempfile
import unittest
from pathlib import Path

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


if __name__ == '__main__':
    unittest.main()
