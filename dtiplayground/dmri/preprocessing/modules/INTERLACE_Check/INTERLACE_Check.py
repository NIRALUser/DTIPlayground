#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

  
import dtiplayground.dmri.preprocessing as prep

import numpy as np
import time,traceback ,yaml
from pathlib import Path
import os
import markdown
import INTERLACE_Check.computations as computations 

logger=prep.logger.write

class INTERLACE_Check(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        spacing=float(np.sum(np.abs(image_obj.information['space_directions']))/3.0)
        self.protocol['translationThreshold']=spacing
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        #logger(yaml.dump(inputParams))
        ### Computation 
        output=None
        output_filename=Path(self.computation_dir).joinpath('computations.yml')
        if output_filename.exists() and not self.options['recompute']:
            logger("Recompute : {}".format(self.options['recompute']),prep.Color.INFO)
            logger("There exists the result of interlacing computations",prep.Color.INFO)
            output=yaml.safe_load(open(output_filename,'r'))
            logger("Computed parameters are loaded : {}".format(str(output_filename)),prep.Color.OK)
        else: 
            ### actual computation for interlacing correlation and motions
            logger("Computing interlace correlations and motions ...",prep.Color.PROCESS)
            output=computations.interlace_compute(self.image)
            yaml.dump(output,open(output_filename,'w'))
        ### Check for QC
        logger("Checking bad gradients ...",prep.Color.PROCESS)
        gradient_indexes_to_remove , interlacing_results= computations.interlace_check( self.image,output,
                                                         correlationDeviationBaseline=self.protocol['correlationDeviationBaseline'],
                                                         correlationDeviationGradient=self.protocol['correlationDeviationGradient'],
                                                         correlationThresholdBaseline=self.protocol['correlationThresholdBaseline'],
                                                         correlationThresholdGradient=self.protocol['correlationThresholdGradient'],
                                                         rotationThreshold=self.protocol['rotationThreshold'],
                                                         translationThreshold=self.protocol['translationThreshold'])

        #logger("\nExcluded gradients : {}".format(gradient_indexes_to_remove),prep.Color.WARNING)
        check_filename=Path(self.computation_dir).joinpath('checks.yml')
        yaml.dump(interlacing_results,open(check_filename,'w'))
        logger("Check file saved : {}".format(str(check_filename)),prep.Color.OK)
        ### output preparation
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        #raise Exception("User Exception for development ...")
        return self.result

    def makeReport(self):
        super().makeReport()        
        
        with open(os.path.abspath(self.output_dir) + '/report.md', 'a') as f:
            if len(self.result['output']['excluded_gradients_original_indexes']) == 0:
                f.write('* 0 excluded gradients\n')
            else:
                excluded_gradients = str(len(self.result['output']['excluded_gradients_original_indexes'])) + " excluded gradient(s): "
                for gradient_index in self.result['output']['excluded_gradients_original_indexes'][:-1]:
                    excluded_gradients = excluded_gradients + str(gradient_index) + ", "
                excluded_gradients += str(self.result['output']['excluded_gradients_original_indexes'][-1])
                f.write('* ' + excluded_gradients + '\n')
        
        self.result['report']['csv_data']['excluded_gradients'] = self.result['output']['excluded_gradients_original_indexes']
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)