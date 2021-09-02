

import dmri.preprocessing as prep
import yaml
from pathlib import Path

###
import numpy as np
import ants 
import antspynet 

logger=prep.logger.write

class BRAIN_Mask(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger("Under implementation",prep.Color.ERROR)
        # << TODOS>>
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        self.baseline_threshold=protocol_options['baseline_threshold']
        res=self.run_mask(method=self.protocol['method'],
                          modality=self.protocol['modality'])
        self.result['output']['success']=True
        return self.result


    def mask_antspynet(self,params):
        logger("AntsPyNet is running ...",prep.Color.INFO)
        res=None
        input_image_path=Path(self.output_dir).joinpath("input.nii.gz").__str__()
        output_mask_path=Path(self.output_dir).joinpath("mask.nii.gz").__str__()

        src_image=params['image']
        modality=params['modality']
        src_image.writeImage(input_image_path,dest_type='nifti')
        ants_image=ants.image_read(input_image_path)
        # print(ants_image)
        ### test to be deleted
        # logger("Test routine",prep.Color.WARNING)
        # temp_nrrd_path=Path(self.output_dir).joinpath("input_directsave.nrrd").__str__()
        # src_image.writeImage(temp_nrrd_path,dest_type='nrrd')

        # temp_path=Path(self.output_dir).joinpath("input_resave.nii.gz").__str__()
        # img=self.loadImage(input_image_path)
        # img.writeImage(temp_path)
        # temp_nrrd_path=Path(self.output_dir).joinpath("input_resave.nrrd").__str__()
        # img.writeImage(temp_nrrd_path,dest_type='nrrd')

        logger("Reduce to 3D volume for masking",prep.Color.INFO)
        # idwi=self.image.idwi(self.baseline_threshold)
        idwi=self.image.directAverage()
        ants_image_3d=ants.from_numpy(data=idwi)
        ants_image_3d.set_origin(list(ants_image.origin)[:3])
        ants_image_3d.set_spacing(list(ants_image.spacing)[:3])
        new_dir=np.resize(ants_image.direction,[4,4])[:3,:3]
        ants_image_3d.set_direction(new_dir.tolist())

        logger("Computing probability mask ...",prep.Color.INFO)
        probability_mask=antspynet.brain_extraction(ants_image_3d,modality)
        logger("Generating thresholded mask ...",prep.Color.INFO)
        mask=ants.threshold_image(probability_mask,
                                  low_thresh=0.5,
                                  high_thresh=1.0,
                                  inval=1,
                                  outval=0)
        logger("Writing mask file",prep.Color.PROCESS)
        ants.image_write(mask, output_mask_path)
        return res 

    def mask_fslbet(self,params):
        logger("FSL bet is running ...",prep.Color.INFO)
        res=None
        return res

    def run_mask(self,method, modality):
        res=None 
        params={}
        logger("Mask is being computed ... ",prep.Color.PROCESS)
        if method=='fsl':
            res=self.mask_fslbet(params)
        elif method=='antspynet':
            params={
                'image': self.image,
                'modality': modality 
            }
            res=self.mask_antspynet(params)
        logger("Mask generation is completed",prep.Color.OK)
        return res;


