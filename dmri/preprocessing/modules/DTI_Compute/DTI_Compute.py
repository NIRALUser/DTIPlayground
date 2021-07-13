

  
import dmri.preprocessing as prep

import yaml

class DTI_Compute(prep.modules.DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DTI_Compute)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## self.result_history, self.result , self.template , self.protocol 
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger("NOT IMPLEMENTED YET",prep.Color.ERROR)

        self.result['output']['success']=True
        return self.result