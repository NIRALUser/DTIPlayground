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
            qc_metrics.write_tsv(str(folder.joinpath('scan_IMAGE_QC.tsv')),
                                 [{'raw_volumes': 49, 'raw_ndc': 0.81, 'raw_bad_slices': 12, 'raw_coherence': 0.68,
                                   'qced_volumes': 47, 'qced_ndc': 0.86, 'qced_bad_slices': 3,
                                   'qced_bad_slices_percent': 0.09, 'qced_coherence': 0.71,
                                   'qced_coherence_best_flip': 'none'}])
            dataset = {'id': 'sub-1', 'output_dir': 'sub-1', 'output_file_base': 'scan', 'images': []}
            row, _ = batch_report.dataset_row(d, dataset, 'done', {})
        self.assertEqual(row['mean_fd'], '0.2')
        self.assertEqual(row['cnr_b1000'], '2.1')
        self.assertEqual(row['snr_b0'], '21.5')
        self.assertEqual(row['poor_fit_slices'], '2')
        self.assertEqual(row['raw_ndc'], '0.81')
        self.assertEqual(row['qced_ndc'], '0.86')
        self.assertEqual(row['qced_bad_slices'], '3')
        self.assertEqual(row['qced_coherence_best_flip'], 'none')
        self.assertEqual(row['noise_sigma'], '') # no DWI_Denoise
        self.assertNotIn('max_rel_translation', row)
        self.assertNotIn('raw_volumes', row) # not among the columns of the cohort table

    def _dataset(self, d):
        folder = Path(d).joinpath('sub-1')
        folder.joinpath('scan/02_SUSCEPTIBILITY_Correct').mkdir(parents=True)
        return folder, {'id': 'sub-1', 'output_dir': 'sub-1', 'output_file_base': 'scan', 'images': []}

    def test_shells_of_other_b_tables_share_the_column(self):
        with tempfile.TemporaryDirectory() as d:
            folder, dataset = self._dataset(d)
            qc_metrics.write_tsv(str(folder.joinpath('scan_EDDY_QC.tsv')),
                                 [{'snr_b0': 21.5, 'cnr_b499': 1.1, 'cnr_b1000': 1.2, 'cnr_b1501': 1.3, 'cnr_b2999': 1.4}])
            row, _ = batch_report.dataset_row(d, dataset, 'done', {})
        self.assertEqual((row['cnr_b500'], row['cnr_b1000'], row['cnr_b1500'], row['cnr_b3000']), ('1.1', '1.2', '1.3', '1.4'))
        self.assertNotIn('cnr_b499', row)

    def test_mask_volume_and_mean_fa_from_the_topup_mask_and_the_tensor(self):
        import nibabel as nib
        import nrrd
        with tempfile.TemporaryDirectory() as d:
            folder, dataset = self._dataset(d)
            mask = np.zeros((4, 5, 6), dtype=np.uint8)
            mask[1:3, 1:3, 1:3] = 1 # 8 voxels of 2 mm: 64 mm3
            nib.save(nib.Nifti1Image(mask, np.diag([2.0, 2.0, 2.0, 1.0])),
                     str(folder.joinpath('scan/02_SUSCEPTIBILITY_Correct/merged_image_mask_mask.nii.gz')))
            tensor = np.zeros((7,) + mask.shape, dtype=np.float32)
            tensor[0] = 1
            tensor[1], tensor[4], tensor[6] = 1.7e-3, 0.3e-3, 0.3e-3 # components xx, yy, zz
            tensor[1:, 0, 0, 0] = 1e-3 # far outside of the mask: not counted
            nrrd.write(str(folder.joinpath('scan_DTI.nrrd')), tensor,
                       {'kinds': ['3D-masked-symmetric-matrix', 'space', 'space', 'space']})
            row, _ = batch_report.dataset_row(d, dataset, 'done', {})
        expected = np.sqrt(0.5 * 2 * 1.4 ** 2 / (1.7 ** 2 + 2 * 0.3 ** 2))
        self.assertEqual(row['mask_ml'], 0.1)
        self.assertAlmostEqual(row['mean_fa'], expected, places=3)

    def test_stripped_volumes_are_not_excluded_volumes(self):
        import nibabel as nib
        with tempfile.TemporaryDirectory() as d:
            folder, dataset = self._dataset(d)
            folder.joinpath('scan/03_EDDYMOTION_Correct').mkdir()
            folder.joinpath('scan/03_EDDYMOTION_Correct/stripped_volumes.txt').write_text('8\n')
            images = []
            for name, volumes in (('ap', 8), ('pa', 20)):
                images.append(str(Path(d).joinpath(name + '.nii.gz')))
                nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, volumes), dtype=np.int16), np.eye(4)), images[-1])
            nib.save(nib.Nifti1Image(np.zeros((2, 2, 2, 18), dtype=np.int16), np.eye(4)), str(folder.joinpath('scan_QCed.nii.gz')))
            row, _ = batch_report.dataset_row(d, dict(dataset, images=images), 'done', {})
        self.assertEqual((row['input_volumes'], row['stripped_volumes'], row['excluded_volumes'], row['output_volumes']), (28, 8, 2, 18))

    def test_no_dti_leaves_the_columns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            folder, dataset = self._dataset(d)
            row, _ = batch_report.dataset_row(d, dataset, 'done', {})
        self.assertEqual((row['mask_ml'], row['mean_fa']), ('', ''))

    def test_a_low_correlation_and_many_bad_slices_are_marked(self):
        rows = [{'qced_ndc': 0.86 + 0.002 * i, 'qced_bad_slices': 3} for i in range(9)]
        rows.append({'qced_ndc': 0.42, 'qced_bad_slices': 61}) # the outlier of the cohort
        rows.append({'qced_ndc': 0.99, 'qced_bad_slices': 0}) # good on both sides: not marked
        marked = batch_report.mark_outliers(rows)
        self.assertIn((9, 'qced_ndc'), marked)
        self.assertIn((9, 'qced_bad_slices'), marked)
        self.assertNotIn((10, 'qced_ndc'), marked)
        self.assertNotIn((10, 'qced_bad_slices'), marked)


