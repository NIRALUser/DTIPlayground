#   Tests of dmrifiberprofile impute-profiles (synthetic tracts, axes and profiles):
#       python -m unittest discover -s tests

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from dtiplayground.dmri.fiberprofile.analysis import fiber_axis
from dtiplayground.dmri.fiberprofile.analysis import impute_profiles as ip

ARCS = np.arange(-20.0, 21.0, 1.0)
# parallel tracts along x, 3 mm apart in y, and one along y crossing them
TRACTS = {'T_a': (0.0, 0.0), 'T_b': (3.0, 0.0), 'T_c': (6.0, 0.0), 'T_d': (9.0, 0.0)}
SCANS = ['sub-0{}_ses-1_dwi'.format(i) for i in range(1, 7)]


def points_of(tract, arcs=ARCS):
    if tract == 'T_x':
        return np.column_stack([np.zeros_like(arcs), 4.5 + arcs / 4.0, np.full_like(arcs, 1.0)])
    y, z = TRACTS[tract]
    return np.column_stack([arcs, np.full_like(arcs, y), np.full_like(arcs, z)])


def field(metric, pts, s):
    """Values linear in the 3-D position, with a level per scan: linear interpolation is exact."""
    x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
    if metric == 'fa':
        return 0.4 + 0.004 * x + 0.01 * y + 0.002 * z + 0.01 * s
    return 0.001 * (1.0 + 0.01 * x - 0.02 * y + 0.01 * s)


def make_dataset(root, rowwise=False, tracts=('T_a', 'T_b', 'T_c', 'T_d', 'T_x'), metrics=('fa', 'md'), scans=None,
                 value=None):
    """Gathered tables (<tract>/<tract>_<metric>.csv) or, *rowwise*, EXTRACT_Profile tables with one row per scan
    (<metric>/<tract>_<metric>.csv), and the tract axes."""
    root = Path(root)
    prof, axes = root / 'Profiles', root / 'FiberAxis'
    axes.mkdir(parents=True)
    for tract in tracts:
        fiber_axis.write_polydata(fiber_axis.build_axis_polydata(points_of(tract), ARCS), axes / '{}_axis.vtk'.format(tract))
        for metric in metrics:
            values = {scan: (value or field)(metric, points_of(tract), s) if value is None else value(metric, tract, s)
                      for s, scan in enumerate(scans or SCANS)}
            df = pd.DataFrame(values, index=pd.Index(ARCS, name='Arc_Length'))
            if rowwise:
                path = prof / metric / '{}_{}.csv'.format(tract, metric)
                df = df.T
                df.index.name = 'case_id'
                df.columns = ['{:g}'.format(a) for a in ARCS]
            else:
                path = prof / tract / '{}_{}.csv'.format(tract, metric)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, float_format='%.6g')
    return prof, axes


def blank(path, scan, arcs, rowwise=False):
    df = pd.read_csv(path, index_col=0, dtype=str, keep_default_na=False)
    for a in arcs:
        if rowwise:
            df.loc[scan, '{:g}'.format(a)] = ''
        else:
            df.loc[df.index.astype(float) == a, scan] = ''
    df.to_csv(path)


def drop(path, scan, rowwise=False):
    df = pd.read_csv(path, index_col=0, dtype=str, keep_default_na=False)
    df = df.drop(index=scan) if rowwise else df.drop(columns=scan)
    df.to_csv(path)


def args_for(prof, axes, out, **kw):
    parser = argparse.ArgumentParser()
    ip.add_parser(parser.add_subparsers())
    argv = ['impute-profiles', '--profiles-dir', str(prof), '--out-dir', str(out)]
    if axes is not None:
        argv += ['--axis-dir', str(axes)]
    for k, v in kw.items():
        flag = '--' + k.replace('_', '-')
        argv += [flag] if v is True else [flag, str(v)]
    return parser.parse_args(argv)


