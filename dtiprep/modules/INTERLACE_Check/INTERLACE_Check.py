#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml,traceback 
import INTERLACE_Check.computations as computations 

import numpy as np
import time
from pathlib import Path
logger=dtiprep.logger.write

class INTERLACE_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(INTERLACE_Check)
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
        return self.protocol
    def process(self): ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        #logger(yaml.dump(inputParams))

        ### Computation 
        output=None
        output_filename=Path(self.computation_dir).joinpath('computations.yml')
        if output_filename.exists():
            logger("There exists the result of interlacing computations",dtiprep.Color.INFO)
            output=yaml.safe_load(open(output_filename,'r'))
            logger("Computed parameters are loaded : {}".format(str(output_filename)),dtiprep.Color.OK)
        else: 
            ### actual computation for interlacing correlation and motions
            logger("Computing interlace correlations and motions ...",dtiprep.Color.PROCESS)
            output=computations.interlace_compute(self.image)
            yaml.dump(output,open(output_filename,'w'))
        ### Check for QC
        logger("Checking bad gradients ...",dtiprep.Color.PROCESS)
        gradient_indexes_to_remove , interlacing_results= computations.interlace_check( self.image,output,
                                                         correlationDeviationBaseline=self.protocol['correlationDeviationBaseline'],
                                                         correlationDeviationGradient=self.protocol['correlationDeviationGradient'],
                                                         correlationThresholdBaseline=self.protocol['correlationThresholdBaseline'],
                                                         correlationThresholdGradient=self.protocol['correlationThresholdGradient'],
                                                         rotationThreshold=self.protocol['rotationThreshold'],
                                                         translationThreshold=self.protocol['translationThreshold'])

        logger("\nExcluding gradients : {}".format(gradient_indexes_to_remove),dtiprep.Color.WARNING)
        check_filename=Path(self.computation_dir).joinpath('checks.yml')
        yaml.dump(interlacing_results,open(check_filename,'w'))
        logger("Check file saved : {}".format(str(check_filename)),dtiprep.Color.OK)
        ### output preparation
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        #raise Exception("User Exception for development ...")
        return self.result

    @dtiprep.measure_time
    def postProcess(self,result_obj):
        super().postProcess(result_obj)