def _ring_dwi(bvals, bvecs, shape=(32, 32, 12), noise=1.0, seed=1):
    """A ring bundle in the xy plane (the fiber direction is tangent to the circle, so it curves in space) and its
    mask: a flipped b-vector axis points the directions across the ring, which lowers the coherence index."""
    import dipy.sims.voxel as sims
    from dipy.core.gradients import gradient_table
    rng = np.random.default_rng(seed)
    gtab = gradient_table(bvals, bvecs)
    data = np.zeros(shape + (len(bvals),))
    mask = np.zeros(shape, dtype=bool)
    center = np.array([(shape[0] - 1) / 2.0, (shape[1] - 1) / 2.0])
    for x in range(shape[0]):
        for y in range(shape[1]):
            if not 8 <= np.hypot(x - center[0], y - center[1]) <= 12:
                continue
            tangent = np.array([-(y - center[1]), x - center[0], 0.0])
            tangent /= np.linalg.norm(tangent)
            radial = np.array([x - center[0], y - center[1], 0.0])
            radial /= np.linalg.norm(radial)
            evecs = np.column_stack([tangent, radial, np.cross(tangent, radial)])
            signal = sims.single_tensor(gtab, S0=100.0, evals=np.array([1.7e-3, 0.3e-3, 0.3e-3]), evecs=evecs)
            data[x, y, 2:shape[2] - 2] = signal
            mask[x, y, 2:shape[2] - 2] = True
    return data + rng.normal(scale=noise, size=data.shape), mask


