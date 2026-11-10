import os
import tempfile
import unittest

import numpy as np

from dtiplayground.dmri.common import tensor_registration as tr
from dtiplayground.dmri.fiberprofile.analysis import frame_align
from dtiplayground.dmri.preprocessing.modules.DTI_Register import DTI_Register as dti_register

dti_register.logger = lambda *args, **kwargs: None  # the module logger is set in __init__, which the tests bypass


def tensor_field(shape=(24, 24, 24)):
    """Physical tensors (1e-3 mm^2/s) of a phantom: a ring of white matter (principal direction tangent to the ring,
    in the x-y plane) crossing a straight z tract, isotropic elsewhere."""
    X, Y, Z = np.meshgrid(*[np.arange(n) - (n - 1) / 2 for n in shape], indexing='ij')
    T = np.zeros(shape + (3, 3)) + np.eye(3) * 0.8
    r = np.sqrt(X ** 2 + Y ** 2)
    ring = (np.abs(r - 7) < 2.5) & (np.abs(Z) < 4)
    t = np.stack([-Y, X, np.zeros_like(X)], -1) / np.maximum(r, 1e-6)[..., None]
    T[ring] = 0.3 * np.eye(3) + 1.2 * t[ring][:, :, None] * t[ring][:, None, :]
    line = (np.abs(X - 3) < 2) & (np.abs(Y + 2) < 2)
    T[line] = 0.3 * np.eye(3) + np.diag([0, 0, 1.2])
    return T


