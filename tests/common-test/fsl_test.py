#!/usr/bin/python3



import sys
import argparse
from pathlib import Path 
import yaml
import traceback
sys.path.append("../../")

import dmri.common
import dmri.common.tools as tools 

logger=dmri.common.logger.write


def FSL_eddy(args):
    s_path=args.software_path 
    cmd=args.command

    module=tools.FSL(paths["FSL"])
    #module.setPath()
    comp=module.execute(cmd)
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0   

if __name__=='__main__':
    current_dir=Path(__file__).parent
    parser=argparse.ArgumentParser()
    parser.add_argument('command',help='command')
    parser.add_argument('--software-path',help='software paths', default=str(current_dir.joinpath('software_paths.yml')))
    parser.add_argument('--log',help='log file',default=str(current_dir.joinpath('log.txt')))
    parser.add_argument('--no-log-timestamp',help='Add timestamp in the log', default=False, action="store_true")
    parser.add_argument('-n','--no-verbosity',help='Remove timestamp in the log', default=False, action="store_false")
    parser.add_argument('--args',nargs='*')
    args=parser.parse_args()
    dmri.common.logger.setLogfile(args.log,'w')
    dmri.common.logger.setTimestamp(not args.no_log_timestamp)
    dmri.common.logger.setVerbosity(not args.no_verbosity)
    
    s_path=args.software_path 
    print(sys.argv)
    paths=yaml.safe_load(open(s_path,'r'))
    fsl=tools.FSL(paths['FSL'])
    func=getattr(fsl,args.command)
    comp=func(*args.args)
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))

