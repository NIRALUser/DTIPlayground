#!python

import shutil
import os 
from pathlib import Path
import traceback
import yaml
import re

from dtiplayground.config import INFO as info
import dtiplayground
import dtiplayground.dmri.common as common
import dtiplayground.dmri.common.module as module
from dtiplayground.dmri.common.appbase import AppBase

import dtiplayground.dmri.preprocessing as preprocessing
logger=common.logger.write 
color= common.Color

class DMRIPrepApp(AppBase):

    ######### Mandatory Implementations Begins
    def __init__(self, config_root, app_name = 'dmriprep', *args, **kwargs): 
        super().__init__(config_root,app_name,*args,**kwargs)

    def getAppInfoImpl(self):
        return self.app

    def initializeImpl(self, options):

        home_dir = Path(self.app['application_dir'])

        user_module_dir=home_dir.parent.joinpath('modules/{}'.format(self.app['application'])).absolute()
        user_module_dir.mkdir(parents=True,exist_ok=True)
        user_tools_param_dir=home_dir.joinpath('parameters').absolute()
        user_tools_param_dir.mkdir(parents=True,exist_ok=True)

        template_filename=home_dir.joinpath("protocol_template.yml").absolute()
        source_template_path=Path(preprocessing.__file__).parent.joinpath("templates/protocol_template.yml")
        protocol_template=yaml.safe_load(open(source_template_path,'r'))
        config_filename=home_dir.joinpath("config.yml")
        environment_filename=home_dir.joinpath("environment.yml")
        ## make configuration file (config.yml)
        config={"user_module_directories": [str(user_module_dir)],"protocol_template_path" : 'protocol_template.yml'}
        yaml.dump(protocol_template,open(template_filename,'w'))
        yaml.dump(config,open(config_filename,'w'))
        logger("Config file written to : {}".format(str(config_filename)),color.INFO)
        ## copy default software path
        software_filename=home_dir.joinpath('software_paths.yml')
        self._update_software_paths(self.globalvars)
        logger("Software path file is written to : {}".format(str(software_filename)),color.INFO)
        system_module_paths = [Path(dtiplayground.__file__).resolve().parent.joinpath('dmri/preprocessing/modules')]
        modules=module.load_modules(system_module_paths = system_module_paths, user_module_paths=config['user_module_directories'])
        # The below line spells "environment" wrong
        environment=module.generate_module_envionrment(modules,str(home_dir))
        yaml.dump(environment,open(environment_filename,'w'))
        logger("Environment file written to : {}".format(str(environment_filename)),color.INFO) 
        return True

    #######################
    #### default command
    #######################

    def runImpl(self,_options):
        return self.runQC(_options)
    ######### Mandatory Implementations Ends###############################################
   
    #######################
    #### commands
    #######################

    def runQC(self,_options):

        @self.after_initialized
        def _run(_options):
            _options.setdefault('output_file_base', None)
            _options.setdefault('baseline_threshold', 10)
            _options.setdefault('execution_id', common.get_uuid())
            _options.setdefault('output_format', None)
            _options.setdefault('global_variables',{})
            _options.setdefault('no_output_image', False)

            options={
                "config_dir" : self.app['application_dir'],
                "input_image_paths" : _options['input_image_paths'],
                "protocol_path" : _options['protocol_path'],
                "output_dir" : _options['output_dir'],
                "default_protocols":_options['default_protocols'],
                "num_threads":_options['num_threads'],
                "execution_id":_options['execution_id'],
                "baseline_threshold" : _options['baseline_threshold'],
                "output_format" : _options['output_format'],
                "output_file_base" : _options['output_file_base'],
                "no_output_image" : _options['no_output_image'],
                "global_variables" : _options['global_variables']
            }

            if options['output_format'] is not None:
                options['output_format']=options['output_format'].lower()
            ## load config file and run pipeline
            config,environment = self._load_configurations()
            template_path=Path(options['config_dir']).joinpath(config['protocol_template_path'])
            template=yaml.safe_load(open(template_path,'r'))
            proto=preprocessing.protocols.Protocols(options['config_dir'], global_vars=options['global_variables'])
            proto.loadImages(options['input_image_paths'],b0_threshold=options['baseline_threshold'])
            if options['output_dir'] is None:
                raise Exception("Output directory is missing")
            else:
                proto.setOutputDirectory(options['output_dir'])
            if options['default_protocols'] is not None:
                if len(options['default_protocols'])==0:
                    options['default_protocols']=None
                proto.makeDefaultProtocols(options['default_protocols'],template=template,options=options)
            elif options['protocol_path'] is not None:
                proto.loadProtocols(options["protocol_path"])
            else :
                proto.makeDefaultProtocols(options['default_protocols'],template=template,options=options)
            if options['num_threads'] is not None:
                proto.setNumThreads(options['num_threads'])
            Path(options['output_dir']).mkdir(parents=True,exist_ok=True)
            logfilename=str(Path(options['output_dir']).joinpath('log.txt').absolute())
            common.logger.setLogfile(logfilename)  
            logger("\r----------------------------------- QC Begins ----------------------------------------\n")
            res=proto.runPipeline(options=options)
            logger("\r----------------------------------- QC Done ----------------------------------------\n")
            return res 

        return _run(_options)

    def makeProtocols(self, _options):

        @self.after_initialized
        def make_protocol(options):
            options.setdefault('baseline_threshold', 10)
            options.setdefault('output_format', None)
            options.setdefault('global_variables',{})
            options.setdefault('no_output_image', False)
            options={
                "config_dir" : self.app['application_dir'],
                "input_image_paths" : options['input_images'],
                "module_list": options['module_list'],
                "output_path" : options['output'],
                "baseline_threshold" : options['b0_threshold'],
                "output_format" : options['output_format'],
                "no_output_image" : options['no_output_image'],
                "global_variables" : options['global_variables']
            }
            ## load config file
            config,environment = self._load_configurations()
            template_path=Path(options['config_dir']).joinpath(config['protocol_template_path'])
            template=yaml.safe_load(open(template_path,'r'))
            proto=preprocessing.protocols.Protocols(options['config_dir'],global_vars=options['global_variables'])
            proto.loadImages(options['input_image_paths'],b0_threshold=options['baseline_threshold'])
            if options['module_list'] is not None and  len(options['module_list'])==0:
                    options['module_list']=None
            proto.makeDefaultProtocols(options['module_list'],template=template,options=options)
            outstr=yaml.dump(proto.getProtocols())
            # print(outstr)
            if options['output_path'] is not None:
                open(options['output_path'],'w').write(outstr)
                logger("Protocol file has been writte to : {}".format(options['output_path']),color.OK)

            return True 
        return make_protocol(_options)

    def remove_module(self,_options):

        @self.after_initialized
        def _remove_module(args):
            home_dir=Path(self.app['application_dir'])
            module_name = args['name']
            config_filename=home_dir.joinpath("config.yml")
            environment_filename=home_dir.joinpath("environment.yml")
            config=yaml.safe_load(open(config_filename,'r'))
            
            module_root_dir = Path(config['user_module_directories'][0])
            module_dir = module_root_dir.joinpath(module_name)
            if module_dir.exists():
                logger("Removing the module : {} at {}".format(module_name, module_dir.__str__()), color.PROCESS)
                shutil.rmtree(module_dir)
                logger("Module {} has been successfully removed".format(module_name), color.OK)
            else:
                logger("There is no such module in {}".format(module_root_dir.__str__()), color.ERROR)

            return True

        return _remove_module(_options)

    def add_module(self,_options):
        @self.after_initialized
        def _add_module(args):
            home_dir=Path(self.app['application_dir'])
            module_name = args['name']
            base_module_name = args['base_module']
            config_filename=home_dir.joinpath("config.yml")
            environment_filename=home_dir.joinpath("environment.yml")
            config=yaml.safe_load(open(config_filename,'r'))
            system_module_root_dir = Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/preprocessing/modules")
            user_module_root_dir = Path(config['user_module_directories'][0])
            module_dir = user_module_root_dir.joinpath(module_name)

            if self._check_if_module_exists(module_name):
                logger("Module {} exists in {} or {}".format(module_name, user_module_root_dir.__str__(), system_module_root_dir.__str__()), color.ERROR)
                return False

            if base_module_name is None: ### NEW module 
                logger("Making directories and files ... ", color.PROCESS)
                module_dir.mkdir(parents=True,exist_ok=False)
                module_template_fn =Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/preprocessing/templates/module_template.py")
                module_template = open(module_template_fn,'r').read()
                module_data_fn = module_template_fn.parent.joinpath('module_template.yml')
                module_readme_fn = module_template_fn.parent.joinpath('module_template.md')
                module_data = open(module_data_fn,'r').read()
                module_readme = open(module_readme_fn,'r').read()
                ### replacing variable
                regex=r"@MODULENAME@"
                module_py = re.sub(regex,module_name,module_template,0)
                module_yml = re.sub(regex,module_name,module_data,0)
                module_md = re.sub(regex,module_name, module_readme, 0)

                ### write down files into user module dir

                init_fn = module_dir.joinpath("__init__.py")
                with open(init_fn,'w') as f:
                    f.write("")
                out_py_fn = module_dir.joinpath("{}.py".format(module_name))
                with open(out_py_fn,'w') as f:
                    f.write(module_py)
                out_yml_fn = module_dir.joinpath("{}.yml".format(module_name))
                with open(out_yml_fn,'w') as f:
                    f.write(module_yml)
                out_md_fn = module_dir.joinpath("README.md")
                with open(out_md_fn,'w') as f:
                    f.write(module_md)
                
                logger("Module is added, please implement the module {} in {}".format(module_name, module_dir.__str__()), color.OK)
            else: ### copy base module to new one (new name)
                base_module_dir= None
                if system_module_root_dir.joinpath(base_module_name).exists():
                    base_module_dir = system_module_root_dir.joinpath(base_module_name)
                    logger("Module {} found in system module directory".format(base_module_name),color.OK)
                elif user_module_root_dir.joinpath(base_module_name).exists():
                    base_module_dir = user_module_root_dir.joinpath(base_module_name)
                    logger("Module {} found in user module directory".format(base_module_name),color.OK)
                else:
                    logger("Module {} NOT found in either system or user module directory".format(base_module_name),color.ERROR)
                    return False

                logger("Generating {} at {}".format(module_name, module_dir.__str__()),color.PROCESS)
                shutil.copytree(base_module_dir, module_dir)
                if module_dir.joinpath('__pycache__').exists():
                    shutil.rmtree(module_dir.joinpath('__pycache__'))
                flist = list(filter(lambda x: '__pycache__' not in x.__str__(), module_dir.glob("**/*")))
                for fn in flist: ### changing module name in contents (may not perfect)
                    out_content=None
                    with open(fn,'r') as f:
                        ### change class name to new module name
                        content = f.read()
                        out_content = content.replace(base_module_name, module_name)
                        out_content = out_content.replace(base_module_name.replace("_"," "), module_name.replace("_"," "))
                    with open(fn,'w') as f:
                        f.write(out_content)

                    nameparts = fn.name.split('.')
                    if nameparts[0] == base_module_name:
                        nameparts[0] = module_name
                    out_fn = ".".join(nameparts)
                    fn.rename(module_dir.joinpath(out_fn))
                logger("Module {} cloned from {} has been generated at {}".format(module_name, base_module_name, module_dir.__str__()),color.OK)
                if args['edit']:
                    command=["vi",module_dir.joinpath("{}.py".format(module_name))]
                    subprocess.run(command)
                return True

        return _add_module(_options)

    #############        
    ### utilities
    ##############

    def _check_if_module_exists(self,module_name):
        home_dir=Path(self.app['application_dir'])

        config_filename=home_dir.joinpath("config.yml")
        environment_filename=home_dir.joinpath("environment.yml")
        config=yaml.safe_load(open(config_filename,'r'))
        
        system_module_root_dir = Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/preprocessing/modules")
        user_module_root_dir = Path(config['user_module_directories'][0])
        if system_module_root_dir.joinpath(module_name).exists():
            return True
        if user_module_root_dir.joinpath(module_name).exists():
            return True
        return False 

    def _load_configurations(self):
        ## reparametrization
        home_dir=Path(self.app['application_dir'])
        ## Function begins
        config_filename=home_dir.joinpath("config.yml")
        environment_filename=home_dir.joinpath("environment.yml")
        config=yaml.safe_load(open(config_filename,'r'))
        environment=yaml.safe_load(open(environment_filename,'r'))
        return config,environment


