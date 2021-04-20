
import numpy as np 
from dipy.align.imaffine import (transform_centers_of_mass,
                                 AffineMap,
                                 MutualInformationMetric,
                                 AffineRegistration)
import dipy.align 
from dipy.align.transforms import (TranslationTransform2D,
                                   RigidTransform2D,
                                   AffineTransform2D,
                                   TranslationTransform3D,
                                   RigidTransform3D,
                                   AffineTransform3D)
import dtiprep

logger=dtiprep.logger.write

def baseline_average(image_obj, opt,
                      averageInterpolationMethod='linear-interpolation',
                      averageMethod='BaselineOptimized',
                      b0Threshold=10,
                      stopThreshold=0.02):
    return None

def _quad_fit(bval, domain=[0,1000], fimage=[3.0,3.5]): #returns std multiple between fimage
    if bval > domain[1] : 
        return fimage[1]
    elif bval < domain[0] : 
        return fimage[0]
    a= (fimage[1]-fimage[0])/((domain[1]-domain[0])**2)
    c= fimage[0]
    return a*(bval**2)+c

def quadratic_fit_generator(domain,fimage):
    def wrapper(bval):
        return _quad_fit(bval,domain,fimage)
    return wrapper

def ncc(x,y): #normalized cross correlation in image (ref: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/ )
    ab=np.sum(x*y)
    a2=np.sum(x**2)
    b2=np.sum(y**2)
    if a2*b2==0.0: 
        return 1.0
    else:
        return ab/np.sqrt(a2*b2)

def affine_3d_to_2d(mat,indices=[0,1]):
    new_mat=mat.copy()
    to_remove=list(set(range(mat.shape[0]-1))-set(indices))
    new_mat=np.delete(new_mat,to_remove,axis=0)
    new_mat=np.transpose(np.delete(np.transpose(new_mat),to_remove,axis=0))
    return new_mat

def decompose_affine_matrix(mat4d): ## r
    scale, shear, angles, trans, persp =dipy.align.streamlinear.decompose_matrix(mat4d)
    angles_in_deg=list(map(lambda x : float(np.rad2deg(x)), angles))
    res={"scale":scale.tolist(),
         "shear":list(map(float,shear)),
         "angles":angles,
         "angles_in_degree":angles_in_deg,
         "translations":trans.tolist(),
         "perspective":persp.tolist()}
    return res

def measure_translation_from_affine_matrix(mat):
    translation=mat[:,2][:2]
    norm=np.sqrt(np.sum(translation*translation))
    return norm 

def measure_max_translation_from_affine_matrix(mat):
    translation=np.abs(mat[:,2][:2])
    norm=np.abs(np.max(translation))
    return norm 

@dtiprep.measure_time
def rigid_3d(static,moving,
             affine_static,affine_moving,
             nbins=32,
             level_iters=[10000,1000,100],
             sigmas=[3.0,1.0,0.0],
             factors=[4,2,1]):
    ## Make affine map
    identity=np.eye(4)
    affine_map=AffineMap(identity,static.shape, affine_static,
                                  moving.shape, affine_static)

    ## Resample moving image from affine (but same in a volume)
    resampled=affine_map.transform(moving)

    ## center of mass transform
    c_of_mass = transform_centers_of_mass(static, affine_static, moving, affine_moving)
    transformed=c_of_mass.transform(moving)

    ## registration preparation
    nbins=32
    sampling_prop = None
    metric= MutualInformationMetric(nbins,sampling_prop)
    level_iters=[10000,1000,100]
    sigmas = [3.0, 1.0, 0.0]
    factors= [4,2,1]
    affreg= AffineRegistration(metric=metric, 
                               level_iters=level_iters, 
                               sigmas=sigmas, 
                               factors=factors,
                               verbosity=0)

    ## Translation transform registration
    transform=TranslationTransform3D()
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
    transform=RigidTransform3D()
    params0=None
    starting_affine=translation.affine
    rigid=affreg.optimize(static,moving,transform,params0,affine_static,affine_moving,starting_affine=starting_affine)
    transformed = rigid.transform(moving)

    return transformed, rigid.affine 



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

    # Translation transform registration
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
