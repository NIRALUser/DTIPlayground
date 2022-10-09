#!python

import shutil
import os 
import importlib
from pathlib import Path
import argparse,yaml
from argparse import RawTextHelpFormatter
import traceback,time,copy,yaml,sys,uuid
import sys
import subprocess
import re
sys.path.append(Path(__file__).resolve().parent.parent.__str__()) ## this line is for development
import dtiplayground
import dtiplayground.dmri.common
import dtiplayground.dmri.common.module
from dtiplayground.config import INFO as info

logger=dtiplayground.dmri.common.logger.write 
color= dtiplayground.dmri.common.Color

### unit functions

def resolve_softwarepaths(spathobj, globalvars):
    if 'dtiplayground-tools' in globalvars:
        p = Path(globalvars['dtiplayground-tools']['path'])
        if p.exists():
            os.environ['DTIPLAYGROUNDTOOLS'] = p.resolve().__str__()

    if 'fsl' in globalvars:
        p = Path(globalvars['fsl']['path'])
        if p.exists():
            os.environ['FSL'] = p.resolve().__str__()

    if  'DTIPLAYGROUNDTOOLS' not in os.environ:
        os.environ['DTIPLAYGROUNDTOOLS']=os.path.expandvars("$HOME/.niral/dtiplayground-tools")
        tooldir=os.environ['DTIPLAYGROUNDTOOLS']
        if Path(tooldir).exists():
            logger("DTI Playground tools directory found at {}".format(tooldir), color.OK)
        else:
            logger("DTI Playground tools directory is set to {}".format(tooldir), color.WARNING)
            logger("DTI Playground tools directory not found, please install toolkits or specify software paths manually", color.WARNING)
    else:
        tooldir=os.environ['DTIPLAYGROUNDTOOLS']
        if Path(os.environ['DTIPLAYGROUNDTOOLS']).exists():
            
            logger("DTI playground tools are found in {}".format(tooldir),color.OK)
        else:
            logger("DTI playground tools are not found in {}".format(tooldir),color.ERROR)
    if 'FSL' not in os.environ:
        logger("FSL directory is not set in environment variable FSL",color.WARNING)
        logger("Make sure FSL directory is set in the software paths",color.WARNING)
    else:
        if Path(os.environ['FSL']).exists():
            logger("FSL directory is found at {}".format(os.environ['FSL']),color.OK)
        else:
            logger("FSL directory is set in environment variable FSL, but doesn't exist",color.WARNING)
    
    sp = spathobj['softwares']
    for k,v in sp.items():
        resolved_path = os.path.expandvars(v['path'])
        sp[k]['path'] = resolved_path
    spathobj['softwares'] = sp
    return spathobj

def initialize_logger(args):
    ## default log setting
    dtiplayground.dmri.common.logger.setLogfile(args.log)
    dtiplayground.dmri.common.logger.setTimestamp(not args.no_log_timestamp)
    dtiplayground.dmri.common.logger.setVerbosity(not args.no_verbosity)

def check_initialized(args):
    home_dir=Path(args.config_dir)
    if home_dir.exists():
        config_file=home_dir.joinpath('config.yml')
        environment_file=home_dir.joinpath('environment.yml')
        if not config_file.exists():  return False
        if not environment_file.exists(): return False
        return True
    else: 
        return False

def load_configurations(config_dir:str):
    ## reparametrization
    home_dir=Path(config_dir)
    ## Function begins
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    config=yaml.safe_load(open(config_filename,'r'))
    environment=yaml.safe_load(open(environment_filename,'r'))
    return config,environment

### decorators
def after_initialized(func): #decorator for other functions other than command_init
    def wrapper(args):
        home_dir=Path(args.config_dir)
        if home_dir.exists() and home_dir.joinpath('config.yml').exists() and home_dir.joinpath('environment.yml').exists():
            config_file=home_dir.joinpath('config.yml')
            environment_file=home_dir.joinpath('environment.yml')
            initialize_logger(args)
            return func(args)
        else: 
            # raise Exception("Not initialized, please run init command at the first use")
            logger("Configuration directory is not found or some files are missing, commencing initialization ...",dtiplayground.dmri.common.Color.WARNING)
            command_init(args)
            config_file=home_dir.joinpath('config.yml')
            environment_file=home_dir.joinpath('environment.yml')
            initialize_logger(args)
            return func(args)
    return wrapper

