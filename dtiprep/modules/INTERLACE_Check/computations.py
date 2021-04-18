
import numpy as np 
from dipy.align.imaffine import (transform_centers_of_mass,
                                 AffineMap,
                                 MutualInformationMetric,
                                 AffineRegistration)
from dipy.align.transforms import (TranslationTransform2D,
                                   RigidTransform2D,
                                   AffineTransform2D)
import dtiprep

def affine_3d_to_2d(mat,indices=[0,1]):
    new_mat=mat.copy()
    to_remove=list(set(range(mat.shape[0]-1))-set(indices))
    new_mat=np.delete(new_mat,to_remove,axis=0)
    new_mat=np.transpose(np.delete(np.transpose(new_mat),to_remove,axis=0))
    return new_mat

def measure_translation_from_affine_matrix(mat):
    translation=np.transpose(mat)[-1]
    norm=np.sqrt(np.sum(translation*translation))
    return norm 
    
def rigid_2d(static,moving,
             affine_static,affine_moving,
             nbins=32,
             level_iters=[10000,1000,100],
             sigmas=[3.0,1.0,0.0],
             factors=[4,2,1]):
    ## Make affine map
    identity=np.eye(3)
    affine_map=AffineMap(identity,static.shape, affine_static,
                                  moving.shape, affine_moving)

    ## Resample moving image from affine (but same in a volume)
    resampled=affine_map.transform(moving)

    ## center of mass transform
    c_of_mass = transform_centers_of_mass(static, affine_static, moving, affine_moving)
    transformed=c_of_mass.transform(moving)

    ## registration preparation
    sampling_prop = None
    metric= MutualInformationMetric(nbins,sampling_prop)
    affreg= AffineRegistration(metric=metric, 
                               level_iters=level_iters, 
                               sigmas=sigmas, 
                               factors=factors,
                               verbosity=0)

    ## Translation transform registration
    transform=TranslationTransform2D()
    params0=None
    starting_affine= c_of_mass.affine
    translation=affreg.optimize(static, 
                                moving, 
                                transform, 
                                params0, 
                                affine_static,affine_moving, 
                                starting_affine=starting_affine)
    transformed = translation.transform(moving)

    ## Ridid registration
    transform=RigidTransform2D()
    params0=None
    starting_affine=translation.affine
    rigid=affreg.optimize(static,moving,transform,params0,affine_static,affine_moving,starting_affine=starting_affine)
    transformed = rigid.transform(moving)

    return transformed, rigid.affine 
