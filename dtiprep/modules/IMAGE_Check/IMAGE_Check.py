
import dtiprep
import yaml
from dtiprep.modules import DTIPrepModule
logger=dtiprep.logger.write

class IMAGE_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(IMAGE_Check)

    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
        return self.protocol
    def process(self): ## self.results_history, self.results 
        super().process()
        print("Child method begins")
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))

        self.result['output']['success']=True
        return self.result