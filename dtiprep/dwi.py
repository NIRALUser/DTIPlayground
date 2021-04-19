import numpy as np
import nrrd
import dipy
import dipy.io.image as dii
import matplotlib.pyplot as plt
import yaml
from pathlib import Path
import dtiprep
import copy

#
#
# gradients are unit-vectors normalized according to b-value (nrrd), there is also normalized gradient coupled with bvalue
#
#

logger=dtiprep.logger.write

def _load_nrrd(filename):
    org_data,header = nrrd.read(filename)
    
    ## dimension checkout
    kinds=[]
    grad_axis=0
    for idx,k in enumerate(header['kinds']):
        if k.lower() != "domain" and k.lower() != 'space':
            grad_axis=idx 
            kinds.append(False)
        else:
            kinds.append(True)
    ## extract image size 
    img_size=[]
    space_directions=[]
    grad_size=None
    for idx,k in enumerate(kinds):
        if k: 
            img_size.append(list(header['sizes'].tolist()))
            space_directions.append(header['space directions'].tolist()[idx])
        else:
            grad_size=header['sizes'][idx]
    img_size.append(grad_size)


    info={
        'space':header['space'],
        'dimension': int(header['dimension']),
        'sizes': list(img_size), #header['sizes'],
        'kinds': header['kinds'],
        'kinds_space' : kinds,
        'image_size' : list(img_size[:3]),
        'b_value':float(header['DWMRI_b-value']),
        'space_directions': space_directions,
        'measurement_frame':header['measurement frame'].tolist(),
        'space_origin':header['space origin'].tolist()
    }
    if "thicknesses" in header :
        info['thicknesses'] = header['thicknesses'].tolist()

    ### move axis to match nifti
    data=np.moveaxis(org_data.copy(),grad_axis,-1)
    info['sizes']=data.shape
    info['image_size']=data.shape[0:3]
    ### extracting gradients
    gradients=[]
    for k,v in header.items():
        if 'DWMRI_gradient' in k:
            idx=int(k.split('_')[2])
            vec=np.array(list(map(lambda x: float(x),v.split())))
            bval=np.sum(vec**2)*info['b_value']
            unit_vec=(vec/np.sqrt(np.sum(vec**2)))
            gradients.append({'index':idx,'gradient':vec,'b_value':bval,'unit_gradient':unit_vec,'original_index':idx})
    gradients=sorted(gradients,key=lambda x: x['index'])
    return data,gradients,info , (org_data,header)

def _load_nifti(filename,bvecs_file=None,bvals_file=None):
    parent_dir=Path(filename).parent
    if bvals_file is None: bvals_file=parent_dir.joinpath(Path(Path(filename).stem).stem+'.bvals')
    if bvecs_file is None: bvecs_file=parent_dir.joinpath(Path(Path(filename).stem).stem+'.bvecs')
        
    gradients=None

    ## extract gradients with form {'index': , 'gradient': }
    bvals=[]
    bvecs=[]
    bvpairs=list(zip(open(bvals_file,'r').readlines(),open(bvecs_file,'r').readlines()))
    gradients=[]
    normalized_vecs=[]
    vecs=[]
    max_bval=0.0
    for idx,bv in enumerate(bvpairs):
        bval,bvec = bv
        normalized_vecs.append(np.array(list(map(lambda x: float(x), bvec.split(' ')))))
        bvals.append(float(bval))

    max_bval=np.max(bvals)
    for idx,vec in enumerate(normalized_vecs):
        denormalized_vec=vec*np.sqrt((bvals[idx]/max_bval))
        gradients.append({'index':idx,
                          'gradient': denormalized_vec,
                          'b_value': bvals[idx],
                          'unit_gradient': vec,
                          'original_index':idx})

    ## move gradient index to the first (same to nrrd format)
    org_data, affine, header= dipy.io.image.load_nifti(filename,return_img=True)
    data=org_data.copy()

    ## extract header info
    mat=np.array(header.affine)
    space=""
    if mat[0,0]<0.0 : space+='left-'
    else: space+='right-'
    if mat[1,1]<0.0 : space+='posterior-'
    else: space+='anterior-'
    if mat[2,2]<0.0 : space+='inferior'
    else: space+='superior'

    flipops=np.array(   ## x,y will be flipped
            [[-1,0,0],
             [0,-1,0],
             [0,0,1]])
    space_directions=np.matmul(mat[:3,:3],flipops)[:3,:3]
    space_origin=np.matmul(mat[:3,3],flipops)[:3]
    info={
        'space': space,
        'dimension': len(data.shape),
        'sizes': np.array(data.shape).tolist(),
        'image_size' : np.array(data.shape[0:3]).tolist(),
        'b_value': float(max_bval),
        'space_directions': space_directions.tolist(),
        'measurement_frame': np.identity(3).tolist(), ## this needs to be clarified for nifti
        'space_origin':space_origin.tolist()
    }
        
    return data, gradients, info, (org_data,affine,header)

