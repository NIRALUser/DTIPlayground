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
            self.assertEqual(age_table.load_age_table(p, 'months')[('1', None)], 1.5) # kept as a float

    def test_age_bins_hold_the_fractional_ages(self):
        self.assertTrue(age_table.in_age_bin(3.5, 0, 3))  # 0-3m: from 0 up to 4 months
        self.assertFalse(age_table.in_age_bin(4.0, 0, 3))
        self.assertTrue(age_table.in_age_bin(4.0, 4, 9))
        self.assertTrue(age_table.in_age_bin(80.2, 10, float('inf')))
        self.assertFalse(age_table.in_age_bin(None, 0, 3))

    def test_ages_in_other_units(self):
        self.assertEqual(age_table.months_to(18.0, 'years'), 1.5)
        self.assertEqual(age_table.months_to(18.0), 18.0)
        self.assertIsNone(age_table.months_to(None, 'years'))

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

    def _ibis(self, d):
        return os.path.join(d, 'Data_DTI', '999434', 'VSA-CVD', 'mask', '999434_VSA-CVD_CMRR_APPA_topupEddy_corr_noNeg_tensor.nrrd')

    def test_the_ibis_organization(self):
        """A 6 digit id folder followed by a visit folder starting with V, when the path has no BIDS entities."""
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._module({}, self._ibis(d)).subjectSession(), ('999434', 'SA-CVD'))
            for session in ('SA-CVD', 'VSA-CVD'):  # the table may name the visit with or without its V
                p = _table(d, 'ages.csv', 'participant_id,session_id,age\n999434,{},25\n'.format(session))
                self.assertEqual(self._module({'ageCSV': p}, self._ibis(d)).subjectAge(), 25.0)


class TestNamedColumns(unittest.TestCase):

    def test_the_subject_and_session_columns_can_be_named(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'ScanID,Identifiers,VisitName,AgeAtScan\nx,999434,VSA-CVD,25\n')
            self.assertRaises(ValueError, age_table.load_age_table, p)  # no subject column detected
            table = age_table.load_age_table(p, age_column='AgeAtScan', subject_column='identifiers',
                                             session_column='VisitName')
            self.assertEqual(table, {('999434', 'vsa-cvd'): 25})
            self.assertEqual(age_table.age_from_table('999434', 'SA-CVD', table), 25)
            with self.assertRaises(ValueError):
                age_table.load_age_table(p, age_column='AgeAtScan', subject_column='nope')

    def test_ibis_style_columns_are_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'CandID,Visit_label,age\n999434,V24,24\n')
            self.assertEqual(age_table.load_age_table(p), {('999434', 'v24'): 24})

    def test_dti_register_named_columns(self):
        dti = TestDTIRegisterAge()
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'Identifiers,VisitName,AgeAtScan\n999434,VSA-CVD,25\n')
            protocol = {'ageCSV': p, 'ageColumn': 'AgeAtScan', 'ageSubjectColumn': 'Identifiers',
                        'ageSessionColumn': 'VisitName'}
            self.assertEqual(dti._module(protocol, dti._ibis(d)).subjectAge(), 25.0)


class TestAgeFallback(unittest.TestCase):
    """The fallback age of the scans without one (DTI_Register ageFallback, dmrifiberprofile --age-fallback): used only
    when no other source gives an age."""

    def test_the_units_of_the_fallback(self):
        self.assertIsNone(age_table.age_fallback_months(None))
        self.assertEqual(age_table.age_fallback_months(24), 24.0)
        self.assertEqual(age_table.age_fallback_months(2, 'years'), 24.0)
        self.assertEqual(age_table.age_fallback_months(0), 0.0)
        with self.assertRaises(ValueError):
            age_table.age_fallback_months(-1)

    def test_dti_register_uses_the_fallback_last(self):
        dti = TestDTIRegisterAge()
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'ages.csv', 'participant_id,session_id,age\nsub-1234,ses-V02,14\n')
            self.assertEqual(dti._module({'ageFallback': 30}, dti._paths(d)).subjectAge(), 30.0)  # nothing else
            self.assertEqual(dti._module({'ageFallback': 30, 'ageCSV': p}, dti._paths(d)).subjectAge(), 14.0)
            self.assertEqual(dti._module({'ageFallback': 30}, dti._paths(d, 'ses-006m')).subjectAge(), 6.0)
            self.assertEqual(dti._module({'ageFallback': 30, 'age': 7}, dti._paths(d)).subjectAge(), 7.0)
            other = os.path.join(d, 'sub-9999', 'ses-V02', 'sub-9999_ses-V02_dwi_DTI.nrrd')  # not in the table
            self.assertEqual(dti._module({'ageFallback': 30, 'ageCSV': p}, other).subjectAge(), 30.0)

    def test_dti_register_fallback_from_the_global_variables(self):
        dti = TestDTIRegisterAge()
        with tempfile.TemporaryDirectory() as d:
            for name in ('ageFallback', 'age_fallback'):
                module = dti._module({}, dti._paths(d))
                module.global_variables = {name: '30'}
                self.assertEqual(module.subjectAge(), 30.0)

    def test_dti_register_ignores_an_invalid_fallback(self):
        dti = TestDTIRegisterAge()
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(dti._module({'ageFallback': -3}, dti._paths(d)).subjectAge())
            self.assertIsNone(dti._module({'ageFallback': 'old'}, dti._paths(d)).subjectAge())

    def test_qc_registration_session_age(self):
        import re
        from dtiplayground.dmri.fiberprofile.analysis import registration_qc as rq
        pattern = re.compile(r'ses-(\d+)m')
        table = {('1234', 'v02'): 14.0}
        self.assertEqual(rq.age_for_session('sub-1234', 'ses-V02', table, pattern, 30.0), 14.0)
        self.assertEqual(rq.age_for_session('sub-1234', 'ses-006m', None, pattern, 30.0), 6.0)
        self.assertEqual(rq.age_for_session('sub-5678', 'ses-V02', table, pattern, 30.0), 30.0)
        self.assertIsNone(rq.age_for_session('sub-5678', 'ses-V02', table, pattern))

    def test_impute_profiles_scan_ages(self):
        from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip, profile_qc
        self.addCleanup(profile_qc.set_age_source)
        cohort = type('Cohort', (), {'scans': ['sub-1_ses-006m_x', 'sub-2_ses-V02_x']})()
        self.assertEqual(ip.scan_ages(cohort), [6.0, None])
        self.assertEqual(ip.scan_ages(cohort, fallback=30), [6.0, 30.0])
        self.assertEqual(ip.scan_ages(cohort, age_units='years', fallback=2), [6.0, 24.0])


