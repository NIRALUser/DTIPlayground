#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

import dtiplayground.dmri.preprocessing as prep

import yaml,traceback 
import BASELINE_Average.computations as computations 
import numpy as np
import time
from pathlib import Path
import os
import markdown

logger=prep.logger.write


class BASELINE_Average(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
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
            new_image, excluded_original_indexes=computations.baseline_average(self.image, opt=None ,
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

    