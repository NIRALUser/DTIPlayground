
import dmri.prep as prep

import yaml
import sys

import TEST_Check.dummy as dummy #user defined module in the module
import TEST_Check.arisu as ari
from TEST_Check.tmod import arisu  as tmodari

logger=prep.logger.write

class TEST2_Check(prep.modules.DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(TEST2_Check)
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol
    def process(self): ## self.result_history, self.result , self.template , self.protocol 
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))
        logger("USER defined pipeline function : {}".format(self))
        self.result['output']['success']=True
        return self.result
