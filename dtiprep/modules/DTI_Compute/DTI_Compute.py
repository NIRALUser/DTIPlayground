

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml

logger=dtiprep.logger.write

class DTI_Compute(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DTI_Compute)
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