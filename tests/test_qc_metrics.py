import tempfile
import unittest
from pathlib import Path

import numpy as np

from dtiplayground.dmri.preprocessing import qc_metrics, batch_report


def _gradients(n_dirs=30, n_b0=5, bval=1000.0, seed=0):
    rng = np.random.default_rng(seed)
    dirs = rng.normal(size=(n_dirs, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    bvecs = np.vstack([np.zeros((n_b0, 3)), dirs])
    bvals = np.concatenate([np.zeros(n_b0), np.full(n_dirs, bval)])
    return bvals, bvecs


def _dwi(bvals, bvecs, shape=(24, 24, 12), noise=5.0, seed=1):
    """Tensor field with random orientations (FA ~0.6) and S0 between 600 and 1400, plus Gaussian noise."""
    rng = np.random.default_rng(seed)
    evals = np.array([1.7e-3, 0.4e-3, 0.3e-3])
    data = np.zeros(shape + (len(bvals),))
    for idx in np.ndindex(shape):
        q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        d = q @ np.diag(evals) @ q.T
        data[idx] = rng.uniform(600, 1400) * np.exp(-bvals * np.einsum('vi,ij,vj->v', bvecs, d, bvecs))
    return data + rng.normal(scale=noise, size=data.shape)


class TestEddyMotion(unittest.TestCase):
    def test_framewise_displacement_and_outliers(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).joinpath('output_eddied')
            par = np.zeros((3, 16))
            par[1, 0] = 1.0 # 1 mm along x
            par[2, 0] = 1.0
            par[2, 5] = 0.01 # 0.01 rad about z
            np.savetxt(str(base) + '.eddy_parameters', par)
            np.savetxt(str(base) + '.eddy_movement_rms', np.array([[0, 0], [1, 1], [1.2, 0.5]]))
            Path(str(base) + '.eddy_outlier_map').write_text(
                'One row per scan, one column per slice. Outlier: 1, Non-outlier: 0\n0 0 0 0\n0 1 0 0\n0 1 1 0\n')
            rows, qc = qc_metrics.eddy_motion(base, [0, 1000, 1000], original_indexes=[0, 2, 5])
        self.assertEqual([r['framewise_displacement'] for r in rows], [0.0, 1.0, 0.5])
        self.assertEqual([r['original_index'] for r in rows], [0, 2, 5])
        self.assertEqual([r['outlier_slices'] for r in rows], [0, 1, 2])
        self.assertAlmostEqual(qc['mean_fd'], 0.75)
        self.assertEqual(qc['max_fd'], 1.0)
        self.assertEqual(qc['max_translation'], 1.0)
        self.assertAlmostEqual(qc['max_rotation'], np.degrees(0.01), places=3)
        self.assertEqual(qc['outlier_slices'], 3)
        self.assertEqual(qc['outlier_slices_percent'], 25.0)

    def test_missing_parameters(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(qc_metrics.eddy_motion(Path(d).joinpath('x'), [0]), (None, None))

    def test_cnr_names_follow_the_shells(self):
        import nibabel as nib
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).joinpath('output_eddied')
            maps = np.zeros((4, 4, 2, 3))
            maps[..., 0], maps[..., 1], maps[..., 2] = 20.0, 3.0, 1.5
            nib.save(nib.Nifti1Image(maps, np.eye(4)), str(base) + '.eddy_cnr_maps.nii.gz')
            cnr = qc_metrics.eddy_cnr(base, [0, 995, 1005, 2000, 1990], b_range=50)
            self.assertEqual(cnr, {'snr_b0': 20.0, 'cnr_b1000': 3.0, 'cnr_b1995': 1.5})
            ## a different number of maps than shells: generic names
            self.assertEqual(sorted(qc_metrics.eddy_cnr(base, [0, 1000])), ['cnr_map0', 'cnr_map1', 'cnr_map2'])


class TestTensorFit(unittest.TestCase):
    def test_good_fit_and_dropout_slice(self):
        bvals, bvecs = _gradients()
        data = _dwi(bvals, bvecs)
        data[:, :, 6, 20] *= 0.4 # signal dropout of one slice of one volume
        mask = np.ones(data.shape[:3], dtype=bool)
        rows, qc, slice_r2, poor = qc_metrics.tensor_fit(data, bvals, bvecs, mask, min_slice_voxels=50)
        self.assertEqual(slice_r2.shape, (12, len(bvals)))
        ## the dropout volume, and possibly other volumes of that slice whose fit it pulled
        flagged = list(zip(*np.nonzero(poor)))
        self.assertIn((6, 20), flagged)
        self.assertEqual({k for k, _ in flagged}, {6})
        self.assertEqual(np.unravel_index(np.nanargmin(slice_r2), slice_r2.shape), (6, 20))
        self.assertEqual(qc['poor_fit_slices'], len(flagged))
        self.assertEqual(rows[20]['poor_fit_slices'], 1)
        self.assertGreater(qc['fit_r2_mean'], 0.9)
        self.assertEqual(qc['fit_r2_min'], min(r['fit_r2'] for r in rows))
        self.assertLess(rows[20]['fit_r2'], rows[21]['fit_r2'])

    def test_zero_voxels_are_left_out(self):
        bvals, bvecs = _gradients(n_dirs=12, n_b0=2)
        data = _dwi(bvals, bvecs, shape=(10, 10, 4))
        clean = qc_metrics.tensor_fit(data, bvals, bvecs, np.ones((10, 10, 4)), min_slice_voxels=10)[1]
        data[:5, :, :, 7] = 0 # thresholded at 0, e.g. after eddy
        rows, qc, _, _ = qc_metrics.tensor_fit(data, bvals, bvecs, np.ones((10, 10, 4)), min_slice_voxels=10)
        self.assertEqual(qc['fit_excluded_voxels_percent'], 50.0)
        self.assertAlmostEqual(qc['fit_r2_mean'], clean['fit_r2_mean'], delta=0.02)
        self.assertEqual(clean['fit_excluded_voxels_percent'], 0.0)

    def test_chunks_give_the_same_result(self):
        bvals, bvecs = _gradients(n_dirs=12, n_b0=2)
        data = _dwi(bvals, bvecs, shape=(10, 10, 4))
        mask = np.ones(data.shape[:3], dtype=bool)
        a = qc_metrics.tensor_fit(data, bvals, bvecs, mask, min_slice_voxels=10)
        b = qc_metrics.tensor_fit(data, bvals, bvecs, mask, min_slice_voxels=10, chunk=37)
        np.testing.assert_allclose(a[2], b[2], rtol=1e-9)
        self.assertEqual(a[1], b[1])

    def test_carpet_plot(self):
        bvals, bvecs = _gradients(n_dirs=12, n_b0=2)
        data = _dwi(bvals, bvecs, shape=(10, 10, 4))
        rows, qc, slice_r2, poor = qc_metrics.tensor_fit(data, bvals, bvecs, np.ones((10, 10, 4)), min_slice_voxels=10)
        with tempfile.TemporaryDirectory() as d:
            path = qc_metrics.carpet_plot(str(Path(d).joinpath('c.png')), slice_r2, poor, bvals, [r['fit_r2'] for r in rows])
            self.assertGreater(Path(path).stat().st_size, 1000)


class TestShells(unittest.TestCase):
    def test_shells(self):
        self.assertEqual(qc_metrics.shells([0, 5, 990, 1000, 1010, 2000, 2020]), [1000, 2010])
        self.assertEqual(qc_metrics.shell_of([0, 995, 2019], [1000, 2010]), [0, 1000, 2010])


class TestOutlierDirection(unittest.TestCase):
    def test_one_sided_columns(self):
        rows = [{'mean_fd': v, 'fit_r2_mean': r} for v, r in
                [(0.3, 0.95), (0.31, 0.96), (0.29, 0.95), (0.3, 0.94), (0.32, 0.95), (2.0, 0.60), (0.01, 0.999)]]
        marked = batch_report.mark_outliers(rows, {'mean_fd': 1, 'fit_r2_mean': -1})
        self.assertEqual(marked, {(5, 'mean_fd'), (5, 'fit_r2_mean')})
        both = batch_report.mark_outliers(rows, ['mean_fd'])
        self.assertEqual(both, {(5, 'mean_fd'), (6, 'mean_fd')})


class TestBatchReportColumns(unittest.TestCase):
    def test_summaries_become_columns(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d).joinpath('sub-1')
            folder.mkdir()
            qc_metrics.write_tsv(str(folder.joinpath('scan_EDDY_QC.tsv')),
                                 [{'mean_fd': 0.2, 'max_fd': 1.1, 'max_translation': 0.5, 'max_rotation': 0.3,
                                   'max_rel_translation': 0.4, 'max_rel_rotation': 0.2, 'outlier_slices': 3,
                                   'outlier_slices_percent': 0.1, 'snr_b0': 21.5, 'cnr_b1000': 2.1}])
            qc_metrics.write_tsv(str(folder.joinpath('scan_DTI_fit_QC.tsv')),
                                 [{'fit_r2_mean': 0.97, 'fit_r2_min': 0.9, 'fit_corr_mean': 0.98, 'fit_corr_min': 0.95,
                                   'poor_fit_slices': 2}])
            dataset = {'id': 'sub-1', 'output_dir': 'sub-1', 'output_file_base': 'scan', 'images': []}
            row, _ = batch_report.dataset_row(d, dataset, 'done', {})
        self.assertEqual(row['mean_fd'], '0.2')
        self.assertEqual(row['cnr_b1000'], '2.1')
        self.assertEqual(row['snr_b0'], '21.5')
        self.assertEqual(row['poor_fit_slices'], '2')
        self.assertEqual(row['noise_sigma'], '') # no DWI_Denoise
        self.assertNotIn('max_rel_translation', row)


class TestDenoisePatch(unittest.TestCase):
    def test_auto_patch_radius(self):
        from dtiplayground.dmri.preprocessing.modules.DWI_Denoise.DWI_Denoise import auto_patch_radius
        self.assertEqual(auto_patch_radius(20), 1) # 27 voxels
        self.assertEqual(auto_patch_radius(27), 1)
        self.assertEqual(auto_patch_radius(44), 2) # 125 voxels
        self.assertEqual(auto_patch_radius(288), 3) # 343 voxels


if __name__ == '__main__':
    unittest.main()