def log_off(func):
    def wrapper(*args,**kwargs):
        dtiplayground.dmri.common.logger.setVerbosity(False)
        res=func(*args,**kwargs)
        dtiplayground.dmri.common.logger.setVerbosity(True)
        return res 
    return wrapper

def search_fsl(lookupdirs=None):
    fslpath=None
    if 'FSLDIR' in os.environ:
        fslpath1=Path(os.environ['FSLDIR'])
        if fslpath1.exists():
            fslpath=fslpath1
    elif 'FSL' in os.environ:
        fslpath1=Path(os.environ['FSL'])
        if fslpath1.exists():
            fslpath=fslpath1
    else:
        fslpath=None

    if fslpath is not None:
        if fslpath.exists():
            logger("FSL directory found : {}".format(fslpath.resolve().__str__()), color.OK)
    else:
        logger("FSL directory not found for environment variable FSLDIR/FSL", color.WARNING)
        search_dirs=[]
        if lookupdirs is None or len(lookupdirs) < 1:
            search_dir = input("Specify the directory of installed FSL [/] :")
            if not search_dir: 
                search_dirs = ['/']
            else:
                search_dirs = [search_dir]
        else:
            logger("Looking up in the directories : {}".format(lookupdirs))
            search_dirs=lookupdirs

        for sdir in search_dirs:
            should_break=False
            search_dir = Path(sdir)
            candidates = search_dir.glob("**/bin/fsl")
            logger("Searching FSL in {}".format(search_dir.__str__()),color.PROCESS)
            for c in candidates:
                
                c = Path(c)
                if c.__str__().lower().endswith('/bin/fsl'):
                    fslpath = c.resolve().parent.parent
                    version=open(fslpath.joinpath('etc/fslversion'),'r').read().strip()
                    logger("Found : {}, Version: {}".format(fslpath.__str__(), version), color.OK)
                    confirm = input("Is this FSL you want? [Y/n]")
                    if not confirm: confirm = 'y'
                    if confirm.lower() == 'y':
                        should_break=True
                        break
            if should_break:
                break

    if fslpath.joinpath('etc/fslversion').exists():
        info = {
            "name" : "fsl",
            "version" : open(fslpath.joinpath('etc/fslversion'),'r').read().strip()
        }
        res = {
            "fsl" : {
                "path" : fslpath.resolve().__str__(),
                "info" : info
            }
        }
        return res
    else:
        return None

def search_dtiplayground_tools(lookupdirs=None):   
    target_path=None
    search_dirs=[]
    if lookupdirs is None or len(lookupdirs) < 1:
        search_dir = input("Specify the directory of installed DTI Playground tools [/] :")
        if not search_dir: 
            search_dirs = ['/']
        else:
            search_dirs = [search_dir]
    else:
        search_dirs=lookupdirs
    for sdir in search_dirs:
        should_break=False
        search_dir = Path(sdir)
        candidates = search_dir.glob("**/info.yml")
        info={}
        logger("Searching DTIPlaygroundTools in {}".format(search_dir.__str__()),color.PROCESS)
        for c in candidates:
            c = Path(c)
            info = yaml.safe_load(open(c,'r'))
            if 'name' in info:
                if info['name']=='dtiplayground-tools':
                    target_path = c.resolve().parent
                    version=info['version']
                    logger("Found : {}, Version: {}".format(target_path.__str__(), version), color.OK)
                    confirm = input("Is this DTI Playground Tools you want? [Y/n]")
                    if not confirm: confirm = 'y'
                    if confirm.lower() == 'y':
                        should_break=True
                        break
        if should_break: break

    if target_path is not None:
        res = {
            "dtiplayground-tools" : {
                "path" : target_path.resolve().__str__(),
                "info" : info
            }
        }
        return res
    else:
        return None
    
