#!/usr/bin/python3



import sys
import argparse
from pathlib import Path 
import yaml
import traceback
sys.path.append("../../")

import dmri.common
import dmri.common.tools as tools 

# import dmri.common.tools.image_math as tool_im 
# import dmri.common.tools.dti_reg as tool_im 
# import dmri.common.tools.brainsfit as tool_im 
# import dmri.common.tools.dtiaverage as tool_im 
# import dmri.common.tools.dtiprocess as tool_im 
# import dmri.common.tools.greedy_atlas as tool_im 
# import dmri.common.tools.itk_transform_tools as tool_im 


logger=dmri.common.logger.write


def ImageMath(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.ImageMath()
    module.setPath(paths["ImageMath"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def ResampleDTIlogEuclidean(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.ResampleDTIlogEuclidean()
    module.setPath(paths["ResampleDTIlogEuclidean"])

    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def CropDTI(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.CropDTI()
    module.setPath(paths["CropDTI"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def DTIProcess(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.DTIProcess()
    module.setPath(paths["dtiprocess"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def BRAINSFit(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.BRAINSFit()
    module.setPath(paths["BRAINSFit"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def GreedyAtlas(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.GreedyAtlas()
    module.setPath(paths["GreedyAtlas"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0


def DTIReg(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.DTIReg()
    module.setPath(paths["DTI-Reg"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def DTIAverage(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.DTIAverage()
    module.setPath(paths["dtiaverage"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def unu(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.UNU()
    module.setPath(paths["unu"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0

def ITKTransformTools(args):
    s_path=args.software_path 
    paths=yaml.safe_load(open(s_path,'r'))

    module=tools.ITKTransformTools()
    module.setPath(paths["ITKTransformTools"])
    comp=module.execute()
    logger(str(comp.args))
    logger(str(comp.stdout))
    logger(str(comp.stderr))
    logger(str(comp.returncode))
    #comp.check_returncode() ## 0 is success
    logger(str(module))
    return comp.returncode==0


## test runner
    
def run_tests(testlist: list,args=None):
    n_success=0
    for idx,t in enumerate(testlist):
        c=dmri.common.Color.BLACK+dmri.common.Color.BOLD
        logger("---------------------------------------",c)
        logger("--------- {}/{} - Running : {}".format(idx+1,len(testlist),t),c)
        logger("---------------------------------------",c)
        if eval(t)(args) : 
            logger("[{}/{}] : {} - Success".format(idx+1,len(testlist),t))
            n_success+=1
        else: 
            logger("[{}/{}] : {} - Failed".format(idx+1,len(testlist),t))
    logger("{}/{} has been executed successfully.".format(n_success,len(testlist)),dmri.common.Color.INFO)
    return n_success

if __name__=='__main__':
    current_dir=Path(__file__).parent
    parser=argparse.ArgumentParser()
    parser.add_argument('--software-path',help='software paths', default=str(current_dir.joinpath('software_paths.yml')))
    parser.add_argument('--log',help='log file',default=str(current_dir.joinpath('log.txt')))
    parser.add_argument('--no-log-timestamp',help='Add timestamp in the log', default=False, action="store_true")
    parser.add_argument('-n','--no-verbosity',help='Remove timestamp in the log', default=False, action="store_false")
    args=parser.parse_args()
    dmri.common.logger.setLogfile(args.log,'w')
    dmri.common.logger.setTimestamp(not args.no_log_timestamp)
    dmri.common.logger.setVerbosity(not args.no_verbosity)
    
    tests=['ImageMath',
           'CropDTI',
           'ResampleDTIlogEuclidean',
           'DTIProcess',
           'BRAINSFit',
           'GreedyAtlas',
           'DTIReg',
           'DTIAverage',
           'unu',
           'ITKTransformTools']
    try:
        run_tests(tests,args)
    except Exception as e:
        msg=traceback.format_exc()
        logger("{} : {}".format(str(e),msg))

    print(sys.argv)
