#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

import dtiplayground.dmri.preprocessing as prep

import yaml,traceback 
import numpy as np
import time
from pathlib import Path
import os
import markdown

from dipy.align.imaffine import (transform_centers_of_mass,
                                 AffineMap,
                                 MutualInformationMetric,
                                 AffineRegistration)
import dipy.align 
from dipy.align.transforms import (TranslationTransform3D,
                                   RigidTransform3D,
                                   AffineTransform3D)
import dtiplayground.dmri.preprocessing as prep
import copy


def baseline_average(image_obj, opt,
                      averageInterpolationMethod='linear-interpolation',
                      averageMethod='BaselineOptimized',
                      b0Threshold=10,
                      stopThreshold=0.02,
                      maxIterations=2):
    
    image=copy.copy(image_obj)
    averaged_baseline_image=None #2d image
    output=None

    ## baseline gradients and volum extraction  
    baseline_grads, _=image_obj.getBaselines(b0_threshold=b0Threshold)
    logger("Finding baseline gradients : ",prep.Color.INFO)
    for idx,g in enumerate(baseline_grads):
        logger("Gradient.idx {:03d} Original.idx {:03d} Direction {} B-value {:.1f}"
            .format(g['index'],g['original_index'],g['gradient'],g['b_value']),prep.Color.INFO)

    ### Check availability 
    no_baseline=False
    only_one_baseline=False
    if len(baseline_grads)<2:
        if len(baseline_grads)<1: no_baseline=True
        else: only_one_baseline=True

    ### computation
    if no_baseline:
        logger("[WARNING] There was no baseline found",prep.Color.WARNING)
        b0Threshold = min(list(map(lambda x: x['b_value'], image.getGradients())))
        #return None,[]
        output=direct_average(image, averageInterpolationMethod, b0Threshold,stopThreshold)
    elif averageMethod=='DirectAverage' or only_one_baseline:
        if only_one_baseline: logger("Only one baseline was found, averaging method will be changed to DirectAverage",prep.Color.WARNING)
        output=direct_average(image, averageInterpolationMethod, b0Threshold,stopThreshold)
    elif averageMethod=='BaselineOptimized':    
        output=baseline_optimized_average(image, averageInterpolationMethod, b0Threshold,stopThreshold,maxIterations)
    elif averageMethod=='BSplineOptimized':
        logger("[WARNING] BSplineOptimized method is NOT implemented, averaging method will be changed to baseline optimized averaging",prep.Color.WARNING)
        output=baseline_optimized_average(image, averageInterpolationMethod, b0Threshold,stopThreshold,maxIterations)

    averaged_baseline_volume = output['averaged_baseline']
    output_gradient= output['output_baseline_gradient'] ## single gradient
    baseline_gradients= output['baseline_gradients']

    #post processing. To remove baselines from the original image and insert the averaged basline image. Re-indexing of gradients
    image.deleteGradientsByOriginalIndex([x['original_index'] for x in baseline_gradients])
    image.insertGradient(output_gradient,averaged_baseline_volume,pos=0)
    excluded_gradients_original_indexes=[x['original_index'] for x in baseline_gradients]

    return image , excluded_gradients_original_indexes

def default_output_gradient():
    return {
        "index" : None,
        "original_index" : -1,
        "gradient" : [0.0,0.0,0.0],
        "unit_gradient" : [0.0,0.0,0.0],
        "b_value" : 0,
        "baseline" : True 
    }

def direct_average(image_obj, averageInterpolationMethod , b0Threshold, stopThreshold):
    logger("Direct averaging on the baseline(s) ... ",prep.Color.PROCESS)
    baseline_grads, baseline_images=image_obj.getBaselines(b0_threshold=b0Threshold)
    out_gradient=default_output_gradient()
    output={"averaged_baseline" : np.mean(baseline_images,axis=3) ,
            "output_baseline_gradient" : out_gradient, 
            "baseline_gradients" : baseline_grads}
    logger("Direct averaging DONE ",prep.Color.OK)
    return output

