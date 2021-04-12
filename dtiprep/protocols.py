import yaml,sys,traceback
import dtiprep
import dtiprep.io 
import dtiprep.modules 
from pathlib import Path
# import importlib
# import importlib.util
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


def _load_modules_from_paths(user_module_paths: list):
    modules={}
    mods=[]
    logger("Loading modules ... ")
    for pth in map(lambda x: str(x),user_module_paths):  ## path objects to string array
        logger("---------------------------------------------------------")
        logger("From {} ,".format(str(pth)))
        logger("---------------------------------------------------------")
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

# def _load_modules_from_paths_deprecated(user_module_paths: list):
#     modules={}
#     for p in user_module_paths:
#         files=list(Path(p).glob('**/*.py'))
#         modulefiles=[]
#         for fn in files:
#             file_path = fn
#             if '__init__.py' in str(fn):
#                 module_name = ".".join(fn.relative_to(p).parts[1:-1])
#             else:
#                 module_name = ".".join(fn.relative_to(p).parts[1:-1]+(fn.stem,))
#             if fn.stem == fn.parent.name:
#                 modulefiles.append(fn)

#             else:
#                 logger("Loading a submodule : {}".format(module_name))
#                 spec = importlib.util.spec_from_file_location(module_name, file_path)
#                 module = importlib.util.module_from_spec(spec)
#                 sys.modules[module_name] = module
#                 spec.loader.exec_module(module)

#         for fn in modulefiles:
#             file_path = fn
#             module_name = fn.stem
#             logger("Loading a module : {}".format(module_name))
#             spec = importlib.util.spec_from_file_location(module_name, file_path)
#             module = importlib.util.module_from_spec(spec)
#             sys.modules[module_name] = module
#             spec.loader.exec_module(module)
#             template_path= fn.parent.joinpath(fn.stem+'.yml')
#             template=yaml.safe_load(open(template_path,'r'))
#             modules[module_name]={
#                 'module' : module,
#                 'path' : module.__file__,
#                 'template' :template,
#                 'template_path' : template_path
#                 }
#     return modules 

def _load_default_modules(): # user_modules list of paths of user modules
    modules={}
    default_module_paths=[Path(__file__).parent.joinpath('modules')]
    return _load_modules_from_paths(default_module_paths)


class Protocols:
    def __init__(self,*args,**kwargs):
        self.image=None
        self.protocol_filename=None
        self.rawdata=None
        self.protocols=None
        self.pipeline=None
        self.io=None
        self.version=None

        #Execution variables
        self.template_filename=Path(__file__).parent.joinpath("templates/protocol_template.yml")
        self.modules=None

    def setImage(self, image:dtiprep.io.DWI):
        self.image=image

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
            self.protocols[mod_name]={}
            for k,v in mod['template']['protocol'].items():
                self.protocols[mod_name][k]=v['default_value']


    def runPipeline(self,user_module_paths=[]):

        ## load modules and template file
        self.modules=_load_modules(user_module_paths=user_module_paths)
        for p in self.pipeline:
            m=getattr(self.modules[p]['module'], p)()
            m.setProtocols(self.protocols)
            m.process()