class TestDTIRegisterGlobalVariables(unittest.TestCase):
    """The age options given as global variables (dmriprep run -g age_csv ... ageColumn ...), with a LORIS export whose
    column names hold a comma."""

    def test_loris_table_from_global_variables(self):
        dti = TestDTIRegisterAge()
        with tempfile.TemporaryDirectory() as d:
            p = _table(d, 'loris.csv', '"VSA demographics,CandID","VSA demographics,Visit_label",'
                                       '"VSA demographics,Age_at_visit_start"\n105477,VSA,150.5\n999434,VSA,140\n')
            path = os.path.join(d, '105477', 'VSA', 'mask', '105477_VSA_APPA_topupEddy_corr_noNeg_FWtensor.nrrd')
            for names in (('ageColumn', 'ageSubjectColumn'), ('age_column', 'age_subject_column')):
                module = dti._module({}, path)
                module.global_variables = {'age_csv': p, names[0]: 'VSA demographics,Age_at_visit_start',
                                           names[1]: 'VSA demographics,CandID'}
                self.assertEqual(module.subjectAge(), 150.5)
                module.global_variables['age_units'] = 'years'
                self.assertEqual(module.subjectAge(), 150.5 * 12)

    def test_the_protocol_wins_over_the_global_variables(self):
        dti = TestDTIRegisterAge()
        module = dti._module({'ageColumn': 'a'}, '/x/a.nrrd')
        module.global_variables = {'ageColumn': 'b', 'age_csv': 'c.csv'}
        self.assertEqual(module.ageOption('ageColumn'), 'a')
        self.assertEqual(module.ageOption('ageCSV'), 'c.csv')
        self.assertIsNone(module.ageOption('ageSessionColumn'))


class TestSubjectSessionFromPath(unittest.TestCase):

    def test_bids_wins_over_ibis(self):
        self.assertEqual(age_table.subject_session_from_path('/x/123456/V12/sub-1/ses-2/a.nrrd'), ('1', '2'))

    def test_ibis(self):
        self.assertEqual(age_table.subject_session_from_path('/x/999434/VSA-CVD/mask/a.nrrd'), ('999434', 'SA-CVD'))
        self.assertEqual(age_table.subject_session_from_path(None, '/x/123456/V06'), ('123456', '06'))

    def test_not_ibis(self):
        for path in ('/x/99943/VSA-CVD/a.nrrd', '/x/9994345/V06/a.nrrd', '/x/999434/SA-CVD/a.nrrd', '/x/999434',
                     '/x/a.nrrd'):
            self.assertEqual(age_table.subject_session_from_path(path), (None, None), path)

    def test_the_visit_matches_with_or_without_v(self):
        table = {('999434', 'sa-cvd'): 25, ('123456', 'v06'): 6}
        self.assertEqual(age_table.age_from_table('999434', 'VSA-CVD', table), 25)
        self.assertEqual(age_table.age_from_table('999434', 'SA-CVD', table), 25)
        self.assertEqual(age_table.age_from_table('123456', '06', table), 6)
        self.assertIsNone(age_table.age_from_table('123456', '12', table))


class TestRegistrationQCIbis(unittest.TestCase):

    def test_parse_registered(self):
        from dtiplayground.dmri.fiberprofile.analysis.registration_qc import parse_registered
        path = '/data/999434/VSA-CVD/mask/999434_VSA-CVD_CMRR_APPA_tensor_Registered_DTI_FA.nii.gz'
        self.assertEqual(parse_registered(path), ('999434', 'VSA-CVD', 'CMRR_APPA_tensor', 'FA'))
        self.assertIsNone(parse_registered('/data/x/scan_Registered_FA.nii.gz'))


if __name__ == '__main__':
    unittest.main()
