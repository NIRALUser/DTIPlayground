

import dtiplayground.dmri.preprocessing as prep
import yaml
from pathlib import Path

###
import numpy as np

logger=prep.logger.write

class TEST(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.global_variables, self.softwares, self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        sourceImageInformation=self.getSourceImageInformation()
        # << TODOS>>
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        self.baseline_threshold=protocol_options['baseline_threshold']
        res=self.run_test(testlist=self.protocol['test_list'])
        self.result['output']['success']=True
        return self.result


    def run_test(self,testlist):
        res=None 
        params={}
        logger("Test is running... ",prep.Color.PROCESS)
        params={
            "image":self.image
        }
        num_test=len(testlist)
        for idx,test in enumerate(testlist):
            logger("-----------------------------------------\n{}/{}  {} is running ...\n-----------------------------------------".format(idx+1,num_test,test['name']))
            logger("------- OPTIONS-------\n{}".format(yaml.dump(test['options'])),prep.Color.DEV)
            func=getattr(self,test['name'])
            res=func(params,test['options'])
        logger("Test is completed",prep.Color.OK)
        return res;

### test functions 

    def image_io_test(self,params,options):
        
        res=None
        src_image=params['image']
        input_image_path=Path(self.output_dir).joinpath("input.nii.gz").__str__()
        src_image.writeImage(input_image_path,dest_type='nifti')
        temp_nrrd_path=Path(self.output_dir).joinpath("input_directsave.nrrd").__str__()
        src_image.writeImage(temp_nrrd_path,dest_type='nrrd')
        temp_path=Path(self.output_dir).joinpath("input_resave.nii.gz").__str__()
        img=self.loadImage(input_image_path)
        img.writeImage(temp_path)
        temp_nrrd_path=Path(self.output_dir).joinpath("input_resave.nrrd").__str__()
        img.writeImage(temp_nrrd_path,dest_type='nrrd')

        return res 

    def global_variable_test(self, params, options):
        print(yaml.dump(self.global_variables))
        return True