class TestNeighboringCorrelation(unittest.TestCase):
    def test_the_neighbor_is_the_closest_direction_of_the_shell(self):
        bvals = np.array([0.0, 0.0, 1000.0, 1000.0, 1000.0])
        bvecs = np.array([[0, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0], [-1, 0.02, 0]], dtype=float)
        bvecs[4] /= np.linalg.norm(bvecs[4])
        data = np.zeros((6, 6, 4, 5))
        rng = np.random.default_rng(3)
        for v in range(5):
            data[..., v] = rng.normal(100, 10, (6, 6, 4))
        mask = np.ones((6, 6, 4), dtype=bool)
        rows, summary = qc_metrics.neighboring_correlation(data, bvals, bvecs, mask)
        self.assertEqual(rows[0]['neighbor'], 1) # b=0: the closest one in acquisition order
        self.assertEqual(rows[2]['neighbor'], 4) # opposite directions measure the same signal
        self.assertEqual(rows[4]['neighbor'], 2)
        self.assertIn('ndc_b0', summary)
        self.assertIn('ndc_b1000', summary)

    def test_a_copied_volume_correlates_perfectly(self):
        bvals = np.array([0.0, 1000.0, 1000.0])
        bvecs = np.array([[0, 0, 0], [1, 0, 0], [0.999, 0.045, 0]], dtype=float)
        bvecs[2] /= np.linalg.norm(bvecs[2])
        rng = np.random.default_rng(4)
        volume = rng.normal(100, 10, (6, 6, 4))
        data = np.stack([rng.normal(200, 10, (6, 6, 4)), volume, volume], axis=-1)
        rows, _ = qc_metrics.neighboring_correlation(data, bvals, bvecs, np.ones((6, 6, 4), dtype=bool))
        self.assertAlmostEqual(rows[1]['ndc'], 1.0, places=4)

    def test_a_volume_alone_in_its_shell_has_no_neighbor(self):
        bvals = np.array([0.0, 1000.0, 3000.0])
        bvecs = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=float)
        rng = np.random.default_rng(5)
        data = rng.normal(100, 10, (6, 6, 4, 3))
        rows, summary = qc_metrics.neighboring_correlation(data, bvals, bvecs, np.ones((6, 6, 4), dtype=bool))
        self.assertEqual(rows[1]['neighbor'], '')
        self.assertIsNone(rows[1]['ndc'])
        self.assertIsNone(summary['ndc_b1000'])


class TestBadSlices(unittest.TestCase):
    def setUp(self):
        self.bvals, self.bvecs = _gradients(n_dirs=30, n_b0=3)
        self.data, self.mask = _ring_dwi(self.bvals, self.bvecs)

    def test_clean_data_has_almost_no_bad_slices(self):
        _, _, summary = qc_metrics.bad_slices(self.data, self.bvals, mask=self.mask)
        self.assertLess(summary['bad_slices_percent'], 1.0)

    def test_a_signal_dropout_is_found(self):
        """A dropout scales a slice down, which the normalized correlation doesn't see: the intensity criterion does."""
        data = self.data.copy()
        data[:, :, 4:7, 7] *= 0.3
        _, bad, summary = qc_metrics.bad_slices(data, self.bvals, mask=self.mask)
        self.assertEqual(sorted(np.nonzero(bad[:, 7])[0]), [4, 5, 6])
        self.assertGreaterEqual(summary['bad_slice_volumes'], 1)

    def test_a_corrupted_slice_is_found(self):
        rng = np.random.default_rng(7)
        data = self.data.copy()
        data[:, :, 5:7, 11] = rng.normal(50, 20, data[:, :, 5:7, 11].shape)
        _, bad, _ = qc_metrics.bad_slices(data, self.bvals, mask=self.mask)
        self.assertTrue(bad[5, 11] and bad[6, 11])

    def test_the_first_and_last_slices_are_skipped(self):
        slice_corr, _, _ = qc_metrics.bad_slices(self.data, self.bvals, mask=self.mask)
        self.assertTrue(np.isnan(slice_corr[0]).all())
        self.assertTrue(np.isnan(slice_corr[-1]).all())


class TestFiberCoherence(unittest.TestCase):
    def test_a_flipped_b_vector_axis_lowers_the_coherence_index(self):
        bvals, bvecs = _gradients(n_dirs=30, n_b0=3)
        data, mask = _ring_dwi(bvals, bvecs)
        spacing = np.array([2.0, 2.0, 2.0])
        given = qc_metrics.fiber_coherence(data, bvals, bvecs, mask, spacing=spacing)
        flipped = qc_metrics.fiber_coherence(data, bvals, bvecs * [1, -1, 1], mask, spacing=spacing)
        self.assertEqual(given['coherence_best_flip'], 'none')
        self.assertEqual(given['coherence'], given['coherence_best'])
        self.assertLess(flipped['coherence'], given['coherence'])
        self.assertAlmostEqual(flipped['coherence_best'], given['coherence'], places=4)
        self.assertNotEqual(flipped['coherence_best_flip'], 'none')

    def test_white_matter_is_needed(self):
        bvals, bvecs = _gradients(n_dirs=6, n_b0=1)
        data = np.full((6, 6, 4, 7), 100.0) # isotropic: no FA above the threshold
        qc = qc_metrics.fiber_coherence(data, bvals, bvecs, np.ones((6, 6, 4), dtype=bool))
        self.assertIsNone(qc['coherence'])


