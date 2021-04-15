import yaml,sys,traceback
import dtiprep
import dtiprep.io 
from dtiprep.modules import _load_modules
import dtiprep.modules 
from pathlib import Path
import pkgutil

logger=dtiprep.logger.write

def _load_protocol(filename):
    return yaml.safe_load(open(filename,'r'))

class Protocols:
    def __init__(self,modules=None,*args,**kwargs):
        self.image_path=None
        self.protocol_filename=None
        self.rawdata=None
        self.protocols=None
        self.pipeline=None
        self.io=None
        self.version=None

        #Execution variables
        self.template_filename=Path(__file__).parent.joinpath("templates/protocol_template.yml")
        self.modules=modules

        #output
        self.results_history=None

    def setImagePath(self, image_path): # this nullify previous results
        self.image_path=str(image_path)
        self.results_history=[{"output":{"image_path": self.image_path}}]

    def getImagePath(self):
        return self.image_path

    def writeProtocols(self,filename):
        self.rawdata={
            'version' : self.version,
            'io' : self.io,
            'pipeline': self.pipeline,
            'protocols':self.protocols
        }
        yaml.dump(self.rawdata,open(filename,'w'))

    def loadProtocols(self,filename):
        try:
            self.rawdata=_load_protocol(filename)
            self.version=self.rawdata['version']
            self.pipeline=self.rawdata['pipeline']
            self.protocols=self.rawdata['protocols']
            self.io=self.rawdata['io']
            self.protocol_filename=filename
            return True
        except Exception as e:
            logger("Exception occurred : {}".format(str(e)))
            return False

    def setModules(self,modules):
        self.modules=modules 

    def addPipeline(self,modulename,index=-1,default_protocol=False):
        if modulename not in self.pipeline:
            self.pipeline.insert(index, modulename)
            if default_protocol:
                self.makeDefaultProtocolForModule(modulename)

    def makeDefaultProtocolForModule(self, module_name):
        if module_name in self.modules.keys():
            self.protocols[module_name]=getattr(self.modules[module_name]['module'],module_name)().generateDefaultProtocol()

    def makeDefaultProtocols(self,pipeline=None,template=None):
        if template==None:
            template=yaml.safe_load(open(self.template_filename,'r'))

        ### generate default protocols
        self.protocols={}
        self.io={}
        self.version=template['version']
        for k,elm in template['options']['io'].items():
            self.io[k]=elm['default_value']
        if pipeline is not None:
            self.pipeline=pipeline 
        else:
            self.pipeline=template['options']['execution']['pipeline']['default_value']
        for mod_name in self.pipeline:
            self.makeDefaultProtocolForModule(mod_name)



    def runPipeline(self):

        ## load modules and template file
        try:
            if self.getImagePath() is None: raise Exception("Image path is not set")
            if self.protocols is not None:
                for idx,p in enumerate(self.pipeline):
                    logger("-----------------------------------------------")
                    logger("Processing [{0}/{1}] : {2}".format(idx+1,len(self.pipeline),p))
                    logger("-----------------------------------------------")
        
                    m=getattr(self.modules[p]['module'], p)()
                    m.setProtocol(self.protocols)
                    m.initialize(self.results_history)
                    success=m.run()
                    if success : logger("Success ")
                    else: raise Exception("Process failed in {}".format(p))
                    self.results_history=m.getResultHistory()
                return self.results_history
            else:
                raise Exception("Protocols are not set")
                return None
        except Exception as e:
            logger("Exception occurred in runPipeline {}".format(str(e)))
            traceback.print_exc()
            return None

