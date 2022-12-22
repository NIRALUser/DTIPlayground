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

    def install_tools(self,_options):
        @self.after_initialized
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

   
    ##############        
    ### utilities
    ##############

 