def baseline_optimized_average(image_obj, averageInterpolationMethod , b0Threshold, stopThreshold, maxIterations=2):
    logger("Baseline Optimized averaging on baselines ... ",prep.Color.PROCESS)
    baseline_grads, baseline_images=image_obj.getBaselines(b0_threshold=b0Threshold)
    out_gradient=default_output_gradient()
    affine=image_obj.getAffineMatrixForNifti()
    static=np.mean(baseline_images,axis=3) #initial direct averaging 
    previous_static=copy.copy(static)
    averaged_image=copy.copy(static)
    moving_images=copy.copy(baseline_images)
    x,y,z,g = moving_images.shape

    succeeded=False
    for i in range(maxIterations):
        temp_images=[]
        logger("Iteration {}/{}".format(i+1,maxIterations),prep.Color.PROCESS)
        for gidx in range(g):

            ## rigid 3d registration to the averaged image
            logger("Rigid registration {}/{}".format(gidx+1,g),prep.Color.PROCESS)
            moving=moving_images[:,:,:,gidx]
            transformed, out_affine = rigid_3d(static,moving,affine,affine,sampling_prop=0.1)
            temp_images.append(transformed)
  
        moving_images=np.moveaxis(np.array(temp_images),0,-1) ## replace existing moving images with registered images
        static=np.mean(moving_images,axis=3) ## re average transformed moving images
        error=computeErrorRatio(static,previous_static)
               
        if error < stopThreshold:
            succeeded=True
            averaged_image=static 
            logger("Error ratio : {:.4f} < tolerance level {:.4f}".format(error,stopThreshold),prep.Color.OK)
            break
        else:
            logger("Error ratio : {:.4f} > tolerance level {:.4f}".format(error,stopThreshold),prep.Color.INFO)
        previous_static=copy.copy(static)

    if not succeeded:
        logger("[WARNING] BaselineOptimized averaging failed, so direct averaging will be performed",prep.Color.WARNING)
        return direct_average(image_obj, averageInterpolationMethod, b0Threshold,stopThreshold)

    output={"averaged_baseline" : averaged_image,
            "output_baseline_gradient" : out_gradient, 
            "baseline_gradients" : baseline_grads}
    logger("Baseline Optimized averaging DONE",prep.Color.OK)
    return output

def computeErrorRatio(static,moving):

    sq_diff=np.mean((static-moving)**2)
    ratio = np.sqrt(sq_diff)/np.mean(moving)
    return ratio

def bspline_optimized_average(image_obj, averageInterpolationMethod , b0Threshold, stopThreshold):
    prep.not_implemented()
    logger("BSplineOptimized averaging on baselines ... ",prep.Color.PROCESS)
    baseline_grads, baseline_images=image_obj.getBaselines(b0_threshold=b0Threshold)
    out_gradient=default_output_gradient()
    output={"averaged_baseline" : None ,
            "output_baseline_gradient" : out_gradient, 
            "baseline_gradients" : baseline_grads}
    logger("BSplineOptimized averaging DONE",prep.Color.OK)
    return output

def decompose_affine_matrix(mat4d): ## in case 
    scale, shear, angles, trans, persp =dipy.align.streamlinear.decompose_matrix(mat4d)
    angles_in_deg=list(map(lambda x : float(np.rad2deg(x)), angles))
    res={"scale":scale.tolist(),
         "shear":list(map(float,shear)),
         "angles":angles,
         "angles_in_degree":angles_in_deg,
         "translations":trans.tolist(),
         "perspective":persp.tolist()}
    return res

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


class BASELINE_Average(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

        
    def process(self,*args,**kwargs): ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        opts=args[0]
        self.baseline_threshold=opts['baseline_threshold']

        output=None
        output_image_path=Path(self.output_dir)
        if self.image.image_type.lower()=='nrrd':
            output_image_path=str(output_image_path.joinpath('output.nrrd'))
        elif self.image.image_type.lower()=='nifti':
            output_image_path=str(output_image_path.joinpath('output.nii.gz'))
        
        output_filename=Path(self.computation_dir).joinpath('computations.yml')
        if output_filename.exists() and not self.options['recompute']: 
            ## pass recomputation
            logger("Computing ommited",prep.Color.INFO)
            pass
        else: ##computed parameters doesn't exist or recompute is true
            ## compute or recompute
            logger("Computing ... ",prep.Color.PROCESS)
            #self.image.deleteGradientsByOriginalIndex([49, 65, 97, 129, 145])#([0, 17, 49, 65, 97, 129, 145]) For test
            new_image, excluded_original_indexes=baseline_average(self.image, opt=None ,
                                                      averageInterpolationMethod=self.protocol['averageInterpolationMethod'],
                                                      averageMethod=self.protocol['averageMethod'],
                                                      b0Threshold=self.baseline_threshold,
                                                      stopThreshold=self.protocol['stopThreshold'],
                                                      maxIterations=self.protocol['maxIterations'])

        if new_image is not None:
            self.image=new_image
            ### if image is changed, next module should load the file. So set image_object to None and write the file instead
        self.image.setSpaceDirection(target_space=self.getSourceImageInformation()['space'])
        self.writeImage(output_image_path,dest_type=self.image.image_type)

        ### output preparation
        self.result['output']['excluded_gradients_original_indexes']=excluded_original_indexes
        self.result['output']['success']=True
        #raise Exception("User Exception for development ...")
        return self.result

    