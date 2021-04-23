#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

from prep.modules import DTIPrepModule
import prep,yaml,traceback 
import BASELINE_Average.computations as computations 

import numpy as np
import time
from pathlib import Path
logger=prep.logger.write


class BASELINE_Average(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(BASELINE_Average)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

        
    def process(self): ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']

        output=None
        output_image_path=str(Path(self.output_dir).joinpath('output.nrrd'))
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
                                                      b0Threshold=self.protocol['b0Threshold'],
                                                      stopThreshold=self.protocol['stopThreshold'],
                                                      maxIterations=self.protocol['maxIterations'])

        if new_image is not None:
            self.image=new_image
            ### if image is changed, next module should load the file. So set image_object to None and write the file instead
        self.writeImage(output_image_path)

        ### output preparation
        self.result['output']['excluded_gradients_original_indexes']=excluded_original_indexes
        self.result['output']['success']=True
        #raise Exception("User Exception for development ...")
        return self.result

    # @prep.measure_time
    # def postProcess(self,result_obj): ## this runs after self.process in run() method, so not need to be added inside of process method. This is due to the re-run and overwriting option
    #     self.result=result_obj
    #     self.result['input']=self.getPreviousResult()['output']
    #     self.image.deleteGradientsByOriginalIndex(self.result['output']['excluded_gradients_original_indexes'])
    #     logger("Excluded gradient indexes (original index) : {}"
    #         .format(self.result['output']['excluded_gradients_original_indexes']),prep.Color.WARNING)

    #     ### re-implementation due to image loading for the next module
    #     gradient_filename=str(Path(self.output_dir).joinpath('gradients.yml'))
    #     image_information_filename=str(Path(self.output_dir).joinpath('image_information.yml'))
        
    #     if  Path(self.output_dir).joinpath('result.yml').exists() and not self.options['overwrite']:
    #         self.result['output']['image_object']=None 
    #         self.image.gradients=yaml.safe_load(open(gradient_filename,'r'))
    #         self.image.information=yaml.safe_load(open(image_information_filename,'r'))
    #     else:
    #         self.result['output']['image_object']=id(self.image)
    #     ### re-implementation ends

    #     self.result['output']['success']=True
    #     outstr=yaml.dump(self.result)
    #     with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
    #         yaml.dump(self.result,f)
    #     self.image.dumpGradients(gradient_filename)
    #     self.image.dumpInformation(image_information_filename)

    #     ## output gradients summary
    #     b_grads, _ =self.image.getBaselines()
    #     grad_summary = self.image.gradientSummary()
    #     logger("Remaining Gradients summary - Num.Gradients: {}, Num.Baselines: {}"
    #         .format(grad_summary['number_of_gradients'],
    #                 grad_summary['number_of_baselines']),prep.Color.INFO)

    #     logger("Remaining baselines",prep.Color.INFO)
    #     for g in b_grads:
    #         logger("[Gradient.idx {:03d} Original.idx {:03d}] Gradient Dir {} B-Value {:.1f}"
    #             .format(g['index'],g['original_index'],g['gradient'],g['b_value']),prep.Color.INFO)

