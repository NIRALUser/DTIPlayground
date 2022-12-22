#!python

import sys
import os 
import traceback
import shutil
import socket
from pathlib import Path
import argparse
from argparse import RawTextHelpFormatter
import yaml
sys.path.append(Path(__file__).resolve().parent.parent.__str__())  ## this line is for development
import dtiplayground
import dtiplayground.dmri.common as common
from dtiplayground.config import INFO as info
from dtiplayground.api.server import DTIPlaygroundServer
from dtiplayground.dmri.playground.app import DMRIPlaygroundApp

logger=common.logger.write 
color= common.Color

## utils

def next_free_port(port=6543, max_port=6999 ):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while port <= max_port:
        try:
            sock.bind(('', port))
            sock.close()
            return port
        except OSError:
            port += 1
    raise IOError('no free ports')

### unit functions

def command_install_tools(args):
    ## reparametrization
    options = {
        'config_dir' : args.config_dir,
        'output_dir' : args.output_dir,
        'clean_install': args.clean_install,
        'no_fsl' : args.no_fsl,
        'install_only' : args.install_only,
        'build' : args.build,
        'no_remove' : args.no_remove,
    }
    app = DMRIPlaygroundApp(options['config_dir'])
    app.install_tools(options)
    return True

def command_init(args):
    ## reparametrization
    options = {
        'config_dir' : args.config_dir,
        'log' : args.log,
        'execution_id' : args.execution_id,
        'no_verbosity' : args.no_verbosity,
        'no_log_timestamp' : args.no_log_timestamp,
        'version' : args.version,
        'tools_dir' : args.tools_dir,
    }
    app = DMRIPlaygroundApp(options['config_dir'])
    return app.initialize(options)
    

def command_server(args):
    config = {
        "config_dir": args.config_dir,
        "host" : args.host,
        "port" : next_free_port(int(args.port)),
        "static_page_dir" : Path(args.directory).resolve().__str__(),
        "browser" : args.browser,
        "debug" : args.debug
    }

    if config['browser']: 
        import webbrowser
        from threading import Timer
        def open_browser():
            webbrowser.open('http://{}:{}'.format(config['host'],config['port']))
        Timer(1, open_browser).start();
        
    app = DMRIPlaygroundApp(config['config_dir'])
    app.run(config)
    
    return True

### Arguments 

def get_args():
    version=info['dmriplayground']['version']
    logger("VERSION : {}".format(str(version)))
    config_dir=Path.home().joinpath('.niral-dti').resolve()
    # ## read template
    uid, ts = common.get_uuid(), common.get_timestamp()

    ### Argument parsers

    parser=argparse.ArgumentParser(prog="dpg",
                                   formatter_class=RawTextHelpFormatter,
                                   description="The dtiplayground is an integrated DWI processing platform",
                                   epilog="Written by SK Park (sangkyoon_park@med.unc.edu) , Johanna Dubos (johannadubos32@gmail.com) , Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States, 2021")
    subparsers=parser.add_subparsers(help="Commands")
    
    ## init command
    parser_init=subparsers.add_parser('init',help='Initialize configurations')
    parser_init.set_defaults(func=command_init)

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
    parser_server.add_argument('--debug', help="Debug mode", default=False, action="store_true")
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
        common.logger.setTimestamp(True)
        result=args.func(args)
        exit(0)
    except Exception as e:
        common.logger.setVerbosity(True)
        msg=traceback.format_exc()
        logger(msg,color.ERROR)
        exit(-1)
    finally:
        pass


