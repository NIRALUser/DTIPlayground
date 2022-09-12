
  
import dtiplayground.dmri.preprocessing as prep
import yaml, os, time
from pathlib import Path
from copy import deepcopy
import numpy as np
logger=prep.logger.write

### dipy
from dipy.reconst.csdeconv import auto_response
from dipy.reconst.shm import CsaOdfModel
from dipy.data import default_sphere
from dipy.direction import peaks_from_model
from dipy.core.gradients import gradient_table

from dipy.reconst.dti import TensorFit, from_lower_triangular, decompose_tensor
from dipy.data import default_sphere, small_sphere
from dipy.direction.peaks import *
from dipy.direction.peaks import _pam_from_attrs

from dipy.reconst.csdeconv import (ConstrainedSphericalDeconvModel,
                                   auto_response_ssst)
from dipy.direction import DeterministicMaximumDirectionGetter, ProbabilisticDirectionGetter
from dipy.reconst.shm import CsaOdfModel

from dipy.tracking.stopping_criterion import ThresholdStoppingCriterion
from dipy.tracking import utils
from dipy.io.vtk import save_vtk_streamlines, load_vtk_streamlines

from dipy.tracking.local_tracking import LocalTracking
from dipy.tracking.streamline import Streamlines

@prep.measure_time
def peaks_from_dti(tensorfit,sphere, relative_peak_threshold,
                     min_separation_angle, mask=None, return_odf=False,
                     return_sh=True, gfa_thr=0, normalize_peaks=False,
                     sh_order=8, sh_basis_type=None, npeaks=5, B=None,
                     invB=None, parallel=False, num_processes=None):

    if return_sh and (B is None or invB is None):
        B, invB = sh_to_sf_matrix(
            sphere, sh_order, sh_basis_type, return_inv=True)

    shape = tensorfit.shape
    if mask is None:
        mask = np.ones(shape, dtype='bool')
    else:
        if mask.shape != shape:
            raise ValueError("Mask is not the same shape as data.")

    gfa_array = np.zeros(shape)
    qa_array = np.zeros((shape + (npeaks,)))

    peak_dirs = np.zeros((shape + (npeaks, 3)))
    peak_values = np.zeros((shape + (npeaks,)))
    peak_indices = np.zeros((shape + (npeaks,)), dtype='int')
    peak_indices.fill(-1)

    if return_sh:
        n_shm_coeff = (sh_order + 2) * (sh_order + 1) // 2
        shm_coeff = np.zeros((shape + (n_shm_coeff,)))

    if return_odf:
        odf_array = np.zeros((shape + (len(sphere.vertices),)))

    global_max = -np.inf
    # odf_all = tensorfit.odf(sphere)
    for idx in ndindex(shape):
        if not mask[idx]:
            continue

        #odf = model.fit(data[idx]).odf(sphere)
        odf = tensorfit[idx].odf(sphere)
        # odf = odf_all[idx]
        if return_sh:
            shm_coeff[idx] = np.dot(odf, invB)

        if return_odf:
            odf_array[idx] = odf

        gfa_array[idx] = gfa(odf)
        if gfa_array[idx] < gfa_thr:
            global_max = max(global_max, odf.max())
            continue

        # Get peaks of odf
        direction, pk, ind = peak_directions(odf, sphere,
                                             relative_peak_threshold,
                                             min_separation_angle)

        # Calculate peak metrics
        if pk.shape[0] != 0:
            global_max = max(global_max, pk[0])

            n = min(npeaks, pk.shape[0])
            qa_array[idx][:n] = pk[:n] - odf.min()

            peak_dirs[idx][:n] = direction[:n]
            peak_indices[idx][:n] = ind[:n]
            peak_values[idx][:n] = pk[:n]

            if normalize_peaks:
                peak_values[idx][:n] /= pk[0]
                peak_dirs[idx] *= peak_values[idx][:, None]

    qa_array /= global_max

    return _pam_from_attrs(PeaksAndMetrics,
                           sphere,
                           peak_indices,
                           peak_values,
                           peak_dirs,
                           gfa_array,
                           qa_array,
                           shm_coeff if return_sh else None,
                           B if return_sh else None,
                           odf_array if return_odf else None)



@prep.measure_time
def compute(*args,**kwargs):
    
    #localTractography(*args)
    dMaxTractography(*args)
    #probTractography(*args)
    exit(0)


