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
sys.path.append(Path(__file__).resolve().parent.parent.__str__())  ## this line is for development
import dtiplayground
import dtiplayground.dmri.common
import dtiplayground.dmri.common.module
from dtiplayground.config import INFO as info
from dtiplayground.api.server import DTIPlaygroundServer

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

    user_module_dir=home_dir.joinpath('modules').absolute()
    user_module_dir.mkdir(parents=True,exist_ok=True)

    globalvars_fn=home_dir.joinpath('global_variables.yml')
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
    logger("Initialized",color.OK)
    return True

def command_server(args):
    config = {
        "config_dir": args.config_dir,
        "host" : args.host,
        "port" : args.port,
        "static_page_dir" : args.directory,
        "browser" : args.browser
    }
    config_dir = Path(config['config_dir'])

    ## spa installation
    logger("Installing UI",color.PROCESS)
    static_dir = config_dir.joinpath('static')
    import dtiplayground.api.static.spa as s 
    from zipfile import ZipFile
    spa_archive_fn=Path(s.__file__).resolve().parent.joinpath('spa.zip')
    with ZipFile(spa_archive_fn,'r') as z:
        z.extractall(static_dir)
    logger("Done",color.OK)
    logger("API Server initiating ... ",color.PROCESS)
    
    ## app prep
    app = DTIPlaygroundServer()
    app.configure(host=config['host'],
                  port=config['port'],
                  static_folder=config['static_page_dir'],
                  static_url_path='/')

    if config['browser']: 
        import webbrowser
        from threading import Timer
        def open_browser():
            webbrowser.open('http://localhost:6543')
        Timer(1, open_browser).start();
    logger("API Server initiated, running",color.OK)
    app.serve()

    return True

### Arguments 

def get_args():
    current_dir=Path(__file__).resolve().parent
    # info=yaml.safe_load(open(current_dir.parent.joinpath('dtiplayground/info.json'),'r'))
    version=info['dtiplayground']['version']
    logger("VERSION : {}".format(str(version)))
    config_dir=Path(os.environ.get('HOME')).joinpath('.niral-dti')
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

    parser=argparse.ArgumentParser(prog="dpg",
                                   formatter_class=RawTextHelpFormatter,
                                   description="The dtiplayground is an integrated DWI processing platform",
                                   epilog="Written by SK Park (sangkyoon_park@med.unc.edu) , Johanna Dubos (johannadubos32@gmail.com) , Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States, 2021")
    subparsers=parser.add_subparsers(help="Commands")
    
    ## init command
    parser_init=subparsers.add_parser('init',help='Initialize configurations')
    parser_init.set_defaults(func=command_init)

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

    ## DPG Server
    parser_server=subparsers.add_parser('serve',help='DTIPlayground Server')
    parser_server.add_argument('--host', help="Host", default="127.0.0.1")
    parser_server.add_argument('-p','--port', help="Port", default=6543)
    parser_server.add_argument('-d','--directory', help="Static Page Path", default=str(config_dir.joinpath('static/spa')))
    parser_server.add_argument('--browser', help="Launch browser at start up", default=False, action="store_true")
    parser_server.set_defaults(func=command_server)

    ## log related
    parser.add_argument('--config-dir',help='Configuration directory',default=str(config_dir))
    parser.add_argument('--log',help='log file',default=str(config_dir.joinpath('log.txt')))
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


