
from dtiprep.modules import DTIPrepModule
import dtiprep,yaml
import DIFFUSION_Check.testmodule as tm 

logger=dtiprep.logger.write 

class DIFFUSION_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DIFFUSION_Check)

    def process(self): ## self.results_history, self.results 
        super().process()
        print("Child method begins")
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))

        self.result['output']['success']=True
        return self.result

        return self.result
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
