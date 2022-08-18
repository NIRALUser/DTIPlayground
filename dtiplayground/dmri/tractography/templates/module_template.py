import dtiplayground.dmri.tractography as base
import dtiplayground.dmri.common as common

import yaml
logger=common.logger.write

class @MODULENAME@(base.modules.DTITractographyModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>


        self.result['output']['success']=True
        return self.result
