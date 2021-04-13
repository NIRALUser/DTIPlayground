import yaml,sys,traceback
import dtiprep
import dtiprep.io 
import dtiprep.modules 
from pathlib import Path
import pkgutil



logger=dtiprep.logger.write

def _load_protocol(filename):
    return yaml.safe_load(open(filename,'r'))

def _generate_default_protocol(image_obj : dtiprep.io.DWI):
    pass

def _load_modules(user_module_paths=[]):
    modules=_load_default_modules()
    usermodules= _load_modules_from_paths(user_module_paths)
    modules.update(usermodules)
    return modules

def _load_default_modules(): # user_modules list of paths of user modules
    modules={}
    default_module_paths=[Path(__file__).parent.joinpath('modules')]
    return _load_modules_from_paths(default_module_paths)

def _load_modules_from_paths(user_module_paths: list):
    modules={}
    mods=[]
    for pth in map(lambda x: str(x),user_module_paths):  ## path objects to string array
        logger(">> Loading modules from {} ".format(str(pth)))
        sys.path.insert(0, pth)
        pkgs_info=list(pkgutil.walk_packages([pth]))
        for p in pkgs_info:
            if len(p.name.split('.'))==1:
                logger("Loading module : {}".format(p.name))
            mods.append(p.module_finder.find_module(p.name).load_module(p.name))
        mod_filtered=list(filter(lambda x: len(x.__name__.split('.'))==2 and x.__name__.split('.')[0]==x.__name__.split('.')[1] ,mods))
        for md in mod_filtered:
            fn=Path(md.__file__)
            template_path= fn.parent.joinpath(fn.stem+'.yml')
            template=yaml.safe_load(open(template_path,'r'))
            modules[md.__name__.split('.')[0]]={
                                "module" : md,
                                "path" : md.__file__,
                                "template" : template,
                                "template_path" : template_path
                                } 
    return modules 


class Protocols:
    def __init__(self,*args,**kwargs):
        self.image_path=None
        self.protocol_filename=None
        self.rawdata=None
        self.protocols=None
        self.pipeline=None
        self.io=None
        self.version=None

        #Execution variables
        self.template_filename=Path(__file__).parent.joinpath("templates/protocol_template.yml")
        self.modules=None

        #output
        self.results=None

    def setImagePath(self, image_path): # this nullify previous results
        self.image_path=str(image_path)
        self.results=[{"output":{"image_path": self.image_path}}]

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

    def addPipeline(self,modulename,index=-1,default_protocol=False):
        if modulename not in self.pipeline:
            self.pipeline.insert(index, modulename)
            if default_protocol:
                self.makeDefaultProtocolForModule(modulename)

    def makeDefaultProtocolForModule(self, module_name):
        if module_name in self.modules.keys():
            self.protocols[module_name]=getattr(self.modules[module_name]['module'],module_name)().generateDefaultProtocol()

    def makeDefaultProtocols(self,user_module_paths=[],template=None):
        if template==None:
            template=yaml.safe_load(open(self.template_filename,'r'))

        ### generate default protocols
        self.protocols={}
        self.io={}
        self.version=template['version']
        for k,elm in template['options']['io'].items():
            self.io[k]=elm['default_value']
        self.pipeline=template['options']['execution']['pipeline']['default_value']
        self.modules=_load_modules(user_module_paths=user_module_paths)
        for mod_name,mod in self.modules.items():
            self.makeDefaultProtocolForModule(mod_name)


    def runPipeline(self,user_module_paths=[]):

        ## load modules and template file
        try:
            if self.getImagePath() is None: raise Exception("Image path is not set")
            if self.protocols is not None:
                if self.modules is None:
                    self.modules=_load_modules(user_module_paths=user_module_paths)
                for idx,p in enumerate(self.pipeline):
                    logger("-----------------------------------------------")
                    logger("Processing [{0}/{1}] : {2}".format(idx+1,len(self.pipeline),p))
                    logger("-----------------------------------------------")
        
                    m=getattr(self.modules[p]['module'], p)()
                    m.setProtocol(self.protocols)
                    m.initialize(self.results)
                    success=m.run()
                    if success : logger("Success ")
                    else: raise Exception("Process failed in {}".format(p))
                    self.results=m.getResult()
                return self.results
            else:
                raise Exception("Protocols are not set")
                return None
        except Exception as e:
            logger("Exception occurred in runPipeline {}".format(str(e)))
            traceback.print_exc()
            return None

