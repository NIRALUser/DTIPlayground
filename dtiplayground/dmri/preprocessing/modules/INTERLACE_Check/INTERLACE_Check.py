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

    def postProcess(self,result_obj,opts):
        super().postProcess(result_obj, opts)        
        if self.result['input']['image_path']:
            input_image = self.result['input']['image_path']
            for number in self.result['input']['image_information']['sizes']:
                if number not in self.result['input']['image_information']['image_size']:
                    self.result['report']['csv_data']['original_number_of_gradients'] = number
        elif type(self.result_history[0]["output"]) == dict: #single input
            input_image = self.result_history[0]["output"]["image_path"]
        else:
            input_image = None
            input_directory = self.result["input"]["output_directory"]
            while input_image == None:
                previous_result = yaml.safe_load(open(str(Path(self.output_dir).parent.parent) + "/" + input_directory + "/result.yml", 'r'))
                input_image = previous_result["input"]["image_path"]
                if "output_directory" in previous_result["input"]:
                    input_directory = previous_result["input"]["output_directory"]

        with open(os.path.abspath(self.output_dir) + '/report.md', 'bw+') as f:
            f.write('## {}\n'.format("Module: " + self.result['module_name']).encode('utf-8'))
            f.write('### {}\n'.format("input image: " + str(os.path.abspath(input_image))).encode('utf-8'))
            if len(self.result['output']['excluded_gradients_original_indexes']) == 0:
                f.write('* {}\n'.format('0 excluded gradients').encode('utf-8'))
            else:
                excluded_gradients = str(len(self.result['output']['excluded_gradients_original_indexes'])) + " excluded gradient(s): "
                for gradient_index in self.result['output']['excluded_gradients_original_indexes'][:-1]:
                    excluded_gradients = excluded_gradients + str(gradient_index) + ", "
                excluded_gradients += str(self.result['output']['excluded_gradients_original_indexes'][-1])
                f.write('* {}\n'.format(excluded_gradients).encode('utf-8'))
            f.seek(0)
            markdown.markdownFromFile(input=f, output=os.path.abspath(self.output_dir) + '/report.html')
        
        self.result['report']['csv_data']['image_name'] = str(os.path.abspath(input_image))
        self.result['report']['csv_data']['excluded_gradients'] = self.result['output']['excluded_gradients_original_indexes']
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)