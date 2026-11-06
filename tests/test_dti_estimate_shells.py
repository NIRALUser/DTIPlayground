"""DTI_Estimate maxBValue: the shells above it are left out of the tensor fit."""
import unittest

import numpy as np

import dtiplayground.dmri.preprocessing.modules  # noqa: F401  (DTIPrepModule)
from dtiplayground.dmri.preprocessing.modules.DTI_Estimate import DTI_Estimate as dti_estimate


class _Image:
    def __init__(self, bvals):
        self.bvals = bvals

    def getGradients(self):
        return [{'b_value': b, 'unit_gradient': [1.0, 0.0, 0.0]} for b in self.bvals]


def _module(bvals, **protocol):
    obj = dti_estimate.DTI_Estimate.__new__(dti_estimate.DTI_Estimate)
    obj.protocol = protocol
    obj.image = _Image(bvals)
    dti_estimate.logger = lambda *a, **k: None
    return obj


class TestFitVolumes(unittest.TestCase):

    BVALS = [0, 5, 498, 502, 1595, 1605, 1600, 2997, 3003, 0]

    def test_default_drops_the_shells_above_1600(self):
        use, description = _module(self.BVALS).fitVolumes()
        np.testing.assert_array_equal(use, [True] * 7 + [False, False, True])  # 1605 is in the shell of 1600, kept
        self.assertIn('3000 above maxBValue 1600', description)

    def test_limit(self):
        use, _ = _module(self.BVALS, maxBValue=1000).fitVolumes()
        np.testing.assert_array_equal(use, [True, True, True, True, False, False, False, False, False, True])
        for off in (0, '', None):
            use, description = _module(self.BVALS, maxBValue=off).fitVolumes()
            self.assertTrue(use.all(), off)
            self.assertIn('all 10 volumes', description)

    def test_single_high_shell_uses_everything(self):
        use, description = _module([0, 2000, 2000, 2005, 0]).fitVolumes()
        self.assertTrue(use.all())
        self.assertIn('no shell at or below maxBValue 1600', description)

    def test_not_a_number(self):
        with self.assertRaises(ValueError):
            _module(self.BVALS, maxBValue='high').fitVolumes()


class TestTractographyFitVolumes(unittest.TestCase):
    """BRAIN_Tractography fits its tensor on the shells of DTI_Estimate: its maxBValue, else DTI_Estimate's."""

    def _module(self, protocol, global_variables):
        from dtiplayground.dmri.preprocessing.modules.BRAIN_Tractography import BRAIN_Tractography as bt
        obj = bt.BRAIN_Tractography.__new__(bt.BRAIN_Tractography)
        obj.protocol, obj.global_variables = protocol, global_variables
        bt.logger = lambda *a, **k: None
        return obj

    def test_precedence(self):
        bvals = [0, 500, 1500, 3000, 3000]
        fit = lambda m: m.fitVolumes(bvals)[0].tolist()
        self.assertEqual(fit(self._module({}, {})), [True, True, True, False, False])            # 1600
        self.assertEqual(fit(self._module({'maxBValue': None}, {'dti_max_bvalue': 0})), [True] * 5)  # DTI_Estimate's
        self.assertEqual(fit(self._module({'maxBValue': 1000}, {'dti_max_bvalue': 0})),
                         [True, True, False, False, False])                                            # its own


class TestMultiShell(unittest.TestCase):
    """MULTI_SHELL_Estimate: the DTI model's shells (maxBValue) and the names of its outputs."""

    def _module(self, protocol, global_vars, output_dir='/x/12_MULTI_SHELL_Estimate'):
        from dtiplayground.dmri.preprocessing.modules.MULTI_SHELL_Estimate import MULTI_SHELL_Estimate as ms
        obj = ms.MULTI_SHELL_Estimate.__new__(ms.MULTI_SHELL_Estimate)
        obj.protocol, obj.global_vars, obj.output_dir = protocol, global_vars, output_dir
        ms.logger = lambda *a, **k: None
        return obj

    def test_shells(self):
        bvals = [0, 500, 1500, 3000]
        self.assertEqual(self._module({}, {}).fitVolumes(bvals)[0].tolist(), [True, True, True, False])
        self.assertEqual(self._module({'maxBValue': 0}, {}).fitVolumes(bvals)[0].tolist(), [True] * 4)

    def test_output_names(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            tensor = os.path.join(d, '07_DTI_Estimate', 'tensor.nrrd')
            os.makedirs(os.path.dirname(tensor))
            open(tensor, 'w').close()
            own = os.path.join(d, '12_MULTI_SHELL_Estimate')
            self.assertEqual(self._module({}, {'dti_path': tensor}, own).outputName('dti'), 'MULTI_SHELL_DTI')
            self.assertEqual(self._module({}, {}, own).outputName('dti'), 'DTI')  # without DTI_Estimate
            self.assertEqual(self._module({}, {'dti_path': os.path.join(d, 'gone.nrrd')}, own).outputName('dti'), 'DTI')
            self.assertEqual(self._module({}, {'dti_path': tensor}, own).outputName('dki'), 'DKI')


    def test_adc(self):
        from dtiplayground.dmri.preprocessing.modules.MULTI_SHELL_Estimate.MULTI_SHELL_Estimate import MULTI_SHELL_Estimate
        bvals = np.array([0, 0, 500, 500, 1500, 3000], dtype=float)
        s0, adc = np.array([[1000.0, 250.0]]), np.array([[0.0008, 0.0021]])
        data = s0[..., None] * np.exp(-bvals * adc[..., None])
        fs0, fadc = MULTI_SHELL_Estimate.fitADC(data, bvals)
        np.testing.assert_allclose(fs0, s0, rtol=1e-10)
        np.testing.assert_allclose(fadc, adc, rtol=1e-10)
        # a zero signal (background) gives finite values, as dwi2adc
        self.assertTrue(np.isfinite(MULTI_SHELL_Estimate.fitADC(np.zeros((2, 6)), bvals)).all())


    def test_models_of_the_tools(self):
        m = self._module({}, {})
        self.assertEqual(m.checkModel('dipy', 'dki'), 'dki')
        self.assertEqual(m.checkModel('amico', 'noddi'), 'noddi')
        self.assertEqual(m.checkModel('amico', 'dti'), 'noddi')     # protocols before 0.9.6
        self.assertEqual(m.checkModel('mrtrix3', 'adc'), 'adc')
        self.assertEqual(m.checkModel('mrtrix3', 'dki'), 'adc')
        with self.assertRaisesRegex(ValueError, 'tool amico'):
            m.checkModel('dipy', 'noddi')
        with self.assertRaisesRegex(ValueError, 'tool mrtrix3'):
            m.checkModel('dipy', 'adc')


if __name__ == '__main__':
    unittest.main()
