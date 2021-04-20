#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml,traceback 
import BASELINE_Average.computations as computations 

import numpy as np
import time
from pathlib import Path
logger=dtiprep.logger.write


class BASELINE_Average(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(BASELINE_Average)

    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
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
            logger("Computing ommited",dtiprep.Color.INFO)
            pass
        else: ##computed parameters doesn't exist or recompute is true
            ## compute or recompute
            logger("Computing ... ",dtiprep.Color.PROCESS)
            computations.baseline_average(self.image, opt=None ,
                                          averageInterpolationMethod=self.protocol['averageInterpolationMethod'],
                                          averageMethod='averageInterpolationMethod',
                                          b0Threshold=self.protocol['averageInterpolationMethod'],
                                          stopThreshold=self.protocol['averageInterpolationMethod'])

        gradient_indexes_to_remove = []
        logger("\nExcluded gradients : {}".format(gradient_indexes_to_remove),dtiprep.Color.WARNING)

        ### if image is changed, next module should load the file. So set image_object to None and write the file instead
        
        self.writeImage(output_image_path)
        ### output preparation

        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        #raise Exception("User Exception for development ...")
        return self.result

    @dtiprep.measure_time
    def postProcess(self,result_obj): ## this runs after self.process in run() method, so not need to be added inside of process method. This is due to the re-run and overwriting option
        self.result=result_obj
        self.result['input']=self.getPreviousResult()['output']
        self.image.deleteGradientsByOriginalIndex(self.result['output']['excluded_gradients_original_indexes'])

        ### re-implementation due to image loading for the next module
        if  Path(self.output_dir).joinpath('result.yml').exists() and not self.options['overwrite']:
            self.result['output']['image_object']=None 
        else:
            self.result['output']['image_object']=id(self.image)
        ### re-implementation ends

        self.result['output']['success']=True
        outstr=yaml.dump(self.result)
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)
        self.image.dumpGradients(str(Path(self.output_dir).joinpath('gradients.yml')))
        self.image.dumpInformation(str(Path(self.output_dir).joinpath('image_information.yml')))

        ## output gradients summary
        b_grads, _ =self.image.getBaselines()
        grad_summary = self.image.gradientSummary()
        logger("Remaining Gradients summary - Num.Gradients: {}, Num.Baselines: {}"
            .format(grad_summary['number_of_gradients'],
                    grad_summary['number_of_baselines']),dtiprep.Color.INFO)

        logger("Remaining baselines",dtiprep.Color.INFO)
        for g in b_grads:
            logger("[Index {:03d} Org.Index {:03d}] Gradient Dir{} B-Value {:.1f}"
                .format(g['index'],g['original_index'],g['gradient'],g['b_value']),dtiprep.Color.OK)

