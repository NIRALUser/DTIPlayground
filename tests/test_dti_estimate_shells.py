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


if __name__ == '__main__':
    unittest.main()