class TestVoxelSpacing(unittest.TestCase):
    def test_the_gradient_axis_is_left_out(self):
        """In the pipeline the information of a DWI has one space direction per axis of the stored image, and the row
        of the gradient axis is NaN (NRRD headers write None there)."""
        self.assertIsNone(np.testing.assert_allclose(
            qc_metrics.voxel_spacing({'space_directions': [[2., 0, 0], [0, -2., 0], [0, 0, 2.], [np.nan] * 3]}),
            [2., 2., 2.]))
        self.assertIsNone(np.testing.assert_allclose(
            qc_metrics.voxel_spacing({'space_directions': [[2., 0, 0], [0, -2., 0], [0, 0, 2.], None]}),
            [2., 2., 2.]))

    def test_anisotropic_and_missing(self):
        self.assertIsNone(np.testing.assert_allclose(
            qc_metrics.voxel_spacing({'space_directions': [[1.5, 0, 0], [0, 1.5, 0], [0, 0, 3.]]}), [1.5, 1.5, 3.]))
        self.assertIsNone(qc_metrics.voxel_spacing({}))
        self.assertIsNone(qc_metrics.voxel_spacing({'space_directions': [[1., 0, 0], [0, 1., 0]]}))

    def test_an_unusable_spacing_falls_back_to_isotropic(self):
        """fiber_coherence must not fail on a spacing that isn't three positive numbers."""
        bvals, bvecs = _gradients(n_dirs=30, n_b0=3)
        data, mask = _ring_dwi(bvals, bvecs)
        good = qc_metrics.fiber_coherence(data, bvals, bvecs, mask, spacing=np.array([1.0, 1.0, 1.0]))
        for spacing in (None, np.array([2.0, 2.0, 2.0, np.nan]), np.array([0.0, 1.0, 1.0])):
            self.assertEqual(qc_metrics.fiber_coherence(data, bvals, bvecs, mask, spacing=spacing), good)


class TestImageQC(unittest.TestCase):
    def test_summary_and_rows(self):
        bvals, bvecs = _gradients(n_dirs=30, n_b0=3)
        data, mask = _ring_dwi(bvals, bvecs)
        rows, summary = qc_metrics.image_qc(data, bvals, bvecs, mask, spacing=np.array([2.0, 2.0, 2.0]))
        self.assertEqual(len(rows), len(bvals))
        self.assertEqual(summary['volumes'], len(bvals))
        for key in ('ndc', 'ndc_b0', 'ndc_b1000', 'bad_slices', 'bad_slices_percent', 'coherence',
                    'coherence_best', 'coherence_best_flip'):
            self.assertIn(key, summary)
        self.assertIn('bad_slices', rows[0])

    def test_the_coherence_index_can_be_left_out(self):
        bvals, bvecs = _gradients(n_dirs=6, n_b0=1)
        rng = np.random.default_rng(8)
        data = rng.normal(100, 10, (8, 8, 6, 7))
        _, summary = qc_metrics.image_qc(data, bvals, bvecs, np.ones((8, 8, 6), dtype=bool), coherence=False)
        self.assertNotIn('coherence', summary)


