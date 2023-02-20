#!python

import shutil
import os 
import importlib
from pathlib import Path
import traceback
import time
import yaml
import uuid
import sys
import re
from functools import wraps
import subprocess

from dtiplayground.config import INFO as info
import dtiplayground
import dtiplayground.dmri.common as common
import dtiplayground.dmri.common.module as module

logger=common.logger.write 
color= common.Color

class AppBase:
    def __init__(self,config_root, app_name,*args,**kwargs):
        self.config_dir = Path(config_root)
        self.app = {}
        self.app['application'] = app_name
        self.getAppInfo()
        if 'application_dir' in self.app:
            self.log_file = str(Path(self.app['application_dir']).joinpath('log.txt'))
            self.app.setdefault('no_log_timestamp',False)
            self.app.setdefault('log', self.log_file)
            self.app.setdefault('no_verbosity', False)
            self.app.setdefault('execution_id',  common.get_uuid())
            self.kwargs=kwargs
        else:
            self.kwargs=kwargs
        self.globalvars = {}
        logger(yaml.dump(self.app))

    def getAppInfo(self):
        version=info[self.app['application']]['version']
        application_dir=Path(self.config_dir).joinpath('{}-{}'.format(self.app['application'],str(version))).resolve()
        res = {
            'version' : version,
            'config_dir' : str(self.config_dir),
            'application_dir' : str(application_dir)
        }
        self.app.update(res)
        self.getAppInfoImpl()

        return self.app 

    def getAppInfoImpl(self):
        return self.app

    def initialize(self, options):
        ## reparametrization
        _args = {
            'log' : self.app['log'],
            'execution_id' : self.app['execution_id'],
            'no_verbosity' : self.app['no_verbosity'],
            'no_log_timestamp' : self.app['no_log_timestamp']
        }
        _args.setdefault('tools_dir',None)
        _args.setdefault('install_tools',False)

        home_dir = Path(self.app['application_dir'])
        version = self.app['version']

        ## Function begins
        home_dir.mkdir(parents=True,exist_ok=True)
        tools_dir = Path(self.app['config_dir'])
        if _args['tools_dir'] is not None:
            tools_dir = Path(_args['tools_dir'])
        else:
            tools_dir = Path(self.app['config_dir'])

        globalvars_fn=Path(self.app['config_dir']).joinpath('global_variables.yml')

        if globalvars_fn.exists():
            self.globalvars = yaml.safe_load(open(globalvars_fn,'r'))


        if tools_dir is not None:
            if tools_dir.exists():
                dptdir = tools_dir.joinpath('dtiplayground-tools')
                fsldir = tools_dir.joinpath('FSL')
                if not fsldir.exists() or not dptdir.joinpath('info.yml').exists():
                    if not _args['install_tools']:
                        logger('Couldn\'t find the DTIPlayground tools',color.ERROR)
                        logger('Please install DTIPlayground tools: $ dmriplayground install-tools',color.INFO)
                        logger('Do you want to install the tools now? [Y/n]')
                        yn = input()
                        if yn=='n':
                            logger('Initialization aborted')
                            exit(1)
                        else:
                            self.install_tools({'output_dir': tools_dir})
                    else:
                        self.install_tools({'output_dir': tools_dir})


                self.globalvars.update({
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
                yaml.dump(self.globalvars, open(globalvars_fn,'w'))
            else:
                logger("Couldn't find tool directory {}".format(str(tools_dir)),color.ERROR)
                exit(1)

        self.initialize_logger(_args)

        self.initializeImpl(options)

        initialization_fn = Path(self.app['application_dir']).joinpath("init.yml")
        yaml.dump(self.app, open(initialization_fn,'w'))
        logger("Initialized. Local configuration will be stored in {}".format(str(home_dir)),color.OK)

    def install_tools(self,_options={}):
        # @self.after_initialized
        def _install_tools(options):
            ## reparametrization
            options.setdefault('no_fsl',False)
            options.setdefault('install_only', True)
            options.setdefault('build', False)
            options.setdefault('no_remove', False)
            options.setdefault('clean_install', False)
            options.setdefault
            args = {
                'output_dir' : options['output_dir'],
                'clean_install': options['clean_install'],
                'no_fsl' : options['no_fsl'],
                'install_only' : options['install_only'],
                'build' : options['build'],
                'no_remove' : options['no_remove'],
            }
            home_dir=Path(self.app['application_dir'])
            home_dir.parent.mkdir(parents=True,exist_ok=True)
            # globalvars_fn = Path(os.path.expandvars("$HOME/.niral-dti/global_variables.yml"))
            globalvars_fn = home_dir.parent.joinpath('global_variables.yml')
            Path(globalvars_fn).parent.mkdir(parents=True,exist_ok=True)
            globalvars = {}
            if globalvars_fn.exists():
                globalvars = yaml.safe_load(open(globalvars_fn,'r'))

            rootdir = Path(os.path.expandvars(args['output_dir'])).resolve()
            rootdir.mkdir(parents=True,exist_ok=True)
            tempdir = rootdir.joinpath('temp-dtiplayground-tools')
            outputdir = rootdir.joinpath('dtiplayground-tools')
            fsldir = rootdir.joinpath('FSL')
            clean_install = args['clean_install']
            leave_files_after_installation = args['no_remove']
            no_fsl = args['no_fsl']
            install_only = args['install_only']
            build=args['build']
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
                import dtiplayground.dmri.common.data
                fslinstaller_fn=Path(dtiplayground.dmri.common.data.__file__).parent.joinpath('fslinstaller.py')
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
                self._update_software_paths(globalvars)
            logger("Installation completed")
            return True
        return _install_tools(_options)

    def initializeImpl(self, options):
        pass

    def run(self,options): ### options must have output_dir 
        return self.runImpl(options)

    def runImpl(self, options):
        return True

    ################################################
    ## decorators (only used in the memeber function)
    #################################################

    def after_initialized(self,func): #decorator for other functions other than command_init
        def wrapper(args):
            home_dir=Path(self.app['application_dir'])
            if home_dir.exists() and home_dir.joinpath('init.yml').exists() and home_dir.parent.joinpath('global_variables.yml').exists():
                logger("Configuration directory is found : {}".format(self.app['application_dir']),color.OK)
                config_file=home_dir.joinpath('config.yml')
                environment_file=home_dir.joinpath('environment.yml')
                self.initialize_logger(self.app)
                return func(args)
            else: 
                # raise Exception("Not initialized, please run init command at the first use")
                logger("Configuration directory is not found or some files are missing, commencing initialization ...",color.WARNING)
                self.initialize(args)
                config_file=home_dir.joinpath('config.yml')
                environment_file=home_dir.joinpath('environment.yml')
                self.initialize_logger(self.app)
                return func(args)
        return wrapper


    #################################################
    ######## utilities
    #################################################

    def initialize_logger(self,_args):
        ## default log setting
        common.logger.setLogfile(_args['log'])
        common.logger.setTimestamp(not _args['no_log_timestamp'])
        common.logger.setVerbosity(not _args['no_verbosity'])


    def _update_software_paths(self, globalvars):
        home_dir=Path(self.app['application_dir'])
        software_info_path=Path(dtiplayground.__file__).resolve().parent.joinpath("dmri/common/data/software_paths.yml")
        software_paths=yaml.safe_load(open(software_info_path,'r'))
        software_paths=self._resolve_softwarepaths(software_paths, globalvars)
        software_filename=home_dir.joinpath('software_paths.yml')
        yaml.dump(software_paths, open(software_filename,'w'))
    
    def _resolve_softwarepaths(self,spathobj, globalvars):
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


