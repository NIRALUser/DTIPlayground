

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml

logger=dtiprep.logger.write

class SLICE_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(SLICE_Check)
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
        self.result['output']['parameters']={
            "GradientNum": None, #int
            "SliceNum" : None,  #int
            "Correlation" : None    #float
        }

        return self.result