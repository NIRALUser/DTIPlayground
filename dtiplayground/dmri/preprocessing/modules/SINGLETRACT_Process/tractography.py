
  
import dtiplayground.dmri.preprocessing as prep
import yaml, os, time
from pathlib import Path
from copy import deepcopy
import numpy as np
logger=prep.logger.write

import dipy.reconst.dti as dti

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
def compute(tensorImage, labelmapImage, output_dir, scalar='fa' , axis=0):
    

    img = tensorImage.images
    logger("Computing {}...".format(scalar_function_map[scalar]['message'],prep.Color.PROCESS)
    img_scalar = np.apply_along_axis(scalar_function_map[scalar]['func'], axis, img)
    labelimg = labelmapImage.images
    print(img.shape)
    print(img_scalar.shape)
    print(labelimg.shape)

    print(np.max(labelimg))
    scalar_file = Path(output_dir).joinpath('{}.nrrd'.format(scalar)).__str__()

    newImg = deepcopy(tensorImage)
    newImg.updateImage3D(img_scalar)
    newImg.writeImage(scalar_file, dest_type='nrrd', dtype='float')


    # logger("Computing Geodesic Anisotropy...",prep.Color.PROCESS)
    # img_ga = np.apply_along_axis(ga, 0, img)
    # print(img_ga.shape)


    exit(0)
