

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml

logger=dtiprep.logger.write

class DENOISING_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DENOISING_Check)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self): ## self.result_history, self.result , self.template , self.protocol 
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger("NOT IMPLEMENTED YET",dtiprep.Color.ERROR)

        self.result['output']['success']=True
        return self.result
