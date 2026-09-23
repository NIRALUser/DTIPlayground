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
