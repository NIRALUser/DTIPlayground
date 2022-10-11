  
import dtiplayground.dmri.preprocessing as prep
import yaml, os
from pathlib import Path

import dtiplayground.dmri.common.tools as tools 


class IDENTITY_Process(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol
        
    @prep.measure_time
    def process(self,*args,**kwargs): ## variables : self.global_variables, self.softwares, self.output_dir, self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.baseline_threshold=protocol_options['baseline_threshold']

        # << TODOS>>
        logger(yaml.dump(self.image.information))
        self.result['output']['success']=True

        return self.result

