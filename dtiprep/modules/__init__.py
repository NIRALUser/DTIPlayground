
# from .. import io as dwiio
import yaml, inspect
from pathlib import Path 
import dtiprep 
logger=dtiprep.logger.write

class DTIPrepModule:
    def __init__(self,*args, **kwargs):
        self.name=self.__class__.__name__
        self.image=None
        self.protocols=None
        self.result=None

        ##
        self.template=None

        ## loading template file (yml)
        self.loadTemplate()

    def loadTemplate(self):
        modulepath=inspect.getfile(self.__class__)
        template_filename=Path(modulepath).parent.joinpath(self.name+".yml")
        self.template=yaml.safe_load(open(template_filename,'r'))

    def setImage(self, image ):
        self.image=image

    def setProtocols(self,protocols):
        self.protocols=protocols


    def getProtocols(self):
        return self.protocols[self.name]
    
    def process(self,*args,**kwargs):
        logger("-----------------------------------------------")
        logger("Processing : {}".format(self.__class__.__name__))
        logger("-----------------------------------------------")
        #logger("{}".format(yaml.dump(self.getProtocols())))
        logger(">>> Template")
        logger(yaml.dump(self.template))


    def getResult(self):
        return self.result