
# from .. import io as dwiio
import yaml
import dtiprep 
logger=dtiprep.logger.write

class DTIPrepModule:
    def __init__(self,*args, **kwargs):
        self.name=self.__class__.__name__
        self.image=None
        self.protocols=None
        self.result=None


    def setImage(self, image: dtiprep.io.DWI):
        self.image=image

    def setProtocols(self,protocols):
        self.protocols=protocols


    def getProtocols(self):
        return self.protocols[self.name]
    
    def process(self,*args,**kwargs):
        logger("-----------------------------------------------")
        logger("Processing : {}".format(self.__class__.__name__))
        logger("-----------------------------------------------")
        logger("{}".format(yaml.dump(self.getProtocols())))


    def getResult(self):
        return self.result