class TestCohort(unittest.TestCase):

    def test_missing_cells_and_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = make_dataset(tmp)
            blank(prof / 'T_a' / 'T_a_fa.csv', SCANS[0], [-2, -1, 0])
            for m in ('fa', 'md'):
                drop(prof / 'T_b' / 'T_b_{}.csv'.format(m), SCANS[1])
            cohort = ip.Cohort(ip.read_tables(str(prof)), ip.read_axes(str(axes), ['T_a', 'T_b', 'T_c', 'T_d', 'T_x']))
            self.assertEqual(cohort.scans, SCANS)
            self.assertEqual(cohort.metrics, ['fa', 'md'])
            self.assertEqual(cohort.n_positions, 5 * len(ARCS))
            miss = np.isnan(cohort.values) & cohort.valid[None]
            self.assertEqual(int(miss[0].sum()), 3)
            self.assertEqual(int(miss[1].sum()), 2 * len(ARCS))  # whole T_b profile, both metrics
            sl = cohort.slices['T_x']
            self.assertTrue(np.allclose(cohort.points[sl], points_of('T_x')))

    def test_axis_positions_beyond_the_ends(self):
        pts = ip.axis_positions(np.array([-3.0, 0.0, 12.0]), np.array([[0, 0, 0], [10, 0, 0]], float), np.array([0.0, 10.0]))
        self.assertTrue(np.allclose(pts[:, 0], [-3, 0, 12]))