class TestBaselinesOfTopup(unittest.TestCase):
    """A series that lost all its baselines must not get its lowest shell labeled b=0."""

    def _create_b0s(self, d, *lowest_b_values):
        from dtiplayground.dmri.preprocessing.modules.SUSCEPTIBILITY_Correct import SUSCEPTIBILITY_Correct as module
        class Image:
            def __init__(self, minb):
                self.filename, self.minb, self.thresholds = 'series.nrrd', minb, []
            def getBValueBounds(self):
                return [self.minb, 3000.0]
            def setB0Threshold(self, value):
                self.thresholds.append(value)
            def extractBaselines(self, threshold):
                self.thresholds.append(threshold)
                return self
            def writeImage(self, *a, **k):
                pass
            def getGradients(self):
                return [{'original_index': 0}]
        obj = module.SUSCEPTIBILITY_Correct.__new__(module.SUSCEPTIBILITY_Correct)
        obj.output_dir = d
        return obj.create_b0s([Image(b) for b in lowest_b_values], 13.0)[3]

    def test_a_series_without_baselines_stops_the_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'no baseline'):
                self._create_b0s(d, 0.0, 500.0)

    def test_baselines_of_b50_raise_the_threshold(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._create_b0s(d, 0.0, 50.0), 50.0)

    def test_the_threshold_stays_with_b0s(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._create_b0s(d, 5.0, 0.0), 13.0)


class TestSliceCheckKeepsOneBaseline(unittest.TestCase):
    def _keep(self, arte, grads):
        from dtiplayground.dmri.preprocessing.modules.SLICE_Check import SLICE_Check as module
        module.logger = lambda *a, **k: None
        obj = module.SLICE_Check.__new__(module.SLICE_Check)
        kept, keep = obj.keepOneBaseline(arte, grads)
        return [a[0] for a in kept], keep

    def test_the_least_abnormal_baseline_is_kept(self):
        grads = [{'baseline': True}, {'baseline': True}, {'baseline': False}]
        arte = [(0, [1, 2, 3]), (1, [1]), (2, [1, 2])]
        self.assertEqual(self._keep(arte, grads), ([0, 2], 1))

    def test_other_baselines_left_nothing_changes(self):
        grads = [{'baseline': True}, {'baseline': True}, {'baseline': False}]
        self.assertEqual(self._keep([(0, [1])], grads), ([0], None))

    def test_a_series_without_baselines_nothing_changes(self):
        self.assertEqual(self._keep([(0, [1])], [{'baseline': False}]), ([0], None))


class TestMoveToFirstVolume(unittest.TestCase):
    def test_volume_and_gradient_move_together(self):
        import nibabel as nib
        from dtiplayground.dmri.common.dwi import DWI
        with tempfile.TemporaryDirectory() as d:
            base = Path(d).joinpath('dwi')
            data = np.arange(1, 6, dtype=np.int16)[None, None, None, :] * np.ones((4, 4, 4, 5), dtype=np.int16)
            nib.save(nib.Nifti1Image(data, np.eye(4)), str(base) + '.nii.gz')
            base.with_suffix('.bval').write_text('1000 1000 0 1000 1000\n')
            base.with_suffix('.bvec').write_text('1 0 0 0 1\n0 1 0 0 0\n0 0 0 1 0\n')
            image = DWI(str(base) + '.nii.gz')
            image.setB0Threshold(10)
            image.deleteGradientsByOriginalIndex([0])
            image.moveToFirstVolumeByOriginalIndex(2)
            gradients = image.getGradients()
            self.assertEqual([g['original_index'] for g in gradients], [2, 1, 3, 4])
            self.assertEqual([g['index'] for g in gradients], [0, 1, 2, 3])
            self.assertTrue(gradients[0]['baseline'])
            self.assertEqual(image.images[0, 0, 0].tolist(), [3, 2, 4, 5])
            image.deleteGradientsByOriginalIndex([3]) # later exclusions find the right volumes
            self.assertEqual(image.images[0, 0, 0].tolist(), [3, 2, 5])


