
import dtiprep
import yaml
from dtiprep.modules import DTIPrepModule
logger=dtiprep.logger.write

class DOMINANTDIRECTION_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DOMINANTDIRECTION_Check)

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