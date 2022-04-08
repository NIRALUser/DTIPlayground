#!python

import shutil
import os 
import importlib
import traceback,time,copy,yaml,sys,uuid
from pathlib import Path
import argparse,yaml
from argparse import RawTextHelpFormatter
sys.path.append(Path(__file__).parent.__str__())


import dtiplayground.dmri.common 
import dtiplayground.dmri.common.study as study
import dtiplayground.dmri.common.study.loaders as study_loaders
from dtiplayground.config import INFO as info
logger=dtiplayground.dmri.common.logger.write 


### decorators

def log_off(func):
    def wrapper(*args,**kwargs):
        dtiplayground.dmri.common.logger.setVerbosity(False)
        res=func(*args,**kwargs)
        dtiplayground.dmri.common.logger.setVerbosity(True)
        return res 
    return wrapper


### command functions

def command_import(args):
    ## reparametrization
    options={
        "study_dirs" : args.study_dirs,
        "execution_id":args.execution_id,
        "output" : args.output
    }
    if options['output'] is None:
        options['output']='output.yml'

    ## load config file and run pipeline
    res = study_loaders.load_bids(options['study_dirs'])
    with open(options['output'],'w') as f:
        yaml.dump(res,f)
    return res

### Arguments 

def get_args():
    current_dir=Path(__file__).parent
    # info=yaml.safe_load(open(current_dir.parent.joinpath('dtiplayground/info.json'),'r'))
    version=info['dtiplayground']['version']
    logger("VERSION : {}".format(str(version)))
    config_dir=Path(os.environ.get('HOME')).joinpath('.niral-dti')
    uid, ts = dtiplayground.dmri.common.get_uuid(), dtiplayground.dmri.common.get_timestamp()

    ### Argument parsers

    parser=argparse.ArgumentParser(prog="dtiplayground",
                                   formatter_class=RawTextHelpFormatter,
                                   description="DTIPlayground is a integration software for the overall DTI processes such as dmriprep, dtiatlasbuilder and so on.",
                                   epilog="Written by SK Park (sangkyoon_park@med.unc.edu) , Neuro Image Research and Analysis Laboratories, University of North Carolina @ Chapel Hill , United States, 2021")
    #parser.add_argument('command',help='command',type=str)
    subparsers=parser.add_subparsers(help="Commands")
    

    ## run command
    parser_import=subparsers.add_parser('import',help='Run Test')
    parser_import.add_argument('-s','--study-dirs',help='Study Directory',type=str,nargs='+')
    parser_import.add_argument('-o','--output',help="Output Filename",type=str,required=False)
    parser_import.set_defaults(func=command_import)

    ## log related
    parser.add_argument('--config-dir',help='Configuration directory',default=str(config_dir))
    parser.add_argument('--log',help='log file',default=str(config_dir.joinpath('log.txt')))
    parser.add_argument('--system-log-dir',help='System log directory',default='/BAND/USERS/skp78-dti/system-logs',type=str)
    parser.add_argument('--execution-id',help='execution id',default=uid,type=str)
    parser.add_argument('--no-log-timestamp',help='Remove timestamp in the log', default=False, action="store_true")
    parser.add_argument('--no-verbosity',help='Do not show any logs in the terminal', default=False, action="store_true")
    

    ## if no parameter is furnished, exit with printing help
    if len(sys.argv)==1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    args=parser.parse_args()

    ## system log
    sys_log_dir=Path(args.system_log_dir)
    sys_log_dir.mkdir(parents=True,exist_ok=True)
    env=os.environ
    
    sys_logfilename='dtiplayground'+env['USER']+"_"+ts+"_"+args.execution_id+".txt"
    sys_logfile=sys_log_dir.joinpath(sys_logfilename)
    dtiplayground.dmri.common.logger.addLogfile(sys_logfile.__str__(),mode='w')
    logger("Execution ID : {}".format(args.execution_id))
    logger("Execution Command : "+" ".join(sys.argv))

    return args 

args=get_args()

if __name__=='__main__':
    try:
        dtiplayground.dmri.common.logger.setTimestamp(True)
        result=args.func(args)
        exit(0)
    except Exception as e:
        dtiplayground.dmri.common.logger.setVerbosity(True)
        msg=traceback.format_exc()
        logger(msg,dtiplayground.dmri.common.Color.ERROR)
        exit(-1)
    finally:
        pass


