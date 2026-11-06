"""N4 bias field correction of the mask input (BRAIN_Mask n4BiasCorrection)."""
import unittest

import numpy as np

from dtiplayground.dmri.common import n4


class TestN4(unittest.TestCase):

    def test_recovers_a_smooth_field(self):
        n = 48
        x, y, z = np.meshgrid(*[np.linspace(-1, 1, n)] * 3, indexing='ij')
        head = (x ** 2 + y ** 2 + z ** 2) < 0.8
        rng = np.random.default_rng(0)
        i, j, k = np.indices(x.shape) // 3
        tissue = (i + j + k) % 2  # two tissues in 3-voxel blocks: finer than any bias field
        image = np.where(head, 100.0 + 30.0 * tissue + rng.normal(0, 2, x.shape), 0.0)
        bias = np.exp(0.4 * x + 0.2 * y)  # x0.55 .. x1.8
        corrected, field = n4.n4_correct(image * bias, (2.0, 2.0, 2.0), shrink_factor=2)
        self.assertEqual(corrected.shape, image.shape)
        ratio = (field / bias)[head]
        ratio /= np.median(ratio)
        self.assertLess(np.percentile(ratio, 95) / np.percentile(ratio, 5), 1.15)  # the field is found, up to a scale
        cv = lambda v: np.std(v[head]) / np.mean(v[head])
        self.assertLess(cv(corrected), 1.1 * cv(image))  # back to the contrast of the tissues
        self.assertGreater(cv(image * bias), 1.5 * cv(image))

    def test_spacing_and_empty(self):
        self.assertEqual(n4.spacing_of(np.diag([1.5, 2.0, 2.5, 1.0])), (1.5, 2.0, 2.5))
        corrected, field = n4.n4_correct(np.zeros((8, 8, 8)))
        self.assertFalse(corrected.any())
        self.assertTrue((field == 1).all())


if __name__ == '__main__':
    unittest.main()