def update_software_paths(args, globalvars):
    home_dir=Path(args.config_dir)
    software_info_path=Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/common/data/software_paths.yml")
    software_paths=yaml.safe_load(open(software_info_path,'r'))
    software_paths=resolve_softwarepaths(software_paths, globalvars)
    software_filename=home_dir.joinpath('software_paths.yml')
    yaml.dump(software_paths, open(software_filename,'w'))

### command functions

def command_find_tools(args):
    ## reparametrization
    home_dir=Path(args.config_dir)

    ## Function begins
    lookup_dirs = args.lookup_dirs
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    software_filename=home_dir.joinpath('software_paths.yml')
    software_info_path=Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/common/data/software_paths.yml")
    globalvars_fn = home_dir.parent.joinpath('global_variables.yml')
    globalvars={}
    if globalvars_fn.exists():
        globalvars.update(yaml.safe_load(open(globalvars_fn,'r')))

    ## load default software paths

    software_paths=yaml.safe_load(open(software_info_path,'r'))
    result = False
    ## search FSL
    fsl_info = search_fsl(lookupdirs=lookup_dirs)
    if fsl_info is not None:
        globalvars.update(fsl_info) 
        logger("Selected FSL directory is : {}".format(fsl_info['fsl']['path']),color.INFO)
    else:
        logger("FSL was not found",color.ERROR)
    ## search DTI Playground Tools
    
    dpt_info = search_dtiplayground_tools(lookupdirs=lookup_dirs)
    if dpt_info is not None:
        globalvars.update(dpt_info)
        logger("Selected DTI Playground tools directory is : {}".format(dpt_info['dtiplayground-tools']['path']),color.INFO)
    else:
        logger("DTI Playground tools were not found",color.ERROR)
    ## update software paths
    logger("Updating global_variables.yml", color.PROCESS)
    yaml.dump(globalvars, open(globalvars_fn,'w'))
    logger("Updating software paths",color.PROCESS)
    update_software_paths(args, globalvars)
    logger("Updates Completed",color.OK)
    result= True
    return result

