#!/usr/bin/python3

from pathlib import Path
import dmri.prep
from dmri.prep.dwi import DWI 
import dmri.prep.modules
import dmri.prep.protocols as protocols
import numpy as np 
import argparse,yaml
import traceback
import time 
import copy
import yaml
import dmri.fa #dti fiber analyser
import dmri.ab #dti atlas builder

logger=dmri.prep.logger.write

def io_test():
    
    try:
        fname_nrrd="_data/images/CT-00006_DWI_dir79_APPA.nrrd"

        # fname_nifti="data/images/CT-00006_DWI_dir79_APPA.nii.gz"
        # dwi_nifti=DWI(fname_nifti)
        dwi_nrrd=prep.dwi.DWI(fname_nrrd)
        logger(str(dwi_nrrd.information))

        # err=0.0
        # for g in zip(dwi_nifti,dwi_nrrd):
        #     dnifti,dnrrd=g
        #     img_nrrd, grad_nrrd = dnrrd
        #     img_nifti,grad_nifti= dnifti
        #     err+= np.sum((grad_nifti['b_value']-grad_nrrd['b_value'])**2)

        bt=time.time()
        newdwi=copy.deepcopy(dwi_nrrd)
        refdwi=dwi_nrrd
        elapsed=time.time()-bt
        logger("Elapsed time to copy image : {}s".format(elapsed))

        newdwi.images=None
        logger(str(dwi_nrrd.images[:,:,40,0]))
        logger(str(newdwi.images))
        logger("Original address : "+str(dwi_nrrd))
        logger("Deepcopied address : "+str(newdwi))
        logger("Referenced address : "+str(refdwi))
        
        
        dwi_nrrd.setB0Threshold(b0_threshold=1500)
        # grad_with_baselines=dwi_nrrd.getGradients()
        # for g in grad_with_baselines:
        #     if g['baseline']:
        #         logger(str(g['b_value']))
        ### writing
        #dwi_nrrd.writeImage('test.nrrd')
        return True
    except Exception as e:
        logger("Exception occurred : {}".format(str(e)))
        traceback.print_exc()
        return False
    
def protocol_test():
    try:
        fname_nrrd="_data/images/CT-00006_DWI_dir79_APPA.nrrd"
        #fname_nrrd="_data/images/CT-00006_DWI_dir79_APPA.nii.gz"
        #fname_nrrd="_data/images/MMU45938_DTI_HF_fix1.nrrd"
        #fname_nrrd="_data/images/neo-0378-1-1-10year-DWI_dir79_AP_1-series.nrrd"
        #fname_nrrd="_data/images/ImageTest1.nrrd"
        output_dir=str(Path(fname_nrrd).parent.joinpath("output"))
        logfile=str(Path(output_dir).joinpath('log.txt'))
        Path(output_dir).mkdir(parents=True,exist_ok=True)
        dmri.prep.logger.setLogfile(logfile)
        options={"options":{"overwrite":False}}
        pipeline=[  
                    ['DIFFUSION_Check',options],
                    ['SLICE_Check',options],
                    ['INTERLACE_Check',options],
                    ['BASELINE_Average',{"options":{"overwrite":False,"recompute":False}, "protocol":{"stopThreshold":0.09}}],
                    ['EDDYMOTION_Correct',{"options":{"overwrite":True,"recompute":True},"protocol":{}} ]
                 ]
        env=yaml.safe_load(open('environment.yml','r'))
        modules=dmri.prep.modules.load_modules(user_module_paths=['test/examples/modules'])
        modules=dmri.prep.modules.check_module_validity(modules,env)
        proto=protocols.Protocols(modules)
        
        proto.loadImage(fname_nrrd,b0_threshold=10)
        proto.setOutputDirectory(output_dir)
        proto.makeDefaultProtocols(pipeline=pipeline)
        #proto.loadProtocols("_data/protocol_files/protocols-2.yml")
        proto.addPipeline('TEST_Check',index=13)
        proto.addPipeline('SLICE_Check',{"options":{"overwrite":False},"protocol":{"tailSkipSlicePercentage":0.5}},index=15)
        res=proto.runPipeline()
        #logger(yaml.dump(res))
        #proto.writeProtocols(Path(output_dir).joinpath("protocols.yml").__str__())
        #logger(yaml.dump(proto.modules))
        return res
    except Exception as e:
        logger("Exception occurred : {}".format(str(e)))
        traceback.print_exc()
        return False

def environment_test():
    try:
        modules=dmri.prep.modules.load_modules(user_module_paths=['user/modules'])
        env=dmri.prep.modules.generate_module_envionrment(modules)
        logger(yaml.dump(env))


        out_filename=str(Path('_data/environment-test.yml').absolute())
        logger("Writing test environment file : {}".format(out_filename),dmri.prep.Color.PROCESS)
        yaml.dump(env,open(out_filename,'w'))

        return True
    except Exception as e:
        logger("Exception occurred :{}".format(str(e)))
        traceback.print_exc()
        return False
    
def run_tests(testlist: list):
    for idx,t in enumerate(testlist):
        c=dmri.prep.Color.BLACK+dmri.prep.Color.BOLD
        logger("---------------------------------------",c)
        logger("--------- {}/{} - Running : {}".format(idx+1,len(testlist),t),c)
        logger("---------------------------------------",c)
        if eval(t)() : logger("[{}/{}] : {} - Success".format(idx+1,len(testlist),t))
        else: logger("[{}/{}] : {} - Failed".format(idx+1,len(testlist),t))

if __name__=='__main__':
    current_dir=Path(__file__).parent
    parser=argparse.ArgumentParser()
    parser.add_argument('--log',help='log file',default=str(current_dir.joinpath('_data/log.txt')))
    parser.add_argument('--log-timestamp',help='Add timestamp in the log', default=False, action="store_true")
    parser.add_argument('-n','--no-verbosity',help='Add timestamp in the log', default=True, action="store_false")
    args=parser.parse_args()
    dmri.prep.logger.setLogfile(args.log)
    dmri.prep.logger.setTimestamp(args.log_timestamp)
    dmri.prep.logger.setVerbosity(args.no_verbosity)
    
    tests=['io_test','protocol_test','environment_test']
    run_tests(tests[1:2])
