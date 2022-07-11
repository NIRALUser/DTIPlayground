
  
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
    logger("{} was chosen for the scalars".format(scalar_function_map[scalar]['message']),prep.Color.INFO)
    logger("Computing {}...".format(scalar_function_map[scalar]['message']),prep.Color.PROCESS)
    img_scalar = np.apply_along_axis(scalar_function_map[scalar]['func'], axis, img)
    img_label = labelmapImage.images

    scalar_file = Path(output_dir).joinpath('{}.nrrd'.format(scalar)).__str__()

    newImg = deepcopy(tensorImage)
    newImg.updateImage3D(img_scalar)
    newImg.writeImage(scalar_file, dest_type='nrrd', dtype='float')

    affine=tensorImage.getAffineMatrixForNifti()

    labels=img_label


    exit(0)
