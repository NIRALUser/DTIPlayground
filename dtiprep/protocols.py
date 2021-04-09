import yaml
import dtiprep
import dtiprep.io as dwiio
import dtiprep.modules as modules
from pathlib import Path
import importlib
import traceback

logger=dtiprep.logger.write

def _load_protocol(filename):
    return yaml.safe_load(open(filename,'r'))

def _generate_default_protocol(image_obj : dwiio.DWI):
    pass

def _load_modules(pipeline : list):
    modules={}
    for m in pipeline:
        try:

            mod=importlib.import_module("dtiprep.modules."+m+"."+m)
            modules[m]={
                'module': mod,
                'path' : mod.__file__,
                'template' : None,
                'template_path' : None}
            templatepath=Path(modules[m]['path']).parent.joinpath(m+".yml")
            if templatepath.exists():
                template=yaml.safe_load(open(templatepath,'r'))
                modules[m]['template']=template
                modules[m]['template_path']=str(templatepath)

        except Exception as e:
            logger("Exception in loading modules in the pipeline: {}".format(str(e)))
            traceback.print_exc()
            return False 

    #print(yaml.dump(modules))
    return modules 


class Protocols:
    def __init__(self,*args,**kwargs):
        self.image=None
        self.protocol_filename=None
        self.rawdata=None
        self.protocols=None
        self.pipeline=[]


        #Execution variables
    def setImage(self, image:dwiio.DWI):
        self.image=image

    def loadProtocols(self,filename):
        try:
            self.rawdata=_load_protocol(filename)
            self.pipeline=self.rawdata['pipeline']
            self.protocols=self.rawdata['protocols']
            self.io=self.rawdata['io']
            self.protocol_filename=filename
            return True
        except Exception as e:
            logger("Exception occurred : {}".format(str(e)))
            return False

    def makeDefaultProtocols(self, template):
        pass

    def runPipeline(self):

        ## load modules and template file
        modules=_load_modules(self.pipeline)
        for p in self.pipeline:
            m=getattr(modules[p]['module'], p)()
            m.setProtocols(self.protocols)
            m.process()


