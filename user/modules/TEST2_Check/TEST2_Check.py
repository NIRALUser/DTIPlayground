
from dtiprep.modules import DTIPrepModule
import dtiprep
import TEST_Check.dummy as dummy #user defined module in the module
import TEST_Check.arisu as ari
from TEST_Check.tmod import arisu  as tmodari
import sys

logger=dtiprep.logger.write
#logger=print



class TEST2_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(TEST2_Check)

    def process(self):
        super().process()

        logger("USER defined pipeline function : {}".format(self))
