#!/usr/bin/python3

from pathlib import Path
import dtiprep
from dtiprep.io import DWI 
import dtiprep.protocols as protocols
import numpy as np 
import argparse,yaml
import traceback

logger=dtiprep.logger.write

def io_test():
    
    try:
        fname_nrrd="data/images/CT-00006_DWI_dir79_APPA.nrrd"
        fname_nifti="data/images/CT-00006_DWI_dir79_APPA.nii.gz"
        dwi_nifti=DWI(fname_nifti)
        dwi_nrrd=DWI(fname_nrrd)

        err=0.0
        for g in zip(dwi_nifti,dwi_nrrd):
            dnifti,dnrrd=g
            img_nrrd, grad_nrrd = dnrrd
            img_nifti,grad_nifti= dnifti
            err+= np.sum((grad_nifti['b_value']-grad_nrrd['b_value'])**2)

        ### writing
        #dwi_nrrd.writeImage('test.nrrd')
        return True
    except Exception as e:
        logger("Exception occurred : {}".format(str(e)))
        return False
    
def protocol_test():
    try:
        proto=protocols.Protocols()
        proto.loadProtocols("data/protocol_files/protocols.yml")
        proto.runPipeline()
        return True
    except Exception as e:
        logger("Exception occurred : {}".format(str(e)))
        traceback.print_exc()
        return False
    pass
    
def run_tests(testlist: list):
    for idx,t in enumerate(testlist):
        logger("---------------------------------------")
        logger("--------- {}/{} - Running : {}".format(idx+1,len(testlist),t))
        logger("---------------------------------------")
        if eval(t)() : logger("[{}/{}] : {} - Success".format(idx+1,len(testlist),t))
        else: logger("[{}/{}] : {} - Failed".format(idx+1,len(testlist),t))

if __name__=='__main__':
    current_dir=Path(__file__).parent
    parser=argparse.ArgumentParser()
    parser.add_argument('--log',help='log file',default=str(current_dir.joinpath('data/log.txt')))
    args=parser.parse_args()
    dtiprep.logger.setLogfile(args.log)
    
    
    tests=['io_test','protocol_test']
    run_tests(tests[1:])