def command_install_tools(args):
    ## reparametrization
    home_dir=Path(args.config_dir).resolve()
    home_dir.parent.mkdir(parents=True,exist_ok=True)
    # globalvars_fn = Path(os.path.expandvars("$HOME/.niral-dti/global_variables.yml"))
    globalvars_fn = home_dir.parent.joinpath('global_variables.yml')
    Path(globalvars_fn).parent.mkdir(parents=True,exist_ok=True)
    globalvars = {}
    if globalvars_fn.exists():
        globalvars = yaml.safe_load(open(globalvars_fn,'r'))

    rootdir = Path(os.path.expandvars(args.output_dir)).resolve()
    rootdir.mkdir(parents=True,exist_ok=True)
    tempdir = rootdir.joinpath('temp-dtiplayground-tools')
    outputdir = rootdir.joinpath('dtiplayground-tools')
    fsldir = rootdir.joinpath('FSL')
    clean_install = args.clean_install
    leave_files_after_installation = args.no_remove
    no_fsl = args.no_fsl
    install_only = args.install_only
    build=args.build
    ### Clean install preparations
    if clean_install:
        logger("Removing temporary, existing packages (dtiplayground-tools only) directories ...")
        if tempdir.exists():
            shutil.rmtree(tempdir)
        if outputdir.exists():
            shutil.rmtree(outputdir)
        logger("Removing files finished")

    ### FSL
    if not no_fsl and not fsldir.exists():
        fslinstaller_fn=Path(__file__).resolve().parent.joinpath('fslinstaller.py')
        command=['/usr/bin/python', fslinstaller_fn ,'-d',fsldir.resolve().__str__()] ### python2 is needed
        subprocess.run(command)
        info = {
            'name' : 'fsl',
            'version' : open(fsldir.joinpath('etc/fslversion'),'r').read().strip()
        }
        globalvars['fsl']={
            'path' : fsldir.resolve().__str__(),
            'info' : info
        }
        yaml.dump(info, open(fsldir.joinpath('info.yml'),'w'))
    else:
        if fsldir.exists():
            info = {
                'name': 'fsl',
                'version' : open(fsldir.joinpath('etc/fslversion'),'r').read().strip()
            }
            yaml.dump(info, open(fsldir.joinpath('info.yml'),'w'))
            globalvars['fsl']={
                'path' : fsldir.resolve().__str__(),
                'info' : info
            }            

    ### DTI playground tools (build with docker, centos7 for now)
    tempdir.mkdir(parents=True,exist_ok=True)
    os.chdir(tempdir)
    srcdir = tempdir.joinpath('dtiplaygroundtools')
    info={}
    if not outputdir.exists():
        if build:
            if not srcdir.exists():
                logger("Fetching source code ...")
                fetch_dtiplaygroundtools = ["git","clone","https://github.com/niraluser/dtiplaygroundtools.git"]
                subprocess.run(fetch_dtiplaygroundtools)
                logger("Source codes downloaded")
            
            os.chdir(srcdir.joinpath('dockerfiles'))
            build_command = ['./build.sh']
            logger("Building software packages ... ")
            subprocess.run(build_command)
            tar_filename = srcdir.joinpath('dist/dtiplayground-tools.tar.gz')
            untar_command = ['tar','xvfz',tar_filename.resolve().__str__(), '-C', rootdir.resolve().__str__()]
            logger("Installing softwares to the output directory {}".format(outputdir.resolve().__str__()))
            subprocess.run(untar_command)
            ### read version info
            info_fn = outputdir.joinpath('info.yml')
            if info_fn.exists():
                info = yaml.safe_load(open(info_fn,'r'))
        else: # prebuilt package (default)
            tar_filename = outputdir.joinpath('dtiplayground-tools.tar.gz')
            if not tar_filename.exists():
                remote_package = "https://github.com/NIRALUser/DTIPlaygroundTools/releases/download/v0.0.1/dtiplayground-tools.tar.gz"
                fetch_package = ['wget',remote_package,'-P',outputdir.resolve().__str__()]
                subprocess.run(fetch_package)
            untar_command = ['tar','xvfz',tar_filename.resolve().__str__(), '-C', rootdir.resolve().__str__()]
            logger("Installing softwares to the output directory {}".format(outputdir.resolve().__str__()))
            subprocess.run(untar_command)
            info_fn = outputdir.joinpath('info.yml')
            if info_fn.exists():
                info = yaml.safe_load(open(info_fn,'r'))
            logger("Removing temporary files ...")
            tar_filename.unlink()

    else:
        info = yaml.safe_load(open(outputdir.joinpath('info.yml'),'r'))
    globalvars['dtiplayground-tools']={
        'path' : outputdir.resolve().__str__(),
        'info' : info
    }

    if not leave_files_after_installation:
        logger("Removing temporary files ...")
        shutil.rmtree(tempdir)
        logger("Removing temporary files finished")

    logger("Saving tool information to {}".format(globalvars_fn.__str__()))
    yaml.dump(globalvars, open(globalvars_fn,'w'))
    if home_dir.joinpath('software_paths').exists() and not install_only:
        update_software_paths(args, globalvars)
    logger("Installation completed")
    return True


