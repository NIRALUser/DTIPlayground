#!python

import shutil
import os 
from pathlib import Path
import traceback
import yaml
import re
from functools import wraps
import subprocess
import sys

from dtiplayground.config import INFO as info
import dtiplayground
import dtiplayground.dmri.common as common
import dtiplayground.dmri.common.module as module
from dtiplayground.dmri.common.appbase import AppBase

from dtiplayground.dmri.atlasbuilder import AtlasBuilder 

logger=common.logger.write 
color= common.Color

class DMRIAtlasBuilderApp(AppBase):

    ######### Mandatory Implementations Begins
    def __init__(self, config_root, app_name='dmriatlas', *args, **kwargs):
        super().__init__(config_root,app_name,*args,**kwargs)

    def getAppInfoImpl(self):
        return self.app

    def initializeImpl(self, options):
        return True

    #######################
    #### default command
    #######################
    def runImpl(self, options):
        return self.build(options)

    ######### Mandatory Implementations Ends



    ########################################
    ######### commands
    ########################################

    def build(self,options):
        @self.after_initialized
        def _build(options):
            logger = common.logger
            # logger.setFilePointer(sys.stdout)
            output_dir = Path(options['output_dir']).resolve()
            output_dir.mkdir(exist_ok=True, parents=False)
            config_path=output_dir.joinpath('common/config.yml')
            hbuild_path=output_dir.joinpath('common/h-build.yml')
            greedy_path=output_dir.joinpath('common/greedy.yml')

            bldr=AtlasBuilder(logger = logger)
            bldr.configure( output_dir=options['output_dir'],
                            config_path=options['config_path'],
                            hbuild_path=options['hbuild_path'],
                            greedy_path=options['greedy_path'])
       
            bldr.build()
        return _build(options)
        
   
    ##############        
    ### utilities
    ##############

 