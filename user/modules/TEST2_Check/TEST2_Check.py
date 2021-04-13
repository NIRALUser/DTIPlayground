
from dtiprep.modules import DTIPrepModule
import dtiprep,yaml
import TEST_Check.dummy as dummy #user defined module in the module
import TEST_Check.arisu as ari
from TEST_Check.tmod import arisu  as tmodari
import sys

logger=dtiprep.logger.write

class TEST2_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(TEST2_Check)
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
    def process(self):
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))
        logger("USER defined pipeline function : {}".format(self))
        self.result['output']['success']=True
        return self.result
