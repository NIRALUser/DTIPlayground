
import dmri.preprocessing as prep
import yaml

logger=prep.logger.write

class DIFFUSION_Check(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ### variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger("NOT IMPLEMENTED YET",prep.Color.ERROR)


        return self.result