class TestBaselineOnlySeries(unittest.TestCase):
    def setUp(self):
        from dtiplayground.dmri.preprocessing.modules.SUSCEPTIBILITY_Correct import SUSCEPTIBILITY_Correct as module
        self.module = module

    def test_which_series_is_stripped(self):
        only = self.module.baseline_only_series
        self.assertEqual(only([(7, 8), (7, 151)]), [0]) # the dummy volume of the short scan (BEE)
        self.assertEqual(only([(1, 2), (7, 151)]), [0]) # most of its baselines were excluded
        self.assertEqual(only([(5, 7), (7, 151)]), []) # two volumes that aren't baselines
        self.assertEqual(only([(7, 151), (7, 7)]), [1])
        self.assertEqual(only([(7, 151), (7, 151)]), []) # two full DWIs
        self.assertEqual(only([(7, 7), (6, 6)]), []) # nothing would be left

    def test_every_volume_has_the_phase_encoding_of_its_series(self):
        rows = self.module.acqp_rows
        self.assertEqual(rows([3, 4], [0, 1, 3, 5]), [1, 2, 2, 3, 3, 4, 4])
        # sub-1266: the second series has no baseline before its volume 24
        result = rows([8, 151], [0, 1, 2, 3, 4, 5, 6, 32, 103])
        self.assertEqual(result[:8], [1, 2, 3, 4, 5, 6, 7, 7])
        self.assertEqual(set(result[8:33]), {8})
        self.assertEqual((result[102], result[103]), (8, 9))

    def test_the_result_starts_with_a_baseline(self):
        self.assertEqual(self.module.stripped_order([3, 4], [0], [0, 5]), [5, 3, 4, 6])

    def test_eddy_strips_with_the_original_indexes(self):
        from dtiplayground.dmri.preprocessing.modules.EDDYMOTION_Correct import EDDYMOTION_Correct as eddy
        eddy.logger = lambda *a, **k: None
        class Image:
            def keepVolumes(self, positions):
                self.positions = positions
        with tempfile.TemporaryDirectory() as d:
            obj = eddy.EDDYMOTION_Correct.__new__(eddy.EDDYMOTION_Correct)
            obj.image, obj.output_dir, obj.result = Image(), d, {'output': {}}
            obj.stripBaselineOnlyImage([5, 3, 6], [0, 1, 3, 5, 6]) # volume 2 was excluded before
            count = Path(d).joinpath('stripped_volumes.txt').read_text()
        self.assertEqual(obj.image.positions, [3, 2, 4])
        self.assertEqual(obj.result['output']['stripped_gradients'], [0, 1])
        self.assertEqual(obj.result['output']['eddy_volumes'], [0, 1, 3, 5, 6])
        self.assertEqual(count, '2\n')


class TestQCReportOfTwoImages(unittest.TestCase):
    def _module(self, image_name, reports=None):
        from dtiplayground.dmri.preprocessing.modules.QC_Report import QC_Report as module
        module.logger = lambda *a, **k: None
        obj = module.QC_Report.__new__(module.QC_Report)
        obj.result_history = [None, {'module_name': 'SUSCEPTIBILITY_Correct',
                                     'report': {'csv_data': {'image_name': image_name}, 'module_report_paths': reports}}]
        return obj

    def test_each_exclusion_is_shown_on_its_image(self):
        obj = self._module([['ap.nii.gz', 'pa.nii.gz'], 'merged.nrrd'])
        shown = []
        obj.CreateImagesOfExcludedGradients = lambda path, gradients, index: shown.append((path, gradients)) or ['x'] * len(gradients)
        obj.AddExcludedGradientsImagesToReport('', [[2], [30, 31], [40]])
        self.assertEqual(shown, [('ap.nii.gz', [2]), ('pa.nii.gz', [30, 31]), ('merged.nrrd', [40])])

    def test_the_same_volume_excluded_from_both_images_keeps_two_pictures(self):
        import nibabel as nib
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, value in (('ap', 100), ('pa', 1000)):
                paths.append(str(Path(d).joinpath(name + '.nii.gz')))
                nib.save(nib.Nifti1Image(np.full((8, 8, 8, 3), value, dtype=np.int16), np.eye(4)), paths[-1])
                Path(d).joinpath(name + '.bval').write_text('0 1000 1000\n')
                Path(d).joinpath(name + '.bvec').write_text('0 1 0\n0 0 1\n0 0 0\n')
            obj = self._module([paths, 'merged.nrrd'])
            obj.GetOutputImagesDirectory = lambda: d
            report = obj.AddExcludedGradientsImagesToReport('', [[1], [1], []])
            pictures = sorted(p.name for p in Path(d).glob('excluded*.jpg'))
        self.assertEqual(pictures, ['excluded_image0_dwi1.jpg', 'excluded_image1_dwi1.jpg'])
        self.assertTrue(all(name in report for name in pictures))

    def test_the_reports_of_the_modules_of_each_image_are_merged(self):
        with tempfile.TemporaryDirectory() as d:
            reports = []
            for name in ('slice1.md', 'slice2.md', 'own.md'):
                reports.append(str(Path(d).joinpath(name)))
                Path(reports[-1]).write_text(name + '\n')
            obj = self._module(None, [reports[:2], reports[2]])
            merged = obj.MergeReports('')
            self.assertTrue(all(name in merged for name in ('slice1.md', 'slice2.md', 'own.md')))

    def test_input_images_stored_by_an_older_version_are_left_out(self):
        with tempfile.TemporaryDirectory() as d:
            own = Path(d).joinpath('own.md')
            own.write_text('own\n')
            gz = Path(d).joinpath('ap.nii.gz')
            gz.write_bytes(b'\x1f\x8b')
            self.assertIn('own', self._module(None, [[str(gz)], str(own)]).MergeReports(''))