class TestMethods(unittest.TestCase):

    def run_method(self, tmp, method, rowwise=False, **kw):
        prof, axes = make_dataset(tmp, rowwise=rowwise)
        a = prof / ('fa/T_a_fa.csv' if rowwise else 'T_a/T_a_fa.csv')
        blank(a, SCANS[0], [-2, -1, 0, 1], rowwise)
        for m in ('fa', 'md'):
            drop(prof / ('{0}/T_b_{0}.csv'.format(m) if rowwise else 'T_b/T_b_{}.csv'.format(m)), SCANS[1], rowwise)
        out = Path(tmp) / 'Profiles_Imputed'
        self.assertEqual(ip.run(args_for(prof, axes, out, method=method, **kw)), 0)
        return prof, out

    def check_gap(self, out, tol):
        df = pd.read_csv(out / 'T_a' / 'T_a_fa.csv', index_col=0)
        truth = field('fa', points_of('T_a'), 0)
        self.assertLess(np.max(np.abs(df[SCANS[0]].to_numpy() - truth)), tol)

    def check_whole(self, out, tol):
        for m in ('fa', 'md'):
            df = pd.read_csv(out / 'T_b' / 'T_b_{}.csv'.format(m), index_col=0)
            self.assertIn(SCANS[1], df.columns)
            truth = field(m, points_of('T_b'), 1)
            self.assertLess(np.max(np.abs(df[SCANS[1]].to_numpy() - truth) / np.abs(truth)), tol)

    def test_arc_linear_fills_gaps_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = self.run_method(tmp, 'arc-linear')
            self.check_gap(out, 1e-5)
            self.assertNotIn(SCANS[1], pd.read_csv(out / 'T_b' / 'T_b_fa.csv', index_col=0).columns)
            summary = pd.read_csv(Path(str(out) + '_report') / 'imputation_summary.csv')
            whole = summary[summary['shape'] == ip.WHOLE]
            self.assertEqual(len(whole), 2)
            self.assertTrue((whole['n_left'] == len(ARCS)).all())

    def test_linear_is_exact_for_a_linear_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = self.run_method(tmp, 'linear')
            self.check_gap(out, 1e-4)
            self.check_whole(out, 1e-3)

    def test_arc_linear_ends(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = make_dataset(tmp)
            blank(prof / 'T_c' / 'T_c_fa.csv', SCANS[2], [-20, -19, -18])
            blank(prof / 'T_c' / 'T_c_fa.csv', SCANS[3], [19, 20])
            truth = field('fa', points_of('T_c'), 2)
            for ends, tol in (('linear', 1e-4), ('constant', 0.02)):
                out = Path(tmp) / ends
                ip.run(args_for(prof, axes, out, method='arc-linear', arc_ends=ends))
                df = pd.read_csv(out / 'T_c' / 'T_c_fa.csv', index_col=0)
                self.assertTrue(df[SCANS[2]].notna().all() and df[SCANS[3]].notna().all())
                self.assertLess(np.max(np.abs(df[SCANS[2]].to_numpy() - truth)), tol)
            summary = pd.read_csv(Path(tmp) / 'linear_report' / 'imputation_summary.csv')
            self.assertEqual(set(summary['shape']), {ip.END})

    def test_knn(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = self.run_method(tmp, 'knn', k=2)
            self.check_gap(out, 0.02)
            self.check_whole(out, 0.05)

    def test_max_distance(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = self.run_method(tmp, 'knn', max_distance=2)
            # T_b is 3 mm from T_a and T_c; T_x passes 1 mm above it at x = 0: only x = -1, 0, 1 are within 2 mm
            df = pd.read_csv(out / 'T_b' / 'T_b_fa.csv', index_col=0)
            self.assertEqual(df.index[df[SCANS[1]].notna()].tolist(), [-1.0, 0.0, 1.0])
            self.check_gap(out, 0.02)

    def test_observed_cells_verbatim_and_masks(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, out = self.run_method(tmp, 'linear')
            src = pd.read_csv(prof / 'T_c' / 'T_c_fa.csv', dtype=str)
            dst = pd.read_csv(out / 'T_c' / 'T_c_fa.csv', dtype=str)
            pd.testing.assert_frame_equal(src, dst)
            mask = pd.read_csv(Path(str(out) + '_report') / 'masks' / 'T_a' / 'T_a_fa.csv', index_col=0)
            self.assertEqual(int(mask[SCANS[0]].sum()), 4)
            self.assertEqual(int(mask.drop(columns=SCANS[0]).to_numpy().sum()), 0)
            masks_b = pd.read_csv(Path(str(out) + '_report') / 'masks' / 'T_b' / 'T_b_md.csv', index_col=0)
            self.assertTrue((masks_b[SCANS[1]] == 1).all())

    def test_rowwise_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = self.run_method(tmp, 'linear', rowwise=True)
            df = pd.read_csv(out / 'fa' / 'T_b_fa.csv', index_col=0)
            self.assertEqual(df.index.name, 'case_id')
            self.assertIn(SCANS[1], df.index)
            truth = field('fa', points_of('T_b'), 1)
            self.assertLess(np.max(np.abs(df.loc[SCANS[1]].to_numpy(dtype=float) - truth)), 1e-4)

    def test_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = self.run_method(tmp, 'arc-linear', fallback='knn', k=5)
            self.check_gap(out, 1e-5)  # the gap by arc-linear
            self.check_whole(out, 0.05)  # the whole profile by knn
            summary = pd.read_csv(Path(str(out) + '_report') / 'imputation_summary.csv')
            self.assertEqual(set(summary['methods']), {'arc-linear', 'knn'})

    def test_min_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = make_dataset(tmp, tracts=('T_a', 'T_b'))
            drop(prof / 'T_b' / 'T_b_fa.csv', SCANS[2])
            blank(prof / 'T_a' / 'T_a_fa.csv', SCANS[2], ARCS[:30])  # 11 of 82 fa values observed
            out = Path(tmp) / 'out'
            ip.run(args_for(prof, axes, out, method='knn'))
            summary = pd.read_csv(Path(str(out) + '_report') / 'imputation_summary.csv')
            row = summary[(summary['scan'] == SCANS[2]) & (summary['tract'] == 'T_b')].iloc[0]
            self.assertEqual(row['n_imputed'], 0)
            self.assertIn('below --min-observed', row['left_reason'])

    def test_siren_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for inputs in ip.SIREN_INPUTS:
                _, out = self.run_method(os.path.join(tmp, inputs.replace('+', '_')), 'siren', siren_inputs=inputs,
                                         epochs=30, hidden_width=32, hidden_layers=1, device='cpu')
                df = pd.read_csv(out / 'T_b' / 'T_b_fa.csv', index_col=0)
                self.assertTrue(np.isfinite(df[SCANS[1]].to_numpy()).all())


class TestValidation(unittest.TestCase):

    def test_region_hides_every_tract_through_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = make_dataset(tmp)
            cohort = ip.Cohort(ip.read_tables(str(prof)), ip.read_axes(str(axes), ['T_a', 'T_b', 'T_c', 'T_d', 'T_x']))
            Y = cohort.scan(0)
            hidden = ip.hide_region(cohort, Y, np.random.default_rng(1), (4.0, 4.0))
            self.assertEqual(ip.hide_region(cohort, Y, np.random.default_rng(1), (50.0, 50.0)), {})  # all tracts
            self.assertTrue(set(hidden.values()) == {ip.REGION})
            tracts = {cohort.tracts[cohort.tract_of[p]] for p in hidden}
            self.assertGreaterEqual(len(tracts), 2)  # 4 mm reaches the tracts 3 mm apart
            for t in tracts:  # whole profiles
                sl = cohort.slices[t]
                self.assertEqual(sum(1 for p in hidden if sl.start <= p < sl.stop), sl.stop - sl.start)

    def test_validation_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = make_dataset(tmp)
            out = Path(tmp) / 'Imp'
            args = args_for(prof, axes, out, validate=True, validate_scans=4, validate_whole_fraction=0.2,
                            validate_gap_fraction=0.5, validate_k='1,3', validate_siren_inputs='xyz,xyz+arc',
                            validate_region_mm='2,3',
                            validate_omega0='10', validate_epochs='5,10', validate_seeds=2, hidden_width=16,
                            hidden_layers=1, device='cpu')
            self.assertEqual(ip.run(args), 0)
            vdir = Path(str(out) + '_report') / 'validation'
            for name in ('validation_summary.csv', 'validation_by_metric.csv', 'validation_by_tract.csv',
                         'axis_proximity.csv', 'validation_settings.json', 'validation_siren_epochs.png'):
                self.assertTrue((vdir / name).exists(), name)
            self.assertFalse(out.exists())  # validation imputes nothing
            s = pd.read_csv(vdir / 'validation_summary.csv')
            self.assertEqual(set(s['pattern']), {ip.GAP, ip.END, ip.WHOLE, ip.REGION})
            siren = s[s['method'] == 'siren']
            self.assertEqual(len(siren), 2 * 2 * 4)  # inputs x epochs x patterns
            ref = s[s['method'] == ip.REFERENCE]
            self.assertEqual(len(ref), 4)
            self.assertTrue((ref['coverage'] == 1).all())
            self.assertTrue(np.allclose(ref['vs_reference'], 1.0))
            lin_s = s[(s['setting'] == 'linear')].dropna(subset=['vs_reference'])
            self.assertTrue((lin_s['vs_reference'] < 0.05).all())  # exact on a linear field, the mean is not
            bym = pd.read_csv(vdir / 'validation_by_metric.csv')
            self.assertIn('vs_reference', bym.columns)
            arc_end = s[(s['pattern'] == ip.END)].set_index('setting')
            self.assertEqual(arc_end.loc['arc-linear', 'coverage'], 0)  # no extrapolation by default
            self.assertEqual(arc_end.loc['arc-linear ends=linear', 'coverage'], 1)
            self.assertLess(arc_end.loc['arc-linear ends=linear', 'nrmse'], 0.05)  # linear field: exact
            self.assertTrue((siren['n_seeds'] == 2).all())
            lin = s[(s['method'] == 'linear')]
            self.assertTrue((lin['nrmse'].dropna() < 0.05).all() and lin['nrmse'].notna().any())  # exact where it fills
            arc = s[(s['setting'] == 'arc-linear')].set_index('pattern')
            self.assertEqual(arc.loc[ip.GAP, 'coverage'], 1.0)
            self.assertTrue(arc.loc[ip.WHOLE, 'coverage'] == 0 or np.isnan(arc.loc[ip.WHOLE, 'coverage']))
            dist = pd.read_csv(vdir / 'validation_by_distance.csv')
            self.assertEqual(set(dist['pattern']), {ip.GAP, ip.END, ip.WHOLE, ip.REGION})
            lin = dist[(dist['setting'] == 'linear') & (dist['metric'] == 'all')]
            self.assertTrue(set(lin['distance_mm']) <= {'0-2', '2-4', '4-6', '6-10', '10-15', '15-20', '20-25', '25-inf'})
            self.assertEqual(int(lin['n_hidden'].sum()), int(s[s['setting'] == 'linear']['n_hidden'].sum()))
            prox = pd.read_csv(vdir / 'axis_proximity.csv').set_index('tract')
            self.assertAlmostEqual(prox.loc['T_a', 'min_mm'], 1.0, places=3)  # T_x is 1 mm above T_a
            settings = json.loads((vdir / 'validation_settings.json').read_text())
            self.assertEqual(len(settings['scans']), 4)
            # both weightings of knn
            knn = set(s[(s['method'] == 'knn') & (s['pattern'] == ip.GAP)]['setting'])
            self.assertEqual(knn, {'knn k=1 distance', 'knn k=1 uniform', 'knn k=3 distance', 'knn k=3 uniform'})

    def test_errors_per_location(self):
        from dtiplayground.dmri.common import fibers
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = make_dataset(tmp)
            out = Path(tmp) / 'Imp'
            args = args_for(prof, axes, out, validate=True, validate_scans=6, validate_rounds=3,
                            validate_whole_fraction=0.4, validate_gap_fraction=0.5, validate_k='3', validate_region_mm='2,3',
                            validate_siren_inputs='xyz', validate_omega0='10', validate_epochs='5,10',
                            validate_seeds=1, hidden_width=16, hidden_layers=1, device='cpu')
            ip.run(args)
            vdir = Path(str(out) + '_report') / 'validation'
            loc = pd.read_csv(vdir / 'validation_by_location.csv')
            # best setting of each method per pattern: arc-linear, linear, knn, one siren epochs
            self.assertEqual(set(loc['method']), {'arc-linear', 'linear', 'knn', 'siren', ip.REFERENCE})
            self.assertEqual(set(loc['metric']), {'fa', 'md', 'all'})
            lin = loc[(loc['method'] == 'linear') & (loc['metric'] == 'all')]
            self.assertTrue((lin['n_hidden'] > 0).all())
            self.assertTrue(np.allclose(lin[['x', 'y', 'z']].to_numpy(),
                                        np.vstack([points_of(t)[ARCS == a] for t, a in zip(lin['tract'], lin['arc_length'])])))
            # 18 scan rounds, 40% of the tracts hidden whole: positions are hidden several times
            whole = lin[lin['pattern'] == ip.WHOLE]
            self.assertIn(ip.REGION, set(lin['pattern']))
            self.assertGreater(whole['n_hidden'].max(), 2 * 2)  # x 2 metrics pooled
            maps = sorted(p.name for p in (vdir / 'error_maps').iterdir())
            self.assertIn('linear.vtk', maps)
            self.assertIn('linear.png', maps)
            self.assertTrue({'knn_k_3_distance.vtk', 'knn_k_3_uniform.vtk'} & set(maps))
            poly = fibers.read_fibers(str(vdir / 'error_maps' / 'linear.vtk'))
            self.assertEqual(poly.number_of_fibers, 5)
            for name in ('arc_length', 'gap_n', 'gap_nrmse', 'whole_nrmse', 'whole_nrmse_fa', 'whole_nrmse_md'):
                self.assertIn(name, poly.point_data)
            w = np.asarray(poly.point_data['whole_nrmse'])
            self.assertTrue(np.nanmax(w) < 0.05)  # linear is exact on the linear field, up to rounding


if __name__ == '__main__':
    unittest.main()


# phase 2: scans with ages in their names, tracts with very different levels, and a deviation per scan that is the
# same everywhere: the raw values of the neighbouring tracts say little, the deviations everything
AGED = ['sub-{:02d}_ses-{:03d}m_dwi'.format(i, age) for i, age in enumerate([1, 2, 3, 5, 6, 8, 12, 20, 30, 40, 50, 60])]
LEVEL = {'T_a': 0.30, 'T_b': 0.60, 'T_c': 0.35, 'T_d': 0.50, 'T_x': 0.45}


def leveled(metric, tract, s):
    scale = 1.0 if metric == 'fa' else 0.002
    return np.full(len(ARCS), scale * (LEVEL[tract] + 0.01 * (s % 4) + 0.002 * s))


def aged_dataset(tmp):
    from dtiplayground.dmri.fiberprofile.analysis import profile_qc
    prof, axes = make_dataset(tmp, scans=AGED, value=leveled)
    tables = sorted(str(p) for p in prof.rglob('*.csv'))
    profile_qc.write_agebin_stats(tables, profile_qc.parse_bins(ip.DEFAULT_BINS), 1)
    return prof, axes


class TestPrior(unittest.TestCase):

    def test_prior_from_files_and_bins(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            cohort = ip.Cohort(ip.read_tables(str(prof)), ip.read_axes(str(axes), list(LEVEL)))
            ages = ip.scan_ages(cohort)
            self.assertEqual(ages[:3], [1.0, 2.0, 3.0])
            prior = ip.Prior.from_files(cohort, str(prof), ages)
            self.assertEqual([b[2] for b in prior.bins], ['0-3m', '4-9m', '10-60m'])
            self.assertEqual(prior.scan_bin.tolist(), [0, 0, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2])
            mean, sd = prior.norm(0)
            sl, m = cohort.slices['T_b'], cohort.metrics.index('fa')
            expect = np.mean([leveled('fa', 'T_b', s)[0] for s in range(3)])
            self.assertTrue(np.allclose(mean[sl, m], expect))

    def test_prior_from_cohort_leaves_the_scan_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            cohort = ip.Cohort(ip.read_tables(str(prof)), None)
            prior = ip.Prior.from_cohort(cohort, ip.bins_from_spec(ip.DEFAULT_BINS), ip.scan_ages(cohort))
            mean, sd = prior.norm(6, cohort.scan(6))  # bin 10-60m: scans 6..11, without 6
            m = cohort.metrics.index('fa')
            others = [leveled('fa', 'T_a', s)[0] for s in range(7, 12)]
            sl = cohort.slices['T_a']
            self.assertTrue(np.allclose(mean[sl, m], np.mean(others)))
            self.assertTrue(np.allclose(sd[sl, m], max(np.std(others, ddof=1), prior.floor[m])))

    def test_prior_from_cohort_leaves_the_subject_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            cohort = ip.Cohort(ip.read_tables(str(prof)), None)
            prior = ip.Prior.from_cohort(cohort, ip.bins_from_spec(ip.DEFAULT_BINS), ip.scan_ages(cohort))
            # scan 7 as another session of the subject of scan 6 (same bin), scan 0 one in another bin
            mean, _ = prior.norm(6, cohort.scan(6), [(cohort.scan(7), prior.scan_bin[7]),
                                                     (cohort.scan(0), prior.scan_bin[0])])
            m, sl = cohort.metrics.index('fa'), cohort.slices['T_a']
            self.assertTrue(np.allclose(mean[sl, m], np.mean([leveled('fa', 'T_a', s)[0] for s in range(8, 12)])))

    def test_validation_per_age_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            out = Path(tmp) / 'Imp'
            ip.run(args_for(prof, axes, out, validate=True, validate_scans_per_bin=2, validate_whole_fraction=0.4,
                            validate_gap_fraction=0.5, validate_region_mm='2,3', validate_methods='linear,prior-mean',
                            no_plots=True))
            v = Path(str(out) + '_report') / 'validation'
            self.assertEqual(len(json.load(open(v / 'validation_settings.json'))['scans']), 6)
            a = pd.read_csv(v / 'validation_by_age_bin.csv')
            self.assertEqual(set(a['age_bin']), {'0-3m', '4-9m', '10-60m'})
            self.assertTrue({'linear', 'linear (z)', 'prior-mean'} <= set(a['setting']))
            s = pd.read_csv(v / 'validation_summary.csv').set_index(['setting', 'pattern'])
            self.assertTrue(np.allclose(s.xs('prior-mean')['vs_age_mean'], 1.0))  # its own reference
            self.assertTrue(np.allclose(s.xs('cohort mean (reference)')['vs_reference'], 1.0))
            # completed with the age bin mean: prior-mean stays 1, a setting that fills nothing of a pattern too
            self.assertTrue(np.allclose(s.xs('prior-mean')['vs_age_mean_completed'], 1.0))
            m = pd.read_csv(v / 'validation_by_metric.csv')
            self.assertTrue((m.loc[m.method != 'reference', 'n_completed'] == m.loc[m.method != 'reference', 'n_hidden']).all())

    def test_defaults_follow_the_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            a = ip.resolve_defaults(args_for(prof, axes, Path(tmp) / 'a'))
            self.assertEqual((a.method, a.fallback, a.relative_to_prior), ('arc-linear', 'none', False))
            self.assertEqual((a.siren_inputs, a.omega0, a.epochs, a.k), ('xyz+tract', 30.0, 1000, 1))
            b = ip.resolve_defaults(args_for(prof, axes, Path(tmp) / 'b', prior_stats_dir=prof))
            self.assertEqual((b.method, b.fallback, b.relative_to_prior), ('siren', 'prior-mean', True))
            self.assertEqual((b.siren_inputs, b.omega0, b.epochs, b.k), ('xyz', 10.0, 500, 20))
            self.assertEqual((a.max_distance, b.max_distance), (10.0, 20.0))
            c = ip.resolve_defaults(args_for(prof, axes, Path(tmp) / 'c', prior_stats_dir=prof, method='knn', k=5))
            self.assertEqual((c.method, c.k, c.relative_to_prior), ('knn', 5, True))
            d = ip.resolve_defaults(args_for(prof, axes, Path(tmp) / 'd', method='siren'))
            self.assertEqual((d.relative_to_prior, d.siren_inputs), (False, 'xyz+tract'))

    def test_default_with_prior_fills_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            drop(prof / 'T_b' / 'T_b_fa.csv', AGED[7])
            out = Path(tmp) / 'out'
            ip.run(args_for(prof, axes, out, prior_stats_dir=prof, epochs=20, device='cpu'))
            df = pd.read_csv(out / 'T_b' / 'T_b_fa.csv', index_col=0)
            self.assertFalse(df[AGED[7]].isna().any())
            settings = json.load(open(Path(str(out) + '_report') / 'imputation_settings.json'))
            self.assertEqual((settings['method'], settings['fallback']), ('siren', 'prior-mean'))

    def test_relative_knn_recovers_whole_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            for metric in ('fa', 'md'):
                drop(prof / 'T_b' / 'T_b_{}.csv'.format(metric), AGED[7])
            truth = leveled('fa', 'T_b', 7)
            errs = {}
            for rel in (False, True):
                out = Path(tmp) / ('z' if rel else 'raw')
                kw = dict(method='knn', k=1, prior_stats_dir=prof, fallback='none')
                kw['relative_to_prior' if rel else 'no_relative_to_prior'] = True
                ip.run(args_for(prof, axes, out, **kw))
                df = pd.read_csv(out / 'T_b' / 'T_b_fa.csv', index_col=0)
                errs[rel] = np.max(np.abs(df[AGED[7]].to_numpy() - truth))
            self.assertGreater(errs[False], 0.1)  # the level of a neighbouring tract
            self.assertLess(errs[True], 0.01)  # the scan's deviation, on the norm of T_b

    def test_scan_missing_most_tracts_is_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            for tract in ('T_a', 'T_b', 'T_c'):  # 3 of 5 tracts of scan 4
                for metric in ('fa', 'md'):
                    drop(prof / tract / '{}_{}.csv'.format(tract, metric), AGED[4])
            out = Path(tmp) / 'out'
            ip.run(args_for(prof, axes, out, method='prior-mean', prior_stats_dir=prof))
            self.assertNotIn(AGED[4], pd.read_csv(out / 'T_a' / 'T_a_fa.csv', index_col=0).columns)
            summary = pd.read_csv(Path(str(out) + '_report') / 'imputation_summary.csv')
            self.assertTrue(summary.loc[summary['scan'] == AGED[4], 'left_reason'].str.contains('3 of 5 tracts').all())
            ip.run(args_for(prof, axes, Path(tmp) / 'all', method='prior-mean', prior_stats_dir=prof,
                            max_missing_tracts=1))
            self.assertIn(AGED[4], pd.read_csv(Path(tmp) / 'all' / 'T_a' / 'T_a_fa.csv', index_col=0).columns)

    def test_prior_mean_fills_a_missing_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            for tract in LEVEL:  # scan 4 has no md at all
                drop(prof / tract / '{}_md.csv'.format(tract), AGED[4])
            out = Path(tmp) / 'out'
            ip.run(args_for(prof, None, out, method='prior-mean', prior_stats_dir=prof))
            df = pd.read_csv(out / 'T_c' / 'T_c_md.csv', index_col=0)
            expect = np.mean([leveled('md', 'T_c', s)[0] for s in (3, 4, 5)])  # the 4-9m bin of the statistics
            self.assertTrue(np.allclose(df[AGED[4]], expect, rtol=1e-4))

    def test_validation_with_prior(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof, axes = aged_dataset(tmp)
            out = Path(tmp) / 'Imp'
            ip.run(args_for(prof, axes, out, validate=True, validate_scans=12, validate_whole_fraction=0.4,
                            validate_gap_fraction=0.5, validate_region_mm='2,3', validate_methods='knn,linear,prior-mean',
                            validate_k='1', no_plots=True))
            s = pd.read_csv(Path(str(out) + '_report') / 'validation' / 'validation_summary.csv')
            self.assertTrue({'knn k=1 distance (z)', 'linear (z)', 'prior-mean'} <= set(s['setting']))
            w = s[s['pattern'] == ip.WHOLE].set_index('setting')
            self.assertLess(w.loc['knn k=1 distance (z)', 'nrmse'], w.loc['knn k=1 distance', 'nrmse'])