#### working (API functions)

    def getProtocolTemplateConfig(self):
        # config_dir = self.getConfigDirectory();
        import dtiplayground.dmri.preprocessing.templates as t
        ptc_fn = Path(t.__file__).parent.joinpath('protocol_template.yml')
        # ptc_fn = config_dir.joinpath('protocol_template.yml')
        with open(ptc_fn,'r') as f:
            ptc = yaml.safe_load(f)

        ptc['ui'] = {
            'execution': self.convertTemplate(ptc['options']['io'])
        } 
        return ptc

    def getModuleList(self,extra_dirs = []):
        res = {
            'system': self.getSystemModuleList(),
            'user': self.getUserModuleList(extra_dirs)
        }
        return res

    def getSystemModuleList(self):
        system_dir = Path(self.getSystemModulePath())    
        sp = [x for x in system_dir.glob('*')]
        sp = list(map(lambda x: {'name': x.name, 'path': str(x)},filter(lambda x: x.is_dir() and x.joinpath('__init__.py').exists() , sp)))
        sp.sort(key=lambda x: x['name'])
        return sp

    def getUserModuleList(self,extra_dirs=[]):
        user_module_dir = Path(self.getUserModuleDirectory())
        res = []
        for d in ([user_module_dir] + extra_dirs):      
            up = [x for x in Path(d).glob('*')]
            up = list(map(lambda x: {'name': x.name, 'path': str(x)},filter(lambda x: x.is_dir() and x.joinpath('__init__.py').exists() , up)))
            res = res + up
        res.sort(key=lambda x: x['name'])
        return res

    def getTemplate(self, name, extra_dirs=[]):

        system_dir = Path(self.getSystemModulePath())
        user_module_dir = Path(self.getUserModuleDirectory())
        filepath = system_dir.joinpath(name).joinpath("{}.yml".format(name))
        if not filepath.exists():
            for d in ([user_module_dir] + extra_dirs):
                filepath = d.joinpath(name).joinpath("{}.yml".format(name))
                if filepath.exists(): break
        if not filepath.exists() : raise Exception("There is no such module : {}".format(name))
        with open(filepath,'r') as f:
            original=yaml.safe_load(f)
        ui = self.convertTemplate(original['protocol'])

        protoTemplate = self.getProtocolTemplateConfig()
        
        options = self.convertTemplate(protoTemplate['options']['execution']['options'])
        res = {
                'original': original,
                'ui': {
                    'name' : original['name'],
                    'description': original['description'],
                    'protocol' : self.parseDefaultValues(ui),
                    'options' : options
                 }
        }
        return res


    def setEnvironmentVars(self):
        os.environ['CONFIG_DIR'] = self.getConfigDirectory().__str__()

    def parseDefaultValues(self,template):
        self.setEnvironmentVars()
        for idx,v in enumerate(template):
            print(v['name'])
            if 'filepath' in v['type'] or 'dirpath' in v['type']:
                if v['default_value'] is not None:
                    try:
                        template[idx]['default_value'] = os.path.expandvars(v['default_value'])
                    except:
                        pass

        return template
    def convertTemplate(self, template):
        new_proto = []
        for k,v in template.items():
            tmp = v
            tmp.update({'name': k})
            new_proto.append(tmp)
        return new_proto


    def getConfigDirectory(self):
        return self.app['application_dir']

    def getUserModuleDirectory(self):
        return Path(self.app['config_dir']).joinpath('modules/dmriprep').__str__()

    def getSystemModulePath(self):
        import dtiplayground.dmri.preprocessing.modules as modules
        return Path(modules.__file__).parent.__str__()