
from dtiprep.modules import DTIPrepModule
import dtiprep,yaml

logger=dtiprep.logger.write

class SUSCEPTIBILITY_Correct(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(SUSCEPTIBILITY_Correct)
    def checkDependency(self): #use information in template, check if this module can be processed
        # FSL should be ready before execution

        return True #test
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
        return self.protocol
    def process(self): ## self.result_history, self.result , self.template , self.protocol 
        super().process()
        print("Child method begins")
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))

        self.result['output']['success']=True
        return self.result