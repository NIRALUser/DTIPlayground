
from dtiprep.modules import DTIPrepModule
import dtiprep,yaml
import DIFFUSION_Check.testmodule as tm 

logger=dtiprep.logger.write 

class DIFFUSION_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(DIFFUSION_Check)

    def process(self): ### variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        print("Child method begins")
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))

        self.result['output']['success']=True
        self.result['output']['image_object']=id(self.image)
        return self.result

    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
        return self.protocol
