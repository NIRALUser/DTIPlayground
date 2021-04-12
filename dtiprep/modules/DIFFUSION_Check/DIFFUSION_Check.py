
from dtiprep.modules import DTIPrepModule
import dtiprep
import DIFFUSION_Check.testmodule as tm 

logger=dtiprep.logger.write 

class DIFFUSION_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DIFFUSION_Check)

    def process(self):
        super().process()
        logger("User defined module : {}".format(tm.mult(300,500)))