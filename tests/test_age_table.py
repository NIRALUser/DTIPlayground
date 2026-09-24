import os
import tempfile
import unittest

from dtiplayground.dmri.common import age_table
from dtiplayground.dmri.preprocessing.modules.DTI_Register import DTI_Register as dti_register

dti_register.logger = lambda *args, **kwargs: None # the module logger is set in __init__, which the tests bypass


def _table(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, 'w') as f:
        f.write(text)
    return path


class TestLoadAgeTable(unittest.TestCase):
    """The table of 'qc-registration --age-csv' and of the DTI_Register protocol option ageCSV."""

    def test_subject_and_session_columns_are_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'a.csv', 'participant_id,session_id,age\nsub-1234,ses-V02,14\nsub-9999,ses-V01,3\n')
            table = age_table.load_age_table(p)
        self.assertEqual(table[('1234', 'v02')], 14)
        self.assertEqual(table[('9999', 'v01')], 3)

    def test_a_table_without_sessions_gives_one_age_per_subject(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'a.csv', 'participant_id,age_months\nsub-1234,20\n')
            table = age_table.load_age_table(p)
        self.assertEqual(table[('1234', None)], 20)
        self.assertEqual(age_table.age_from_table('sub-1234', 'ses-anything', table), 20)

    def test_the_units_are_converted_to_months(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'a.csv', 'participant_id,age\nsub-1,1.5\n')
            self.assertEqual(age_table.load_age_table(p, 'years')[('1', None)], 18)
            self.assertEqual(age_table.load_age_table(p, 'months')[('1', None)], 2) # 1.5 rounds to 2

    def test_a_tab_separated_table_and_rows_without_an_age(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'a.tsv', 'participant_id\tsession_id\tage\nsub-1\tses-1\t7\nsub-2\tses-1\tn/a\n')
            table = age_table.load_age_table(p)
        self.assertEqual(table, {('1', '1'): 7}) # the BIDS 'n/a' row is left out

    def test_the_age_column_can_be_named(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'a.csv', 'participant_id,age,corrected_age\nsub-1,7,9\n')
            self.assertEqual(age_table.load_age_table(p)[('1', None)], 7) # 'age' is detected
            self.assertEqual(age_table.load_age_table(p, age_column='corrected_age')[('1', None)], 9)
            with self.assertRaises(ValueError):
                age_table.load_age_table(p, age_column='nope')

    def test_a_table_without_an_age_or_subject_column_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertRaises(ValueError, age_table.load_age_table, _table(d, 'a.csv', 'participant_id,x\nsub-1,7\n'))
            self.assertRaises(ValueError, age_table.load_age_table, _table(d, 'b.csv', 'thing,age\nx,7\n'))

    def test_the_session_entry_wins_over_the_subject_entry(self):
        table = {('1', None): 20, ('1', 'v02'): 14}
        self.assertEqual(age_table.age_from_table('sub-1', 'ses-V02', table), 14)
        self.assertEqual(age_table.age_from_table('sub-1', 'ses-V03', table), 20)
        self.assertIsNone(age_table.age_from_table('sub-2', 'ses-V02', table))
        self.assertIsNone(age_table.age_from_table(None, 'ses-V02', table))


class TestDTIRegisterAge(unittest.TestCase):
    """DTI_Register picks the age bin of the normative model from the protocol age, the age table, or the path."""

    REGEX = r'ses-(\d+)m'

    def _module(self, protocol, path):
        obj = dti_register.DTI_Register.__new__(dti_register.DTI_Register)
        obj.protocol = dict({'ageRegex': self.REGEX}, **protocol)
        obj.global_variables = {}
        obj.dtiImagePath = path
        obj.image = type('Image', (), {'filename': path})()
        obj.output_dir = os.path.dirname(path)
        return obj

    def _paths(self, d, session='ses-V02'):
        """A scan whose session name carries no age."""
        return os.path.join(d, 'sub-1234', session, 'sub-1234_{}_dwi_DTI.nrrd'.format(session))

    def test_the_age_comes_from_the_table_when_the_session_has_none(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'participant_id,session_id,age\nsub-1234,ses-V02,14\n')
            self.assertEqual(self._module({'ageCSV': p}, self._paths(d)).subjectAge(), 14.0)

    def test_without_a_table_and_without_an_age_in_the_session(self):
        """The registration then falls back to the reference image instead of a normative bin."""
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(self._module({}, self._paths(d)).subjectAge())

    def test_the_protocol_age_wins_over_the_table(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'participant_id,session_id,age\nsub-1234,ses-V02,14\n')
            self.assertEqual(self._module({'ageCSV': p, 'age': 7}, self._paths(d)).subjectAge(), 7.0)

    def test_the_table_wins_over_the_session_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'participant_id,session_id,age\nsub-1234,ses-006m,9\n')
            path = self._paths(d, 'ses-006m')
            self.assertEqual(self._module({}, path).subjectAge(), 6.0)            # the regex alone
            self.assertEqual(self._module({'ageCSV': p}, path).subjectAge(), 9.0) # the table

    def test_the_units_of_the_table(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'participant_id,session_id,age\nsub-1234,ses-V02,1.5\n')
            self.assertEqual(self._module({'ageCSV': p, 'ageUnits': 'years'}, self._paths(d)).subjectAge(), 18.0)

    def test_a_scan_that_is_not_in_the_table_falls_back_to_the_session(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'participant_id,session_id,age\nsub-9999,ses-006m,3\n')
            path = os.path.join(d, 'sub-1234', 'ses-006m', 'sub-1234_ses-006m_dwi_DTI.nrrd')
            self.assertEqual(self._module({'ageCSV': p}, path).subjectAge(), 6.0)

    def test_a_missing_table_falls_back_to_the_session(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'sub-1234', 'ses-006m', 'sub-1234_ses-006m_dwi_DTI.nrrd')
            self.assertEqual(self._module({'ageCSV': os.path.join(d, 'nope.csv')}, path).subjectAge(), 6.0)

    def test_the_subject_and_session_are_read_from_the_path(self):
        with tempfile.TemporaryDirectory() as d:
            module = self._module({}, self._paths(d))
            self.assertEqual(module.subjectSession(), ('1234', 'V02'))
            self.assertEqual(self._module({}, os.path.join(d, 'no_entities.nrrd')).subjectSession(), (None, None))


if __name__ == '__main__':
    unittest.main()
