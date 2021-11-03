#!/usr/bin/python3



import numpy as np 
from pathlib import Path
import argparse
import yaml
import traceback
import time 
import copy
import yaml
import sys
import os
sys.path.append("../../")

import dmri.preprocessing
from dmri.preprocessing.dwi import DWI 
import dmri.preprocessing.modules
import dmri.preprocessing.protocols as protocols
import dmri.fiberanalyzer #dti fiber analyser
import dmri.atlasbuilder #dti atlas builder

logger=dmri.preprocessing.logger.write


def io_test():
    
    try:
        fname_nrrd="../_data/images/CT-00006_DWI_dir79_APPA.nrrd"

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
        fname_nrrd="../_data/images/CT-00006_DWI_dir79_APPA.nrrd"
        #fname_nrrd="_data/images/CT-00006_DWI_dir79_APPA.nii.gz"
        #fname_nrrd="_data/images/MMU45938_DTI_HF_fix1.nrrd"
        #fname_nrrd="_data/images/neo-0378-1-1-10year-DWI_dir79_AP_1-series.nrrd"
        #fname_nrrd="_data/images/ImageTest1.nrrd"
        output_dir=str(Path(fname_nrrd).parent.joinpath("output"))
        logfile=str(Path(output_dir).joinpath('log.txt'))
        Path(output_dir).mkdir(parents=True,exist_ok=True)
        dmri.preprocessing.logger.setLogfile(logfile)
        options={"options":{"overwrite":False}}
        pipeline=[  
                    ['DIFFUSION_Check',options],
                    ['SLICE_Check',options],
                    #['INTERLACE_Check',options],
                    ['BASELINE_Average',{"options":{"overwrite":False,"recompute":False}, "protocol":{"stopThreshold":0.09}}]
                 ]
        env=yaml.safe_load(open('environment.yml','r'))
        modules=dmri.preprocessing.modules.load_modules(user_module_paths=['examples/modules'])
        modules=dmri.preprocessing.modules.check_module_validity(modules,env)
        proto=protocols.Protocols(modules)
        
        proto.loadImage(fname_nrrd,b0_threshold=10)
        proto.setOutputDirectory(output_dir)
        proto.makeDefaultProtocols(pipeline=pipeline)
        #proto.loadProtocols("_data/protocol_files/protocols-2.yml")
        proto.addPipeline('TEST_Check',index=13)
        proto.addPipeline('SLICE_Check',{"options":{"overwrite":False},"protocol":{"tailSkipSlicePercentage":0.1,"correlationDeviationThresholdbaseline":1.0}},index=15)
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
        modules=dmri.preprocessing.modules.load_modules(user_module_paths=['user/modules'])
        env=dmri.preprocessing.modules.generate_module_envionrment(modules)
        logger(yaml.dump(env))


        out_filename=str(Path('_data/environment-test.yml').absolute())
        logger("Writing test environment file : {}".format(out_filename),dmri.preprocessing.Color.PROCESS)
        yaml.dump(env,open(out_filename,'w'))

        return True
    except Exception as e:
        logger("Exception occurred :{}".format(str(e)))
        traceback.print_exc()
        return False

def image_padding_test():
    try:
        fname_nrrd="../../../testdata-dtiprep/CT-00006_DWI_dir79_APPA.nrrd"
        img=DWI(fname_nrrd)
        img.zeroPad([2,0,0,1])
        img.writeImage('./output.nii.gz')

        return True
    except Exception as e:
        exc=traceback.format_exc()
        print("Exception {} : {}".format(str(e),exc))
        return False

def run_tests(testlist: list):
    for idx,t in enumerate(testlist):
        c=dmri.preprocessing.Color.BLACK+dmri.preprocessing.Color.BOLD
        logger("---------------------------------------",c)
        logger("--------- {}/{} - Running : {}".format(idx+1,len(testlist),t),c)
        logger("---------------------------------------",c)
        if eval(t)() : logger("[{}/{}] : {} - Success".format(idx+1,len(testlist),t))
        else: logger("[{}/{}] : {} - Failed".format(idx+1,len(testlist),t))

def image_conversion_test():
    fname_nrrd = "../../../testdata-dtiprep/CT-00006_DWI_dir79_APPA.nrrd"
    fname_nifti = "../../../testdata-dtiprep/CT-00006_DWI_dir79_APPA.nii.gz"
    outname_nrrd = "../../../out.nrrd"
    outname_nifti = "../../../out.nii.gz"
    ## nrrd to nifti to nrrd
    nrrd_img = dmri.preprocessing.dwi.DWI(fname_nrrd)
    nifti_img= dmri.preprocessing.dwi.DWI(fname_nifti)
    print(nrrd_img.information['space_directions'])
    print(nifti_img.information['space_directions'])
    nifti_img.writeImage(outname_nrrd,dest_type="nrrd")
    print("Testing Nifti to Nrrd")
    os.system("unu head {} | grep 'space directions'".format(outname_nrrd))
    print("Testing Nrrd to Nifti and back to Nrrd")
    nrrd_img.writeImage(outname_nifti,dest_type="nifti")
    nifti_img=dmri.preprocessing.dwi.DWI(outname_nifti)
    nifti_img.writeImage(outname_nrrd,dest_type="nrrd",dtype="short")
    os.system("unu head {} | grep 'space directions'".format(outname_nrrd))

if __name__=='__main__':
    current_dir=Path(__file__).parent
    parser=argparse.ArgumentParser()
    parser.add_argument('--log',help='log file',default=str(current_dir.joinpath('./log.txt')))
    parser.add_argument('--log-timestamp',help='Add timestamp in the log', default=False, action="store_true")
    parser.add_argument('-n','--no-verbosity',help='Add timestamp in the log', default=True, action="store_false")
    args=parser.parse_args()
    # dmri.preprocessing.logger.setLogfile(args.log)
    # dmri.preprocessing.logger.setTimestamp(args.log_timestamp)
    # dmri.preprocessing.logger.setVerbosity(args.no_verbosity)
    
    tests=['io_test','protocol_test','environment_test','image_padding_test','image_conversion_test']
    run_tests(tests[4:])