@prep.measure_time
def localTractography(tensorImage, dwi_image, dipyLabelmap, output_dir,**kwargs):

    output_peaks_file = Path(output_dir).joinpath('peaks.pkl').__str__()
    output_sl_file = Path(output_dir).joinpath('streamlines.vtk').__str__()

    img = tensorImage.images
    img = np.moveaxis(img,3,0)
    logger("Computing dti parameters ...",prep.Color.PROCESS)
    dtiparams = np.zeros(img.shape[1:]+(12,))
    for idx in np.ndindex(img.shape[1:]):
        x,y,z = idx
        xx, xy, xz, yy,yz, zz=img[:,x,y,z]
        tri = np.array([xx,xy,yy,xz,yz,zz])
        lt=from_lower_triangular(tri)
        eigvals, eigvecs = decompose_tensor(lt)
        dtiparams[x,y,z,0:3] = eigvals
        dtiparams[x,y,z,3:] = eigvecs.ravel()


    img_label = dipyLabelmap
    affine=tensorImage.getAffineMatrixForNifti()
    labels=img_label

    tf = TensorFit(None,dtiparams)
    logger("Computing dti peaks ...",prep.Color.PROCESS)
    peaks = peaks_from_dti(  tf, default_sphere,
                             relative_peak_threshold=.8,
                             min_separation_angle=75,
                             mask=labels)


    stopping_criterion = ThresholdStoppingCriterion(peaks.gfa, .25)
    seed_mask = (labels == 1)
    seeds = utils.seeds_from_mask(seed_mask, affine, density=[3,3,3])
    logger("Generating streamlines ...",prep.Color.PROCESS)
    streamlines_generator = LocalTracking(peaks, stopping_criterion, seeds,
                                          affine=affine, step_size=.5)
    streamlines = Streamlines(streamlines_generator)

    logger("Saving streamlines ...",prep.Color.PROCESS)
    save_vtk_streamlines(streamlines, output_sl_file, to_lps=False, binary=False)
    logger("Tractogram generation completed",prep.Color.OK)


@prep.measure_time
def dMaxTractography(tensorfit, dwi_image, dipyLabelmap, output_dir,**kwargs):


    output_peaks_file = Path(output_dir).joinpath('peaks.pkl').__str__()
    output_sl_file = Path(output_dir).joinpath('streamlines.vtk').__str__()

    data = dwi_image.images
    affine = dwi_image.getAffineMatrixForNifti()
    bvecs = [x['nifti_gradient'] for x in dwi_image.getGradients()]
    bvals = [x['b_value'] for x in dwi_image.getGradients()]
    gtab = gradient_table(bvals,bvecs)

    labels=dipyLabelmap
    seed_mask = labels == (labels == 1) | (labels == 2)
    white_matter = (labels == 1) | (labels == 2)
    # seed_mask = labels >= 0
    # white_matter = seed_mask
    seeds = utils.seeds_from_mask(seed_mask, affine, density=[1,1,1])
    response, ratio = auto_response_ssst(gtab, data, roi_radii=10, fa_thr=0.7)

    csd_model = ConstrainedSphericalDeconvModel(gtab, response, sh_order=6)
    csd_fit = csd_model.fit(data, mask=white_matter)

    csa_model = CsaOdfModel(gtab, sh_order=6)
    gfa = csa_model.fit(data, mask=white_matter).gfa
    stopping_criterion = ThresholdStoppingCriterion(gfa, .25)

    detmax_dg = DeterministicMaximumDirectionGetter.from_shcoeff(
    csd_fit.shm_coeff, max_angle=70., sphere=default_sphere)
    streamline_generator = LocalTracking(detmax_dg, stopping_criterion, seeds,
                                         affine, step_size=.5)
    streamlines = Streamlines(streamline_generator)
    logger("Saving streamlines ...",prep.Color.PROCESS)
    save_vtk_streamlines(streamlines, output_sl_file, to_lps=False, binary=False)
    logger("Tractogram generation completed",prep.Color.OK)

@prep.measure_time
def probTractography(tensorfit, dwi_image, dipyLabelmap, output_dir,**kwargs):

    output_peaks_file = Path(output_dir).joinpath('peaks.pkl').__str__()
    output_sl_file = Path(output_dir).joinpath('streamlines.vtk').__str__()

    data = dwi_image.images
    affine = dwi_image.getAffineMatrixForNifti()
    bvecs = [x['nifti_gradient'] for x in dwi_image.getGradients()]
    bvals = [x['b_value'] for x in dwi_image.getGradients()]
    gtab = gradient_table(bvals,bvecs)

    labels=dipyLabelmap
    seed_mask = labels == 1
    white_matter = (labels == 1) | (labels == 2)
    seeds = utils.seeds_from_mask(seed_mask, affine, density=[1,1,1])
    response, ratio = auto_response_ssst(gtab, data, roi_radii=10, fa_thr=0.7)

    csd_model = ConstrainedSphericalDeconvModel(gtab, response, sh_order=6)
    csd_fit = csd_model.fit(data, mask=white_matter)

    csa_model = CsaOdfModel(gtab, sh_order=6)
    gfa = csa_model.fit(data, mask=white_matter).gfa
    stopping_criterion = ThresholdStoppingCriterion(gfa, .25)

    fod = csd_fit.odf(small_sphere)
    pmf = fod.clip(min=0)
    prob_dg = ProbabilisticDirectionGetter.from_pmf(pmf, max_angle=30.,
                                                    sphere=small_sphere)
    streamline_generator = LocalTracking(prob_dg, stopping_criterion, seeds,
                                         affine, step_size=.5)
    streamlines = Streamlines(streamline_generator)
    logger("Saving streamlines ...",prep.Color.PROCESS)
    save_vtk_streamlines(streamlines, output_sl_file, to_lps=False, binary=False)
    logger("Tractogram generation completed",prep.Color.OK)