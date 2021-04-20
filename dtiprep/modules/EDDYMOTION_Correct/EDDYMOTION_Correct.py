

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml
from pathlib import Path 

logger=dtiprep.logger.write

class EDDYMOTION_Correct(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(EDDYMOTION_Correct)
    def checkDependency(self,environment): #use information in template, check if this module can be processed
        # FSL should be ready before execution
        if self.name in environment:
            try:
                fslpath=Path(environment[self.name]['fsl_path'])
                fsl_exists=fslpath.exists()
                if fsl_exists:
                    return True, None 
                else:
                    return False, "FSL Path doesn't exist : {}".format(str(fslpath))
            except Exception as e:
                return False, "Exception in finding FSL6 : {}".format(str(e))
        else:
            return False, "Can't locate FSL" #test

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self): ## self.result_history, self.result , self.template , self.protocol 
        super().process()
        inputParams=self.getPreviousResult()['output']
        gradient_indexes_to_remove=[]
        logger("NOT IMPLEMENTED YET",dtiprep.Color.ERROR)
        ## results
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        return self.result