def command_init(args):
    ## reparametrization
    home_dir=Path(args.config_dir)

    ## Function begins
    home_dir.mkdir(parents=True,exist_ok=True)
    tools_dir = None
    if args.tools_dir is not None:
        tools_dir = Path(args.tools_dir)

    user_module_dir=home_dir.parent.joinpath('modules/dmrifiberprofile').absolute()
    user_module_dir.mkdir(parents=True,exist_ok=True)
    user_tools_param_dir=home_dir.joinpath('parameters').absolute()
    user_tools_param_dir.mkdir(parents=True,exist_ok=True)
    template_filename=home_dir.joinpath("protocol_template.yml").absolute()
    source_template_path=Path(dtiplayground.dmri.fiberprofile.__file__).parent.joinpath("templates/protocol_template.yml")
    protocol_template=yaml.safe_load(open(source_template_path,'r'))
    globalvars_fn=home_dir.parent.joinpath('global_variables.yml')
    globalvars = {}

    if globalvars_fn.exists():
        globalvars = yaml.safe_load(open(globalvars_fn,'r'))

    if tools_dir is not None:
        if tools_dir.exists():
            dptdir = tools_dir.joinpath('dtiplayground-tools')
            fsldir = tools_dir.joinpath('FSL')
            globalvars.update({
                "dtiplayground-tools" :{
                    "path" : dptdir.resolve().__str__(),
                    "info" : yaml.safe_load(open(dptdir.joinpath('info.yml'),'r'))
                },
                "fsl" : {
                    "path" : fsldir.resolve().__str__(),
                    "info" : {
                        'name' : 'fsl',
                        "verson" : open(fsldir.joinpath('etc/fslversion'),'r').read().strip()
                    }
                }
            })
            yaml.dump(globalvars, open(globalvars_fn,'w'))
        else:
            logger("Couldn't find tool directory {}".format(str(tools_dir)),color.ERROR)
            exit(1)

    initialize_logger(args)
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    ## make configuration file (config.yml)
    config={"user_module_directories": [str(user_module_dir)],"protocol_template_path" : 'protocol_template.yml'}
    yaml.dump(protocol_template,open(template_filename,'w'))
    yaml.dump(config,open(config_filename,'w'))
    logger("Config file written to : {}".format(str(config_filename)),color.INFO)
    ## copy default software path
    software_filename=home_dir.joinpath('software_paths.yml')
    update_software_paths(args, globalvars)
    logger("Software path file is written to : {}".format(str(software_filename)),color.INFO)
    system_module_paths = [Path(dtiplayground.__file__).resolve().parent.joinpath('dmri/fiberprofile/modules')]
    modules=dtiplayground.dmri.common.module.load_modules(system_module_paths = system_module_paths, user_module_paths=config['user_module_directories'])
    environment=dtiplayground.dmri.common.module.generate_module_envionrment(modules,str(home_dir))
    yaml.dump(environment,open(environment_filename,'w'))
    logger("Environment file written to : {}".format(str(environment_filename)),color.INFO)
    logger("Initialized. Local configuration will be stored in {}".format(str(home_dir)),color.OK)
    
    return True


@after_initialized
def command_update(args):
    ## reparametrization
    home_dir=Path(args.config_dir)

    ## Function begins
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")

    ## load config_file
    config=yaml.safe_load(open(config_filename,'r'))
    ## make environment file (environment.yml)
    system_module_paths = [Path(dtiplayground.__file__).resolve().parent.joinpath('dmri/fiberprofile/modules')]
    modules=dtiplayground.dmri.common.module.load_modules(system_module_paths = system_module_paths,user_module_paths=config['user_module_directories'])
    environment=dtiplayground.dmri.common.module.generate_module_envionrment(modules,str(home_dir))
    yaml.dump(environment,open(environment_filename,'w'))
    logger("Environment file written to : {}".format(str(environment_filename)),color.INFO)
    logger("Initialized. Local configuration will be stored in {}".format(str(home_dir)),color.OK)
    return True

def check_if_module_exists(args,module_name):
    home_dir=Path(args.config_dir)
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    config=yaml.safe_load(open(config_filename,'r'))
    module_name = args.name
    system_module_root_dir = Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/fiberprofile/modules")
    user_module_root_dir = Path(config['user_module_directories'][0])
    if system_module_root_dir.joinpath(module_name).exists():
        return True
    if user_module_root_dir.joinpath(module_name).exists():
        return True
    return False 

@after_initialized
def command_add_module(args):
    home_dir=Path(args.config_dir)
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    config=yaml.safe_load(open(config_filename,'r'))
    module_name = args.name
    system_module_root_dir = Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/fiberprofile/modules")
    user_module_root_dir = Path(config['user_module_directories'][0])
    module_dir = user_module_root_dir.joinpath(module_name)
    base_module_name = args.base_module

    if check_if_module_exists(args, module_name):
        logger("Module {} exists in {} or {}".format(module_name, user_module_root_dir.__str__(), system_module_root_dir.__str__()), color.ERROR)
        return False

    if base_module_name is None: ### NEW module 
        logger("Making directories and files ... ", color.PROCESS)
        module_dir.mkdir(parents=True,exist_ok=False)
        module_template_fn =Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/fiberprofile/templates/module_template.py")
        module_template = open(module_template_fn,'r').read()
        module_data_fn = module_template_fn.parent.joinpath('module_template.yml')
        module_data = open(module_data_fn,'r').read()

        ### replacing variable
        regex=r"@MODULENAME@"
        module_py = re.sub(regex,module_name,module_template,0)
        module_yml = re.sub(regex,module_name,module_data,0)
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
        if args.edit:
            command=["vi",module_dir.joinpath("{}.py".format(module_name))]
            subprocess.run(command)
    return True

