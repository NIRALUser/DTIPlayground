

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml

logger=dtiprep.logger.write

class INTERLACE_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(INTERLACE_Check)
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
    def process(self): ## self.results_history, self.results 
        super().process()
        print("Child method begins")
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))

        self.result['output']['success']=True
        return self.result