#!python

import shutil
import os 
from pathlib import Path
import traceback
import yaml
import re
from functools import wraps
import subprocess

from dtiplayground.config import INFO as info
import dtiplayground
import dtiplayground.dmri.common as common
import dtiplayground.dmri.common.module as module
from dtiplayground.dmri.common.appbase import AppBase

from dtiplayground.api.server import DTIPlaygroundServer
import dtiplayground.dmri.playground as playground
logger=common.logger.write 
color= common.Color

class DMRIPlaygroundApp(AppBase):

    ######### Mandatory Implementations Begins
    def __init__(self, config_root, app_name='dmriplayground', *args, **kwargs):
        super().__init__(config_root,app_name,*args,**kwargs)

    def getAppInfoImpl(self):
        return self.app

    def initializeImpl(self, options):
        return True

    #######################
    #### default command
    #######################
    def runImpl(self, options):
        return self.serve(options)

    ######### Mandatory Implementations Ends



    ########################################
    ######### commands
    ########################################

    def serve(self, _options):
        @self.after_initialized
        def _serve(options):
            spa_dir = Path(self.config_dir).joinpath('static/spa')
            options.setdefault('host', '127.0.0.1')
            options.setdefault('port', 6543)
            options.setdefault('browser', False)
            options.setdefault('static_page_dir', spa_dir)
            options.setdefault('debug', False)
            config = {
                "config_dir": Path(self.app['application_dir']).parent.__str__(),
                "host" : options['host'],
                "port" : options['port'],
                "static_page_dir" : options['static_page_dir'],
                "browser" : options['browser'],
                "debug" : options['debug']
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
            app = DTIPlaygroundServer(**config)
            app.configure(host=options['host'],
                          port=options['port'],
                          static_folder=options['static_page_dir'],
                          static_url_path='/')

            logger("API Server initiated, running",color.OK)
            app.serve()

            return True
        return _serve(_options)
   
    ##############        
    ### utilities
    ##############

 