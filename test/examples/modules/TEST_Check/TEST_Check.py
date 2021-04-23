

import dmri.prep as prep

import sys,yaml

import TEST_Check.dummy as dummy #user defined module in the module
import TEST_Check.arisu as ari
import TEST_Check.tmod.arisu as tmodari


logger=prep.logger.write

class TEST_Check(prep.modules.DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(TEST_Check)
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol
    def process(self): ## self.result_history, self.result , self.template , self.protocol 
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))

        
        logger("USER defined pipeline function : {}".format(self))
        logger(str(dummy.add(54,100)))
        logger(str(ari.div(54,100)))
        logger(str(tmodari.div(100,2)))

        self.result['output']['success']=True
        return self.result
