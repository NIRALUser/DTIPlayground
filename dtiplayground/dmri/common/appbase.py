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
            'no_log_timestamp' : self.app['no_log_timestamp'],
        }
        _args.setdefault('tools_dir',None)

        home_dir = Path(self.app['application_dir'])
        version = self.app['version']

        ## Function begins
        home_dir.mkdir(parents=True,exist_ok=True)
        tools_dir = None
        if _args['tools_dir'] is not None:
            tools_dir = Path(_args['tools_dir'])

        globalvars_fn=Path(self.app['config_dir']).joinpath('global_variables.yml')

        if globalvars_fn.exists():
            self.globalvars = yaml.safe_load(open(globalvars_fn,'r'))

        if tools_dir is not None:
            if tools_dir.exists():
                dptdir = tools_dir.joinpath('dtiplayground-tools')
                fsldir = tools_dir.joinpath('FSL')
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
            if home_dir.exists() and home_dir.joinpath('init.yml').exists():
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


