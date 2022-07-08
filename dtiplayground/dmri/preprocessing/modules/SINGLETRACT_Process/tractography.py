
  
import dtiplayground.dmri.preprocessing as prep
import yaml, os, time
from pathlib import Path
from copy import deepcopy
import numpy as np
logger=prep.logger.write

import dipy.reconst.dti as dti
from dipy.tracking.stopping_criterion import ThresholdStoppingCriterion
from dipy.core.gradients import gradient_table
from dipy.data import default_sphere, get_fnames
from dipy.direction import DeterministicMaximumDirectionGetter
from dipy.io.gradients import read_bvals_bvecs
from dipy.io.image import load_nifti, load_nifti_data
from dipy.io.stateful_tractogram import Space, StatefulTractogram
from dipy.io.streamline import save_trk
from dipy.reconst.csdeconv import (ConstrainedSphericalDeconvModel,
                                   auto_response_ssst)
from dipy.reconst.shm import CsaOdfModel
from dipy.tracking import utils
from dipy.tracking.local_tracking import LocalTracking
from dipy.tracking.stopping_criterion import ThresholdStoppingCriterion
from dipy.tracking.streamline import Streamlines

def decompose(elements): #elements vector [xx, xy, xz, 
                         #                     yy, yz, 
                         #                         zz]
    mat = np.zeros((3,3),dtype=float)
    e=elements
    mat[0,0:3] = e[0:3]
    mat[1,1:3] = e[3:5]
    mat[2,2:3] = e[5]
    eigenVals , eigenVecs = np.linalg.eig(mat)
    return np.expand_dims(eigenVals,axis=0)

def fa(elements):
    return dti.fractional_anisotropy(decompose(elements))[0]

def ga(elements):
    return dti.geodesic_anisotropy(decompose(elements))[0]

scalar_function_map = {
    "fa" : {
      'func' : fa,
      'message' : 'fractional anisotropy'
      },
    "ga" : {
      'func' : ga,
      'message' : 'geodesic anisotropy'
      }
}

@prep.measure_time
def compute(tensorImage, labelmapImage, output_dir, scalar='fa' , axis=0):
    

    img = tensorImage.images
    # logger("{} was chosen for the scalars".format(scalar_function_map[scalar]['message']),prep.Color.INFO)
    # logger("Computing {}...".format(scalar_function_map[scalar]['message']),prep.Color.PROCESS)
    # img_scalar = np.apply_along_axis(scalar_function_map[scalar]['func'], axis, img)
    img_label = labelmapImage.images

    scalar_file = Path(output_dir).joinpath('{}.nrrd'.format(scalar)).__str__()

    # newImg = deepcopy(tensorImage)
    # newImg.updateImage3D(img_scalar)
    # newImg.writeImage(scalar_file, dest_type='nrrd', dtype='float')

    affine=tensorImage.getAffineMatrixForNifti()
    
    # logger("Computing Geodesic Anisotropy...",prep.Color.PROCESS)
    # img_ga = np.apply_along_axis(ga, 0, img)
    # print(img_ga.shape)
    labels=img_label
    seed_mask = labels == 2
    white_matter = (labels == 1) | (labels == 2)
    seeds = utils.seeds_from_mask(seed_mask, affine, density=1)
    response, ratio = auto_response_ssst(gtab, data, roi_radii=10, fa_thr=0.7)
    csd_model = ConstrainedSphericalDeconvModel(gtab, response, sh_order=6)
    csd_fit = csd_model.fit(data, mask=white_matter)

    csa_model = CsaOdfModel(gtab, sh_order=6)
    gfa = csa_model.fit(data, mask=white_matter).gfa

    stopping_value = 0.25
    stopping_criteria = ThresholdStoppingCriterion(img_scalar, stopping_value)


    stopping_criterion = ThresholdStoppingCriterion(gfa, .25)
    detmax_dg = DeterministicMaximumDirectionGetter.from_shcoeff(
    csd_fit.shm_coeff, max_angle=30., sphere=default_sphere)
    streamline_generator = LocalTracking(detmax_dg, stopping_criterion, seeds,
                                         affine, step_size=.5)
    streamlines = Streamlines(streamline_generator)

    sft = StatefulTractogram(streamlines, hardi_img, Space.RASMM)
    save_trk(sft, "tractogram_deterministic_dg.trk")


    exit(0)
