
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
import dtiplayground.dmri.preprocessing as prep
import os 

logger=prep.logger.write


@prep.measure_time
def interlace_compute(image_obj):
    image_obj.images=image_obj.images.astype(float)
    # affine=np.transpose(np.append(image_obj.information['space_directions'],np.expand_dims(image_obj.information['space_origin'],0),axis=0))
    # affine=np.append(affine,np.array([[0,0,0,1]]),axis=0)
    affine=image_obj.getAffineMatrixForNifti()
    x,y,z,g = image_obj.images.shape
    evens=[x for x in range(0,z) if x % 2 == 0]
    odds=[x for x in range(0,z) if x % 2 ==1]
    if z % 2 == 1:
        evens.pop()

    output=[]
    for gidx in range(0,g):

        #### interlaing a volume
        static=image_obj.images[:,:,evens,gidx]
        moving=image_obj.images[:,:,odds,gidx]

        #### Correlation and Motion detection
        corr=ncc(moving,static)
        #logger("\rGradient {}/{}, Corr: {:.4f} , registering for motion detection ...".format(gidx,g,corr))
        transformed, out_affine=rigid_3d(static,moving,affine,affine ,
                                                      nbins=32,
                                                      level_iters=[10000,1000,100],
                                                      sigmas=[3.0,1.0,0.0],
                                                      factors=[4,2,1],sampling_prop=0.1)
        affine_info=decompose_affine_matrix(out_affine)
        max_norm=np.max(np.abs(affine_info["translations"]))
        max_angle_in_deg=np.max(np.rad2deg(np.abs(affine_info["angles"])))
        logger("Gradient {}/{}, Corr: {:.4f}, Max translation : {:.4f} , Max angle : {:.4f} degree".format(gidx,g-1,corr,max_norm,max_angle_in_deg))
        output.append({"gradient_index": gidx, 
                       "original_gradient_index": image_obj.getGradients()[gidx]['original_index'], 
                       "affine_matrix":out_affine.tolist(),
                       "correlation": float(corr),
                       "motions": affine_info})

    return output

@prep.measure_time
def interlace_check(image_obj, computation_result,
                    correlationDeviationBaseline=2.5,
                    correlationDeviationGradient=3.0,
                    correlationThresholdBaseline=0.95,
                    correlationThresholdGradient=0.7702,
                    rotationThreshold=0.5,
                    translationThreshold=1.5):
    result_size=len(computation_result)
    correlations=[x['correlation'] for x in computation_result]
    corr_avg=np.mean(correlations)
    corr_std=np.std(correlations)
    gradients=image_obj.getGradients()
    quadfit=quadratic_fit_generator(image_obj.getBValueBounds(),
                                    [min(correlationDeviationBaseline,correlationDeviationGradient),max(correlationDeviationBaseline,correlationDeviationGradient)]
                                    )
    excluding_gradients_indexes=[]
    interlacing_results=[]
    for idx,g in enumerate(computation_result):
        #logger("Checking Gradient {}/{} ".format(idx,result_size-1),prep.Color.PROCESS)
        result=g
        translation=np.max(np.abs(g['motions']['translations']))
        rotation_in_degree=np.max(np.rad2deg(np.abs(g['motions']['angles'])))
        correlation=g['correlation']
        corr_z=(correlation-corr_avg)/corr_std
        isB0=image_obj.isGradientBaseline(g['gradient_index'])
        bval=gradients[idx]['b_value']

        check_rotation= rotation_in_degree <= rotationThreshold
        check_translation= translation <= translationThreshold
        check_correlation= True
        quad_fitted_z_threshold=quadfit(bval)

        if isB0:
            check_correlation= not(corr_z < -quad_fitted_z_threshold)
        else:
            check_correlation= not(corr_z < -quad_fitted_z_threshold)

        excluded=not(check_rotation and check_translation and check_correlation)
        if not excluded:
            color=prep.Color.OK
        else:
            color=prep.Color.WARNING
            excluding_gradients_indexes.append(idx)
        logger("[Grad.idx:{0:03d}, Org.idx:{1:03d}]\tBaseline: {2}, Max.Trans: {3:.2f} , Max.Rotation: {4:.2f}deg, Corr: {5:.4f}, Corr-Z: {6:4f}"
            .format(g['gradient_index'],
                    g['original_gradient_index'],
                    isB0,
                    translation,
                    rotation_in_degree,
                    correlation,
                    corr_z
                    ),color)

        logger("\t\t\t\tZ-Threshold: {:.4f}, Check.Trans: {}, Check.Rotation: {}, Check.Corr: {}"
            .format(quad_fitted_z_threshold,
                    check_translation,
                    check_rotation,
                    check_correlation
                    ),color)

        g['max_translation']=float(translation )
        g['max_rotation_in_degree']=float(rotation_in_degree )
        g['check_translation']=bool(check_translation)
        g['check_rotation']=bool(check_rotation)
        g['check_correlation']=bool(check_correlation)
        g['excluded']=bool(excluded)
        g['corr_z_value']=float(corr_z)
        g['isB0']=bool(isB0)
        g['quad_fitted_z_threshold']=float(quad_fitted_z_threshold)
        g['b_value']=float(bval)
        interlacing_results.append(g)

    return excluding_gradients_indexes, interlacing_results
        

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

@prep.measure_time
def rigid_3d(static,moving,
             affine_static,affine_moving,
             nbins=32,
             level_iters=[10000,1000,100],
             sigmas=[3.0,1.0,0.0],
             factors=[4,2,1],
             sampling_prop=None):
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
    metric= MutualInformationMetric(nbins,sampling_prop)
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
             factors=[4,2,1],
             sampling_prop=None):
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
