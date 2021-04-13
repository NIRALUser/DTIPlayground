

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml

logger=dtiprep.logger.write

class BASELINE_Average(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(BASELINE_Average)

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