@after_initialized
def command_remove_module(args):
    home_dir=Path(args.config_dir)
    config_filename=home_dir.joinpath("config.yml")
    environment_filename=home_dir.joinpath("environment.yml")
    config=yaml.safe_load(open(config_filename,'r'))
    module_name = args.name
    module_root_dir = Path(config['user_module_directories'][0])
    module_dir = module_root_dir.joinpath(module_name)
    if module_dir.exists():
        logger("Removing the module : {} at {}".format(module_name, module_dir.__str__()), color.PROCESS)
        shutil.rmtree(module_dir)
        logger("Module {} has been successfully removed".format(module_name), color.OK)
    else:
        logger("There is no such module in {}".format(module_root_dir.__str__()), color.ERROR)

    return True

def parse_global_variables(global_vars: list):
    gv = {}
    if global_vars is not None:
        n_vars = int(len(global_vars)/2)
        for i in range(n_vars):
            gv[global_vars[i*2]]=global_vars[i*2+1]
    return gv

@after_initialized
@log_off
def command_make_protocols(args):
    ## reparametrization
    options={
        "config_dir" : args.config_dir,
        "input_image_paths" : args.input_images,
        "module_list": args.module_list,
        "output_path" : args.output,
        "baseline_threshold" : args.b0_threshold,
        "output_format" : args.output_format,
        "no_output_image" : args.no_output_image,
        "global_variables" : parse_global_variables(args.global_variables)
    }
    if options['output_path'] is not None:
        dtiplayground.dmri.common.logger.setVerbosity(True)
    ## load config file
    config,environment = load_configurations(options['config_dir'])
    template_path=Path(options['config_dir']).joinpath(config['protocol_template_path'])
    template=yaml.safe_load(open(template_path,'r'))
    proto=dtiplayground.dmri.fiberprofile.protocols.Protocols(options['config_dir'],global_vars=options['global_variables'])
    proto.loadImages(options['input_image_paths'],b0_threshold=options['baseline_threshold'])
    if options['module_list'] is not None and  len(options['module_list'])==0:
            options['module_list']=None
    proto.makeDefaultProtocols(options['module_list'],template=template,options=options)
    outstr=yaml.dump(proto.getProtocols())
    # print(outstr)
    if options['output_path'] is not None:
        open(options['output_path'],'w').write(outstr)
        logger("Protocol file has been writte to : {}".format(options['output_path']),color.OK)


@after_initialized
def command_run(args):
    ## reparametrization
    options={
        "config_dir" : args.config_dir,
        "input_image_paths" : args.input_image_list,
        "protocol_path" : args.protocols,
        "output_dir" : args.output_dir,
        "default_protocols":args.default_protocols,
        "num_threads":args.num_threads,
        "execution_id":args.execution_id,
        "baseline_threshold" : args.b0_threshold,
        "output_format" : args.output_format,
        "output_file_base" : args.output_file_base,
        "no_output_image" : args.no_output_image,
        "global_variables" : parse_global_variables(args.global_variables)
    }
    if args.output_format is not None:
        options['output_format']=args.output_format.lower()
    ## load config file and run pipeline
    config,environment = load_configurations(options['config_dir'])
    template_path=Path(options['config_dir']).joinpath(config['protocol_template_path'])
    template=yaml.safe_load(open(template_path,'r'))
    proto=dtiplayground.dmri.fiberprofile.protocols.Protocols(options['config_dir'], global_vars=options['global_variables'])
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
    dtiplayground.dmri.common.logger.setLogfile(logfilename)  
    logger("\r----------------------------------- Fiber profiling Begins ----------------------------------------\n")
    res=proto.runPipeline(options=options)
    logger("\r----------------------------------- Fiber profiling Done ----------------------------------------\n")
    return res 