class TestQCReportReuse(unittest.TestCase):
    def _reusable(self, protocol, files):
        from dtiplayground.dmri.preprocessing.modules.QC_Report import QC_Report as module
        with tempfile.TemporaryDirectory() as d:
            for name in files:
                Path(d).joinpath(name).touch()
            obj = module.QC_Report.__new__(module.QC_Report)
            obj.protocol, obj.output_dir = protocol, d
            return obj.reusableResult()

    def test_a_result_without_image_qc_is_computed_again(self):
        self.assertFalse(self._reusable({'imageQC': True}, []))
        self.assertTrue(self._reusable({'imageQC': True}, ['image_qc.tsv']))
        self.assertTrue(self._reusable({'imageQC': False}, []))


class TestStatusOfTheReport(unittest.TestCase):
    def test_the_report_refreshes_status_tsv(self):
        from dtiplayground.dmri.preprocessing import batch
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            bdir = batch.batch_dir(out)
            bdir.mkdir(parents=True, exist_ok=True)
            calls = []
            originals = batch.summarize, batch.load_manifest
            batch.summarize, batch.load_manifest = lambda o: calls.append(o), lambda o: []
            try:
                batch_report.write_report(out, echo=lambda m: None)
            finally:
                batch.summarize, batch.load_manifest = originals
        self.assertEqual(calls, [out])


class TestManualExcludeIndexes(unittest.TestCase):
    """The indexes of MANUAL_Exclude are the original ones, so they stop matching the positions in the image as soon
    as an earlier module excluded a volume; the mapping and the missing ones are logged."""

    def _log(self, gradients_present, to_exclude):
        from dtiplayground.dmri.preprocessing.modules.MANUAL_Exclude import MANUAL_Exclude as module
        messages = []
        module.logger = lambda message, *a, **k: messages.append(message)
        obj = module.MANUAL_Exclude.__new__(module.MANUAL_Exclude)
        obj.image = type('Image', (), {'getGradients': lambda s: [{'original_index': i} for i in gradients_present]})()
        obj.logGradientsToExclude(to_exclude)
        return messages

    def test_the_position_in_the_image_is_logged_with_a_warning(self):
        messages = self._log([0, 1, 3, 4, 5], [4]) # original 2 was excluded before: 4 is the 3rd volume now
        self.assertTrue(any('original gradient 4' in m and 'volume 3 of 5' in m for m in messages), messages)
        self.assertTrue(any('not the positions in this image' in m for m in messages), messages)

    def test_no_warning_when_nothing_was_excluded_before(self):
        messages = self._log([0, 1, 2, 3], [2])
        self.assertTrue(any('volume 2 of 4' in m for m in messages), messages)
        self.assertFalse(any('not the positions in this image' in m for m in messages), messages)

    def test_an_index_that_is_gone_is_reported(self):
        messages = self._log([0, 1, 3], [2, 9])
        self.assertTrue(any('2, 9' in m and 'nothing is excluded' in m for m in messages), messages)


class TestDenoisePatch(unittest.TestCase):
    def test_auto_patch_radius(self):
        from dtiplayground.dmri.preprocessing.modules.DWI_Denoise.DWI_Denoise import auto_patch_radius
        self.assertEqual(auto_patch_radius(20), 1) # 27 voxels
        self.assertEqual(auto_patch_radius(27), 1)
        self.assertEqual(auto_patch_radius(44), 2) # 125 voxels
        self.assertEqual(auto_patch_radius(288), 3) # 343 voxels


if __name__ == '__main__':
    unittest.main()
