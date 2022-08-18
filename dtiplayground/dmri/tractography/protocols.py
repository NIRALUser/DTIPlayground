from dtiplayground.dmri.common.pipeline import *

class Protocols(Pipeline):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
    def loadModules(self,pipeline:list,user_module_paths:list, **options):
        mod_names=[x for x in pipeline]
        system_module_paths = [Path(__file__).resolve().parent.joinpath('modules')]
        modules=module._load_modules(system_module_paths = system_module_paths, user_module_paths=user_module_paths,module_names=mod_names, **options)
        modules=module.check_module_validity(modules, self.environment, self.config_dir)
        self.modules=modules

        return self.modules 