def write_tensor_nrrd(path, T, scale=1e-3):
    import nrrd
    data = np.stack([T[..., 0, 0], T[..., 0, 1], T[..., 0, 2], T[..., 1, 1], T[..., 1, 2], T[..., 2, 2]], 0) * scale
    header = {'kinds': ['3D-symmetric-matrix', 'space', 'space', 'space'], 'space': 'left-posterior-superior',
              'space directions': [[np.nan] * 3, [1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], 'space origin': [0.0, 0.0, 0.0],
              'measurement frame': np.eye(3)}
    nrrd.write(str(path), data.astype(np.float32), header)


def rotation(axis, deg):
    from scipy.spatial.transform import Rotation
    return Rotation.from_rotvec(np.radians(deg) * np.asarray(axis, float)).as_matrix()


class TestFrameAlign(unittest.TestCase):
    """The rotation of the tensor frame is recovered: a flip/axis swap plus a continuous rotation."""

    def test_recovers_a_flip_and_a_rotation(self):
        T = tensor_field()
        R_true = rotation([1, 0, 0], 17) @ np.diag([-1.0, -1.0, 1.0])  # 180 deg about z (= a z flip) and 17 deg about x
        with tempfile.TemporaryDirectory() as d:
            ref, sub, fixed = (os.path.join(d, n) for n in ('ref.nrrd', 'sub.nrrd', 'fixed.nrrd'))
            write_tensor_nrrd(ref, T)
            write_tensor_nrrd(sub, R_true.T @ T @ R_true)  # frame rotated by R_true^-1
            r = frame_align.estimate(sub, ref, (np.eye(3), np.zeros(3)), fa_ref=0.3, fa_sub=0.2)
            R = np.asarray(r['R'])
            self.assertLess(r['angle_rotation'], 0.5)
            self.assertGreater(r['angle_identity'], 10)
            # R and -R give the same tensor: compare the tensors
            self.assertTrue(np.allclose(R @ (R_true.T @ T[12, 12, 12] @ R_true) @ R.T, T[12, 12, 12], atol=1e-3))
            frame_align.rotate_tensor_file(sub, fixed, R)
            T_fixed, _ = tr.read_tensor_nrrd(fixed)
            self.assertTrue(np.allclose(T_fixed, T, atol=2e-3))


class TestTensorRegistration(unittest.TestCase):
    """The diffeomorphic tensor registration (CPU) undoes a known translation."""

    def test_recovers_a_translation(self):
        T = tensor_field()
        S = np.roll(T, 2, axis=0)  # subject: the phantom 2 voxels further along x
        Lr, Ls = tr.logm(T), tr.logm(S)
        mask = np.ones(T.shape[:3], np.float32)
        params = dict(levels=(2, 1), iters=(60, 40), w_reg=0.05, smooth=0.5)
        u, ui = tr.register_arrays(Lr, Ls, mask, np.eye(3), params, tr.resolve_device('cpu'))
        from scipy import ndimage
        wm = tr.fa_of(T) > 0.3
        self.assertAlmostEqual(float(np.median(u[wm][:, 0])), 2.0, delta=0.5)  # reference x -> subject x + 2
        self.assertAlmostEqual(float(np.median(ui[wm][:, 0])), -2.0, delta=0.5)
        # the moved subject matches the reference far better than before (a translation needs no reorientation;
        # displacements along the ring tangent cost nothing, so the tensors are compared, not u)
        idx = np.stack(np.meshgrid(*[np.arange(n) for n in T.shape[:3]], indexing='ij'), 0).astype(float)
        moved = np.stack([ndimage.map_coordinates(Ls[..., i, j], idx + u.transpose(3, 0, 1, 2), order=1, mode='nearest')
                          for i in range(3) for j in range(3)], -1).reshape(T.shape)
        err = lambda L: float(np.linalg.norm((L - Lr)[wm], axis=(-1, -2)).mean())
        self.assertLess(err(moved), 0.3 * err(Ls))

    def test_reads_tensors_in_mm2_per_s_and_in_1e3_units(self):
        T = tensor_field((8, 8, 8))
        with tempfile.TemporaryDirectory() as d:
            for scale in (1e-3, 1.0):
                p = os.path.join(d, 't.nrrd')
                write_tensor_nrrd(p, T, scale)
                T2, grid = tr.read_tensor_nrrd(p)
                self.assertTrue(np.allclose(T2, T, atol=1e-4))
                self.assertEqual(grid.GetSize(), (8, 8, 8))


class TestFreeWaterMaps(unittest.TestCase):
    """DTI_Register TensorSVF finds the free water map of the DTI and the reference mean map (multi-shell), or
    registers the tensors only (single shell)."""

    def _module(self, protocol, d):
        obj = dti_register.DTI_Register.__new__(dti_register.DTI_Register)
        obj.protocol = protocol
        obj.global_variables = {}
        obj.result = {'output': {}}
        self.source = os.path.join(d, 'scan', 'sub-1_dwi_QCed_tensor.nrrd')
        self.ref = os.path.join(d, 'bin', 'DTI_mean.nrrd')
        for p in (self.source, self.ref):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w').close()
        return obj

    def touch(self, *parts):
        open(os.path.join(*parts), 'w').close()
        return os.path.join(*parts)

    def test_single_shell_registers_the_tensors_only(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._module({'freeWater': 'auto'}, d)
            self.touch(d, 'bin', 'FWF_mean.nii.gz')
            self.assertEqual(m.freeWaterMaps(self.source, self.ref), (None, None))

    def test_auto_prefers_the_fw_tensor_fraction(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._module({'freeWater': 'auto'}, d)
            fwf = self.touch(d, 'scan', 'sub-1_dwi_QCed_FWf.nii.gz')
            self.touch(d, 'scan', 'sub-1_dwi_QCed_NODDI_FWF.nii.gz')
            ref = self.touch(d, 'bin', 'FWF_mean.nii.gz')
            self.touch(d, 'bin', 'NODDI_FWF_mean.nii.gz')
            self.assertEqual(m.freeWaterMaps(self.source, self.ref), (fwf, ref))

    def test_auto_falls_back_to_noddi_without_a_reference_fwf_map(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._module({'freeWater': 'auto'}, d)
            self.touch(d, 'scan', 'sub-1_dwi_QCed_FWf.nii.gz')
            noddi = self.touch(d, 'scan', 'sub-1_dwi_QCed_NODDI_FWF.nii.gz')
            ref = self.touch(d, 'bin', 'NODDI_FWF_mean.nii.gz')
            self.assertEqual(m.freeWaterMaps(self.source, self.ref), (noddi, ref))

    def test_none_and_explicit_choices(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._module({'freeWater': 'none'}, d)
            self.touch(d, 'scan', 'sub-1_dwi_QCed_FWf.nii.gz')
            self.touch(d, 'bin', 'FWF_mean.nii.gz')
            self.assertEqual(m.freeWaterMaps(self.source, self.ref), (None, None))
            m.protocol = {'freeWater': 'NODDI_FWF'}
            with self.assertRaises(Exception):  # requested but missing
                m.freeWaterMaps(self.source, self.ref)
            m.protocol = {'freeWater': 'auto', 'freeWaterImage': os.path.join(d, 'missing.nii.gz')}
            with self.assertRaises(Exception):
                m.freeWaterMaps(self.source, self.ref)

    def test_iteration_lists(self):
        self.assertEqual(dti_register.DTI_Register.intList('200x150x100'), [200, 150, 100])
        self.assertEqual(dti_register.DTI_Register.intList('4, 2, 1'), [4, 2, 1])


if __name__ == '__main__':
    unittest.main()
