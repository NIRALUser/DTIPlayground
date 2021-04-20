

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml
from pathlib import Path 

logger=dtiprep.logger.write

class EDDYMOTION_Correct(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(EDDYMOTION_Correct)
    def checkDependency(self,environment): #use information in template, check if this module can be processed
        # FSL should be ready before execution

        return True, "Can't locate FSL"
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
        return self.protocol
    def process(self): ## self.result_history, self.result , self.template , self.protocol 
        super().process()
        inputParams=self.getPreviousResult()['output']
        gradient_indexes_to_remove=[]

        ## results
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        return self.result