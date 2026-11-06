"""DTI_Estimate writes its tensor as a 3D-symmetric-matrix NRRD with the components first (teem / 3D Slicer)."""
import os
import tempfile
import unittest

import nrrd
import numpy as np

import dtiplayground.dmri.preprocessing.modules  # noqa: F401
from dtiplayground.dmri.common.dwi import DWI
from dtiplayground.dmri.preprocessing.modules.DTI_Estimate.DTI_Estimate import write_tensor_nrrd

DIRECTIONS = [[1.48, -0.21, -0.07], [0.21, 1.48, -0.05], [0.08, 0.04, 1.5]]  # oblique, as the IBIS scans


def _dwi(path, gradient_axis_first):
    shape = (5, 6, 7)
    data = np.random.default_rng(0).random(shape + (4,)).astype(np.float32)
    kinds = ['domain', 'domain', 'domain', 'list']
    directions = DIRECTIONS + [[np.nan] * 3]
    centerings = ['cell', 'cell', 'cell', '???']
    if gradient_axis_first:
        data, kinds, directions, centerings = (np.moveaxis(data, 3, 0), kinds[3:] + kinds[:3],
                                               directions[3:] + directions[:3], centerings[3:] + centerings[:3])
    header = {'type': 'float', 'dimension': 4, 'space': 'left-posterior-superior', 'kinds': kinds,
              'space directions': directions, 'space origin': [-10.0, -20.0, -30.0], 'centerings': centerings,
              'measurement frame': [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 'modality': 'DWMRI', 'DWMRI_b-value': '1000',
              'DWMRI_gradient_0000': '0 0 0', 'DWMRI_gradient_0001': '1 0 0', 'DWMRI_gradient_0002': '0 1 0',
              'DWMRI_gradient_0003': '0 0 1'}
    nrrd.write(path, data, header)
    return shape


class TestTensorNrrd(unittest.TestCase):

    def test_components_first(self):
        for first in (True, False):
            with self.subTest(gradient_axis_first=first), tempfile.TemporaryDirectory() as d:
                shape = _dwi(os.path.join(d, 'dwi.nrrd'), first)
                dwi = DWI(os.path.join(d, 'dwi.nrrd'))
                tensor = np.random.default_rng(1).random(shape + (6,)).astype(np.float32)
                image = DWI()
                image.copyFrom(dwi, image=False, gradients=False)
                image.setImage(tensor, modality='DTI', kinds=['space', 'space', 'space', '3D-symmetric-matrix'])
                image.setSpaceDirection(target_space=dwi.information['space'])
                write_tensor_nrrd(image, os.path.join(d, 'tensor.nrrd'))
                data, header = nrrd.read(os.path.join(d, 'tensor.nrrd'))
                self.assertEqual(list(header['sizes']), [6, 5, 6, 7])
                self.assertEqual(list(header['kinds']), ['3D-symmetric-matrix', 'space', 'space', 'space'])
                self.assertTrue(np.isnan(header['space directions'][0]).all())
                np.testing.assert_allclose(header['space directions'][1:], DIRECTIONS, atol=1e-6)
                np.testing.assert_allclose(header['space origin'], [-10, -20, -30])
                self.assertNotIn('centerings', header)
                self.assertEqual(header['modality'], 'DTI')
                np.testing.assert_array_equal(data, np.moveaxis(tensor, 3, 0))


if __name__ == '__main__':
    unittest.main()