def _load_dwi(filename, filetype='nrrd'):
    if filetype.lower()=='nrrd': ## load nrrd dwi image
        return _load_nrrd(filename)
    elif filetype.lower()=='nifti':
        return _load_nifti(filename)
    else:
        logger("Not a supported image type",dtiprep.Color.ERROR)
        return None


def _write_dwi(filename,images,header,filetype='nrrd'):
    if filetype.lower()=='nrrd': ## load nrrd dwi image
        return nrrd.write(filename,images,header=header)
    elif filetype.lower()=='nifti':
        logger("Not a supported image type",dtiprep.Color.ERROR)
        return False
    else:
        logger("Not a supported image type",dtiprep.Color.ERROR)
        return False
    
class DWI:
    def __init__(self,filename,b0_threshold=10,filetype=None,**kwargs):
        ## file information
        self.filename=filename
        
        ## Processed data 
        self.images=None #image tensors [ size x, size y, size z , gradient index]
        self.gradients=None #gradient {'index': , 'gradient' : }
        self.information=None #other image information such as b value , origin, ...
        self.b0_threshold=b0_threshold
        
        ## image specific data (not to be used in computation)
        self.image_type=filetype
        self.original_data=None #Original Data returned from each file type
        
        ## load image
        self.loadImage(self.filename,self.image_type)
        
    def __getitem__(self,index):
        return self.images[index,:,:,:], self.gradients[index]
    def __len__(self):
        return len(self.gradients)
    
    @dtiprep.measure_time
    def writeImage(self,filename,filetype=None):
        imgtype='nrrd'
        out_images=None
        if '.nrrd' in filename.lower(): 
            imgtype='nrrd'
            out_images=np.moveaxis(self.images.copy(),-1,0)
        if '.nii' in filename.lower(): 
            imgtype='nifti'
            out_images=self.images      
        if filetype is not None:
            imgtype=filetype
        logger("Writing image to : {}".format(str(filename)),dtiprep.Color.PROCESS)
        _write_dwi(filename,out_images,self.information,filetype=imgtype)
        logger("Image written.",dtiprep.Color.OK)
       
    @dtiprep.measure_time
    def loadImage(self,filename,filetype=None):
        if '.nrrd' in filename.lower(): self.image_type='nrrd'
        if '.nii' in filename.lower(): self.image_type='nifti'
        if filetype is not None:
            self.image_type=filetype
        self.images,self.gradients,self.information ,self.original_data = _load_dwi(filename,self.image_type)
        #self.update_information()
        logger("Image - {} loaded".format(self.filename),dtiprep.Color.OK,terminal_only=True)
        #if dtiprep._debug: logger(yaml.dump(self.information))

    def setB0Threshold(self,b0_threshold):
        self.b0_threshold=b0_threshold
        self.getGradients()
    def getB0Threshold(self):
        return self.b0_threshold

    def getGradients(self):
        for e in self.gradients:
            e['baseline']=bool(e['b_value']<=self.b0_threshold)
        return self.gradients

    def dumpInformation(self,filename):
        info=self.information

        yaml.dump(info,open(filename,'w'))       
    def dumpGradients(self,filename):
        grad=self.getGradients()
        out_grad=[]
        for g in grad:
            temp={'index': int(g['index']),
                 'original_index': int(g['original_index']),
                 'b_value' : float(g['b_value']),
                 'gradient': g['gradient'].tolist(),
                 'unit_gradient': g['unit_gradient'].tolist(),
                 "baseline" : bool(g['baseline'])
            }
            out_grad.append(temp)
        yaml.dump(out_grad,open(filename,'w'))

    def isGradientBaseline(self,gradient_index:int):
        return self.getGradients()[gradient_index]['baseline']

    def getBValueBounds(self):
        grad=self.getGradients()
        min_b= float(np.min([x['b_value'] for x in grad]) )
        max_b= float(np.max([x['b_value'] for x in grad]) )
        return [min_b,max_b]

    def convertToOriginalGradientIndex(self,grad_indexes:list): # from actual index to original gradient index list
        
        out=[]
        grad=self.getGradients()
        for idx in grad_indexes:
            out.append(grad[idx]['original_index'])
        return out 

    def deleteGradientsByOriginalIndex(self, original_indexes: list): #remove gradiensts and delete images corresponding to those gradients, list of gradient indexes
        ## remove gradient slices
        remove_list=[]
        grad=self.getGradients()
        for idx,g in enumerate(grad):
            if g['original_index'] in original_indexes:
                remove_list.append(idx)
        self.deleteGradients(remove_list)

    def deleteGradients(self,remove_list: list): #remove gradiensts and delete images corresponding to those gradients, list of gradient indexes
        ## remove gradient slices
        self.images=np.delete(self.images,remove_list,3)
        self.gradients=list(filter(lambda x: x['index'] not in remove_list, self.gradients))
        for idx,g in enumerate(self.gradients):
            g['index']=idx 
        self.update_information()


    def update_information(self):
        ## here goes anything to update when there is any changes on self.images
        self.information['sizes']=list(self.images.shape )
        self.information['image_size']=list(self.images.shape[:3])
        ## reindexing



        
        