### Arguments 

def get_args():
    current_dir=Path(__file__).resolve().parent
    # info=yaml.safe_load(open(current_dir.parent.joinpath('dtiplayground/info.json'),'r'))
    version=info['dmrifiberprofile']['version']
    logger("VERSION : {}".format(str(version)))
    config_dir=Path(os.environ.get('HOME')).joinpath('.niral-dti/dmrifiberprofile-'+str(version))
    # ## read template
    module_help_str=None
    if config_dir.exists() and config_dir.joinpath('config.yml').exists() and config_dir.joinpath('environment.yml').exists():
        config,environment = load_configurations(str(config_dir))
        template_path=config_dir.joinpath(config['protocol_template_path'])
        template=yaml.safe_load(open(template_path,'r'))
        available_modules=template['options']['execution']['pipeline']['candidates']
        available_modules_list=["{}".format(x['value'])  for x in available_modules if x['description']!="Not implemented"]
        module_help_str="Avaliable Modules := \n" + " , ".join(available_modules_list)
        # print(module_help_str)
    uid, ts = dtiplayground.dmri.common.get_uuid(), dtiplayground.dmri.common.get_timestamp()

    ### Argument parsers

    parser=argparse.ArgumentParser(prog="dmrifiberprofile",
                                   formatter_class=RawTextHelpFormatter,
                                   description="dmrifiberprofile is a tool that profiles for the fibers.",
                                   epilog="Written by SK Park (sangkyoon_park@med.unc.edu) , Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States, 2022")
    subparsers=parser.add_subparsers(help="Commands")
    
    ## init command
    parser_init=subparsers.add_parser('init',help='Initialize configurations')
    parser_init.set_defaults(func=command_init)

    ## update command
    parser_update=subparsers.add_parser('update',help='Update environment file')
    parser_update.set_defaults(func=command_update)

    ## add new module
    parser_new_module=subparsers.add_parser('add-module', help='Add new module to user module directory')
    parser_new_module.add_argument('name', help="Module name")
    parser_new_module.add_argument('-b','--base-module', help="Fork from an existing module with new name", default=None, required=False)
    parser_new_module.add_argument('-e','--edit', help="Run vi editor after generating module", default=False, action="store_true")
    parser_new_module.set_defaults(func=command_add_module)


    ## remove user module 
    parser_remove_module=subparsers.add_parser('remove-module', help='Remove a user module from user module directory')
    parser_remove_module.add_argument('name', help="Module name")
    parser_remove_module.set_defaults(func=command_remove_module)

    ## software find command
    parser_find_tools=subparsers.add_parser('find-tools',help='Search and update software paths')
    parser_find_tools.add_argument('-l','--lookup-dirs', help='Lookup dir list', type=str, nargs='*',required=False)
    parser_find_tools.set_defaults(func=command_find_tools)

    ## software install command
    parser_install_tools=subparsers.add_parser('install-tools',help='Install DTIPlaygroundTools')
    parser_install_tools.add_argument('-o','--output-dir', help="output directory", default="$HOME/.niral-dti")
    parser_install_tools.add_argument('-c','--clean-install', help="Remove existing files", default=False, action="store_true")
    parser_install_tools.add_argument('-b','--build', help="Build DTIPlaygroundTools", default=False, action="store_true")
    parser_install_tools.add_argument('--no-remove', help="Do not remove source and build files after installation", default=False,action="store_true")
    parser_install_tools.add_argument('--no-fsl', help="Do not install FSL", default=False, action="store_true")
    parser_install_tools.add_argument('--install-only', help="Do not update current software paths", default=False, action="store_true")
    parser_install_tools.set_defaults(func=command_install_tools)

    ## generate-default-protocols
    parser_make_protocols=subparsers.add_parser('make-protocols',help='Generate default protocols',epilog=module_help_str)
    parser_make_protocols.add_argument('-i','--input-images',help='Input image paths',type=str,nargs='+',required=True)
    parser_make_protocols.add_argument('-g','--global-variables',help='Global Variables',type=str,nargs='*',required=False)
    parser_make_protocols.add_argument('-o','--output',help='Output protocol file(*.yml)',type=str)
    parser_make_protocols.add_argument('-d','--module-list',metavar="MODULE",
                                        help='Default protocols with specified list of modules, only works with default protocols. Example : -d DIFFUSION_Check SLICE_Check',
                                        default=None,nargs='*')
    parser_make_protocols.add_argument('-b','--b0-threshold',metavar='BASELINE_THRESHOLD',help='b0 threshold value, default=10',default=10,type=float)
    parser_make_protocols.add_argument('-f','--output-format',metavar='OUTPUT FORMAT',default=None,help='OUTPUT format, if not specified, same format will be used for output (NRRD | NIFTI)',type=str)
    parser_make_protocols.add_argument('--no-output-image',help="No output image file will be generated",default=False,action='store_true')
    parser_make_protocols.set_defaults(func=command_make_protocols)
        

    ## run command
    parser_run=subparsers.add_parser('run',help='Run pipeline',epilog=module_help_str)
    parser_run.add_argument('-i','--input-image-list',help='Input image paths',type=str,nargs='+',required=True)
    parser_run.add_argument('-g','--global-variables',help='Global Variables',type=str,nargs='*',required=False)
    parser_run.add_argument('-o','--output-dir',help="Output directory",type=str,required=True)
    parser_run.add_argument('--output-file-base', help="Output filename base", type=str, required=False)
    parser_run.add_argument('-t','--num-threads',help="Number of threads to use",default=None,type=int,required=False)
    parser_run.add_argument('--no-output-image',help="No output output image file will be generated",default=False,action='store_true')
    parser_run.add_argument('-b','--b0-threshold',metavar='BASELINE_THRESHOLD',help='b0 threshold value, default=10',default=10,type=float)
    parser_run.add_argument('-f','--output-format',metavar='OUTPUT FORMAT',default=None,help='OUTPUT format, if not specified, same format will be used for output  (NRRD | NIFTI)',type=str)
    run_exclusive_group=parser_run.add_mutually_exclusive_group()
    run_exclusive_group.add_argument('-p','--protocols',metavar="PROTOCOLS_FILE" ,help='Protocol file path', type=str)
    run_exclusive_group.add_argument('-d','--default-protocols',metavar="MODULE",help='Use default protocols (optional : sequence of modules, Example : -d DIFFUSION_Check SLICE_Check)',default=None,nargs='*')
    parser_run.set_defaults(func=command_run)

    ## log related
    parser.add_argument('--config-dir',help='Configuration directory',default=str(config_dir))
    parser.add_argument('--log',help='log file',default=str(config_dir.joinpath('log.txt')))
    # parser.add_argument('--system-log-dir',help='System log directory',default='/BAND/USERS/skp78-dti/system-logs',type=str)
    parser.add_argument('--execution-id',help='execution id',default=uid,type=str)
    parser.add_argument('--no-log-timestamp',help='Remove timestamp in the log', default=False, action="store_true")
    parser.add_argument('--no-verbosity',help='Do not show any logs in the terminal', default=False, action="store_true")
    parser.add_argument('-v','--version', help="Show version", default=False,action="store_true")
    parser.add_argument('--tools-dir', help="Initialize with specific tool directory", default=None)
    ## if no parameter is furnished, exit with printing help
    if len(sys.argv)==1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args=parser.parse_args()
    if args.version:
        sys.exit(1)

    return args 

## threading environment
args=get_args()
if hasattr(args,'num_threads'):
    os.environ['OMP_NUM_THREADS']=str(args.num_threads) ## this should go before loading any dipy function. 
    os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(args.num_threads) ## for ANTS threading

import dtiplayground.dmri.fiberprofile
import dtiplayground.dmri.fiberprofile.modules
import dtiplayground.dmri.fiberprofile.protocols

if __name__=='__main__':
    try:
        dtiplayground.dmri.common.logger.setTimestamp(True)
        result=args.func(args)
        exit(0)
    except Exception as e:
        dtiplayground.dmri.common.logger.setVerbosity(True)
        msg=traceback.format_exc()
        logger(msg,color.ERROR)
        exit(-1)
    finally:
        pass


