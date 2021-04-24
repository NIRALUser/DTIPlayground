

import dmri.preprocessing as prep

import numpy as np
import nrrd
import dipy
import dipy.io.image as dii
import yaml
from pathlib import Path
import copy

#
#
# gradients are unit-vectors normalized according to b-value (nrrd), there is also normalized gradient coupled with bvalue
#
#

logger=prep.logger.write

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
            bval=float(np.sum(vec**2)*info['b_value'])
            normalize_term=np.sqrt(np.sum(vec**2))
            if normalize_term>0:
                unit_vec=(vec/normalize_term)
            else:
                unit_vec=vec 
            gradients.append({'index':idx,'gradient':vec.tolist(),'b_value':bval,'unit_gradient':unit_vec.tolist(),'original_index':idx})
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
        normalized_vecs.append(np.array(list(map(lambda x: float(x), bvec.split(' ')))).tolist())
        bvals.append(float(bval))

    max_bval=np.max(bvals)
    for idx,vec in enumerate(normalized_vecs):
        denormalized_vec=np.array(vec)*np.sqrt((bvals[idx]/max_bval))
        gradients.append({'index':int(idx),
                          'gradient': denormalized_vec.tolist(),
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
        logger("Not a supported image type",prep.Color.ERROR)
        return None

def get_nrrd_gradient_axis(kinds):
    grad_axis=0
    for idx,k in enumerate(kinds):
        if k.lower() != "domain" and k.lower() != 'space':
            grad_axis=idx 
    return grad_axis

def export_nrrd_to_nrrd(image): #nrrd loaded image to nrrd format (prep.dwi.DWI object)
    if image.image_type.lower() != 'nrrd': raise Exception("Nrrd type image is required for this function")
    info=image.information
    grad=image.getGradients()
    
    new_data=copy.deepcopy(image.images)
    org_header=copy.deepcopy(dict(image.original_data[1]))
    grad_axis_original=get_nrrd_gradient_axis(org_header['kinds'])
    grad_axis=-1

    new_header=copy.deepcopy(org_header)
    s=list(new_data.shape)
    new_header['dimension']=len(new_data.shape)
    g=s[grad_axis]
    s=s[:grad_axis]+s[grad_axis:-1]
    s=s[:grad_axis_original]+[g]+s[grad_axis_original:]
    new_header['sizes']=s
    copy_hdr=copy.deepcopy(new_header)
    for k,v in copy_hdr.items():    
        if 'dwmri_gradient' in k.lower():
            del new_header[k]
    for idx,g in enumerate(grad):
        k="DWMRI_gradient_{:04d}".format(idx)
        new_header[k]=" ".join([str(x) for x in g['gradient']])
    new_data=np.moveaxis(new_data,grad_axis,grad_axis_original)
    return new_data,new_header

def _write_dwi(filename,image , dest_type='nrrd'): ## image : image object (prep.dwi.DWI)
    if dest_type.lower()=='nrrd': ## load nrrd dwi image
        if image.image_type=='nrrd':
            data,header = export_nrrd_to_nrrd(image)
        else:
            raise Exception("Not implemented yet")
        return nrrd.write(filename,data,header=header)
    elif dest_type.lower()=='nifti':
        raise Exception("Not implemented yet")
        logger("Not a supported image type",prep.Color.ERROR)
        return False
    else:
        logger("Not a supported image type",prep.Color.ERROR)
        raise Exception("Not a supported image type")
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
    
    @prep.measure_time
    def writeImage(self,filename,dest_type='nrrd'):
        out_images=None
        if '.nrrd' in filename.lower(): 
            dest_type='nrrd'
        if '.nii' in filename.lower(): 
            dest_type='nifti'
    
        logger("Writing image to : {}".format(str(filename)),prep.Color.PROCESS)
        _write_dwi(filename,self,dest_type=dest_type)
        logger("Image written.",prep.Color.OK)

    @prep.measure_time
    def loadImage(self,filename,filetype=None):
        if '.nrrd' in filename.lower(): self.image_type='nrrd'
        if '.nii' in filename.lower(): self.image_type='nifti'
        if filetype is not None:
            self.image_type=filetype
        self.images,self.gradients,self.information ,self.original_data = _load_dwi(filename,self.image_type)
        #self.update_information()
        logger("Image - {} loaded".format(self.filename),prep.Color.OK,terminal_only=True)
        #if prep._debug: logger(yaml.dump(self.information))

    def setB0Threshold(self,b0_threshold):
        self.b0_threshold=b0_threshold


    def getB0Threshold(self):
        return self.b0_threshold

    def setGradients(self,gradients:list):
        _,_,_,g = self.images.shape 
        if g != len(gradients):
            logger("[ERROR] Gradients in the image doesn't match to the direction number of the gradient file",prep.Color.ERROR)
            logger("Number of gradients from image file : {}, Number of gradients from gradient file : {}".format(g,len(gradients)),prep.Color.ERROR)
            raise Exception("Gradients in the image doesn't match to the direction number of the gradient file")
        else:
            self.gradients=gradients 

    def getAffineMatrix(self):
        affine=np.transpose(np.append(self.information['space_directions'],
                                     np.expand_dims(self.information['space_origin'],0),
                                     axis=0))
        affine=np.append(affine,np.array([[0,0,0,1]]),axis=0)
        return affine 

    def getAffineMatrixForSlice(self,column=2): # 0 for x, 1 for y , 2 for z  output 2d affine matrix (3x3)
        affine=self.getAffineMatrix()
        new_mat=np.delete(affine,column,axis=0)
        new_mat=np.transpose(np.delete(np.transpose(new_mat),column,axis=0))
        return new_mat

    def loadGradients(self,filename):
        self.gradients=yaml.safe_load(open(filename,'r'))

    def loadImageInformation(self,filename):
        self.information=yaml.safe_load(open(filename,'r'))

    def getGradients(self,b0_threshold=None):
        if b0_threshold is None:
            b0_threshold=self.b0_threshold

        for idx,e in enumerate(self.gradients):
            self.gradients[idx]['index']=idx
            self.gradients[idx]['baseline']=bool(e['b_value']<=b0_threshold)

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
                 'gradient': g['gradient'],
                 'unit_gradient': g['unit_gradient'],
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

    def getBaselines(self,b0_threshold=None):
        grads=self.getGradients(b0_threshold)
        baseline_gradients=[x for x in grads if x['baseline']]
        baseline_indexes=[x['index'] for x in baseline_gradients]
        baseline_volumes=self.images[:,:,:,baseline_indexes]
        return baseline_gradients, baseline_volumes

    def gradientSummary(self):
        grads=self.getGradients()
        num_baselines=len([x for x in grads if x['baseline']])
        num_gradients=len(grads)
        res={
            "number_of_baselines": num_baselines,
            "number_of_gradients": num_gradients
        }
        return res
        

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

    def insertGradient(self,gradient,image_volume,pos=-1):
        self.images=np.insert(self.images,pos,image_volume,axis=3)
        self.gradients.insert(pos,gradient)
        self.update_information()

    def update_information(self):
        ## here goes anything to update when there is any changes on self.images
        self.information['sizes']=list(self.images.shape )
        self.information['image_size']=list(self.images.shape[:3])
        self.getGradients()
        ## reindexing



        
        

