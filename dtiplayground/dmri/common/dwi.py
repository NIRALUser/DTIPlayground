

import dtiplayground.dmri.common as common
import numpy as np
import nrrd
import nibabel as nib

import yaml
from pathlib import Path
import copy

#
#
# gradients are unit-vectors normalized according to b-value (nrrd), there is also normalized gradient coupled with bvalue
#
#

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def normalize(v):
    norm = np.linalg.norm(v)
    if norm == 0: 
       return v
    return v / norm

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
    img_size=list(header['sizes'])
    space_directions=[]
    grad_size=None
    space_matrix = np.zeros((3,3))
    for idx,k in enumerate(kinds):
        if k: 
            # img_size.append(list(header['sizes'].tolist()))
            space_directions.append(header['space directions'].tolist()[idx])
        else:
            grad_size=header['sizes'][idx]
    info={
        'space':header['space'],
        'dimension': int(header['dimension']),
        'sizes': list(map(int, img_size)), #header['sizes'],
        'original_kinds': header['kinds'],
        'original_kinds_space' : kinds,
        'image_size' : list(map(int,img_size[:3])),
        # 'b_value':float(header['DWMRI_b-value']),
        'space_directions': space_directions,
        'space_origin':header['space origin'].tolist(),
        #'original_centerings': header['centerings'],
        'endian' : header['endian'],
        'type' : header['type']
    }
    if 'measurement_frame' in header:
        info['measurement_frame'] = header['measurement_frame'].tolist()
    elif 'measurement frame' in header:
        info['measurement_frame'] = header['measurement frame'].tolist()
    else:
        info['measurement_frame'] =  np.identity(3).tolist()
    if 'modality' in header:
        info['modality'] = header['modality']
    else:
        info['modality'] = None

    if 'DWMRI_b-value' in header:
        info['b_value'] = float(header['DWMRI_b-value'])
    else:
        info['b_value'] = None
    if 'centerings' in header:
        info['original_centerings']=header['centerings']
    else:
        info['original_centerings']=None 

    if "thicknesses" in header :
        info['thicknesses'] = header['thicknesses'].tolist()
    else:
        info["thicknesses"] = None

    data=org_data
    ### move axis to match nifti
    if 'DWMRI_b-value' in header: ## only for the dwmri images
        data=np.moveaxis(data,grad_axis,-1)
        info['sizes']=list(data.shape)
        info['image_size']=list(data.shape[0:3])
    ### extracting gradients
    gradients=[]
    measurement_frame = np.array(info['measurement_frame'])
    
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
            # nifti_vec = np.matmul(np.matmul(np.array(space_directions), measurement_frame) , unit_vec) ## ROI
            nifti_vec = np.matmul(np.matmul(np.array(space_directions), measurement_frame.transpose()) , unit_vec) ## ROI, inverting measurement frame by transposing (identical to inversion)
            normalize_term=np.sqrt(np.sum(nifti_vec**2))
            if normalize_term>0:
                nifti_grad = nifti_vec / normalize_term
            else:
                nifti_grad = nifti_vec

            # nifti_grad[1] = -nifti_grad[1] # flipping y axis
            gradients.append({'index':idx,
                              'gradient':vec.tolist(),
                              'b_value':bval,
                              'unit_gradient':unit_vec.tolist(),
                              'original_index':idx,
                              'nifti_gradient':nifti_grad.tolist()})
    gradients=sorted(gradients,key=lambda x: x['index'])
    return data,gradients,info , (org_data,header)

def _load_nifti_bvecs(filename):
    content=open(filename,'r').read().strip()
    num_gradients=len(content.split())/3
    is_old_format= len(content.split('\n'))!=num_gradients 
    if is_old_format:
        x,y,z=content.strip().split('\n')
        x=x.split()
        y=y.split()
        z=z.split()
        return list(zip(x,y,z))
    else:
        return list(chunks(content.split(),3))

def _load_nifti(filename,bvecs_file=None,bvals_file=None):
    parent_dir=Path(filename).parent
    if bvals_file is None: bvals_file=parent_dir.joinpath(Path(Path(filename).stem).stem+'.bval')
    if bvecs_file is None: bvecs_file=parent_dir.joinpath(Path(Path(filename).stem).stem+'.bvec')

    if not bvals_file.exists():
        bvals_file=parent_dir.joinpath(Path(Path(filename).stem).stem+'.bvals')
    if not bvecs_file.exists():
        bvecs_file=parent_dir.joinpath(Path(Path(filename).stem).stem+'.bvecs')
    
    loaded_image_object= nib.load(filename)
    header=loaded_image_object.header
    org_data=loaded_image_object.get_fdata().astype(np.dtype(header.get_data_dtype()))
    image_dim = len(org_data.shape)
    gradients=None

    ## extract gradients with form {'index': , 'gradient': }
    bvals=[]
    bvecs=[]
    gradients=[]
    max_bval=0.0
    affine=loaded_image_object.affine 
    ijk_to_lps = affine
    lps_to_ras = np.diag([-1, -1, 1, 1]) # ras to lps 
    ijk_to_ras = np.matmul(lps_to_ras, ijk_to_lps)
    affine=ijk_to_ras

    inv_space_mat = np.linalg.inv(affine[0:3,0:3].astype('float64'))#.transpose()
    if image_dim == 4:
        tmp_bvals=list(open(bvals_file,'r').read().split())
        tmp_bvecs=_load_nifti_bvecs(bvecs_file)
        bvpairs=list(zip(tmp_bvals,tmp_bvecs))
        normalized_vecs=[]
        vecs=[]
        
        for idx,bv in enumerate(bvpairs):
            bval,bvec = bv
            normalized_vecs.append(list(map(lambda x :float(x),bvec)))
            bvals.append(float(bval))


        max_bval=np.max(bvals)
        for idx,vec in enumerate(normalized_vecs):
            unit_vec = normalize(np.matmul(inv_space_mat, np.array(vec))) # for nifti -> nrrd transform on the gradients
            denormalized_vec=np.array(unit_vec)*np.sqrt((bvals[idx]/max_bval))
            gradients.append({'index':int(idx),
                              'gradient': denormalized_vec.tolist(),
                              'b_value': bvals[idx],
                              'unit_gradient': unit_vec.tolist(),
                              'original_index':idx,
                              'nifti_gradient':vec})

    ## move gradient index to the first (same to nrrd format)
    
    data=org_data

    ## extract header info
    mat=np.array(affine)

    space='left-posterior-superior'

    space_directions=mat[:3,:3] ## transpose for taking row vectors, not column vectors
    space_origin=mat[3,:3] ## column to row vector
    endian="little"
    if header.endianness != '<' :
        endian='big'

    info={
        'space': space,
        'dimension': len(data.shape),
        'sizes': np.array(data.shape).tolist(),
        "original_kinds": ['space','space','space','list'][:image_dim],
        "original_kinds_space" : [True,True,True,False][:image_dim], ## image space = True, gradient dim = False
        'image_size' : np.array(data.shape[0:3]).tolist(),
        'b_value': float(max_bval),
        'space_directions': space_directions.tolist(),
        'measurement_frame': np.identity(3).tolist(), ## this needs to be clarified for nifti
        'space_origin':space_origin.tolist(),
        'type': str(header.get_data_dtype()),
        'endian' : endian,
        'original_centerings' : ['cell','cell','cell','???'][:image_dim],
        'thicknesses' : np.array([np.NAN,np.NAN,np.abs(space_directions.tolist()[2][2]),np.NAN]).tolist()[:image_dim],
        'modality': None
    }



    return data, gradients, info, (org_data,affine,header)

def _load_dwi(filename, filetype='nrrd'):
    if filetype.lower()=='nrrd': ## load nrrd dwi image
        return _load_nrrd(filename)
    elif filetype.lower()=='nifti':
        return _load_nifti(filename)
    else:
        logger("Not a supported image type",common.Color.ERROR)
        return None

def get_nrrd_gradient_axis(kinds):
    grad_axis=0
    for idx,k in enumerate(kinds):
        if k.lower() != "domain" and k.lower() != 'space':
            grad_axis=idx 
    return grad_axis



def export_to_nrrd(image): #image : DWI
    info=copy.copy(image.information)
    grad=image.getGradients()
    new_data=copy.copy(image.images)
    grad_axis_original=get_nrrd_gradient_axis(info['original_kinds'])
    grad_axis=-1
    
    space_directions=info['space_directions']
    if image.information['dimension']>3:
        space_directions.append([np.NAN,np.NAN,np.NAN])
        space_directions_grad_axis=space_directions[grad_axis]
        space_directions=np.insert(space_directions,
                                    grad_axis_original,
                                    space_directions_grad_axis,
                                    axis=0)
        space_directions=np.delete(space_directions,-1,axis=0)
        space_directions=space_directions.tolist()
        

    new_header={
        "type": info['type'],
        "dimension": info['dimension'],
        "space":  info['space'],
        "sizes":  info['sizes'],
        "space directions": space_directions,
        "kinds": info['original_kinds'],
        "endian" : info['endian'],
        "encoding" : 'gzip',
        "space origin" : info['space_origin'],
        "measurement frame": info['measurement_frame']
    }
    if 'modality' in info:
        new_header['modality']=info['modality']
    else:
        new_header['modality']=None
    if info['dimension'] == 4 and info['modality'] != 'DTI' and info['b_value'] is not None:
        new_header['modality']="DWMRI"
        new_header['DWMRI_b-value']=info['b_value']

    if info['original_centerings'] is not None:
        new_header["centerings"]= info['original_centerings'] 
    if info['thicknesses'] is not None:
        new_header['thicknesses']= info['thicknesses']


    s=list(new_data.shape)
    new_header['dimension']=len(new_data.shape)
    if new_header['dimension'] > 3:
        g=s[grad_axis]
        s=s[:grad_axis]+s[grad_axis:-1]
        s=s[:grad_axis_original]+[g]+s[grad_axis_original:]
    new_header['sizes']=s

    copy_hdr=copy.copy(new_header)
    for k,v in copy_hdr.items():    
        if 'dwmri_gradient' in k.lower():
            del new_header[k]
    if new_header['modality']=='DWMRI':
        for idx,g in enumerate(grad):
            k="DWMRI_gradient_{:04d}".format(idx)
            new_header[k]=" ".join([str(x) for x in g['gradient']])
        if new_header['dimension'] > 3:
            new_data=np.moveaxis(new_data,grad_axis,grad_axis_original)
    new_data=new_data.astype(new_header['type'])
    return new_data,new_header 


def flipY(x):
    return [x[0],-x[1],x[2]]


def export_to_nifti(image): # image DWI
    affine=image.getAffineMatrixForNifti()
    rotation = affine[0:3,0:3]
    measurement_frame = image.information['measurement_frame']
    img=image.images 
    gradients=image.getGradients()
    bvals=["{:d}\n".format(int(round(x['b_value']))) for x in gradients]
    bvecs=[" ".join(map(lambda s : "{:.8f}".format(s),x['nifti_gradient']))+"\n" for x in gradients]
    return img,affine, bvals, bvecs

def _write_nrrd(image,filename,dtype): 
    image.information['type']=dtype
    data,header = export_to_nrrd(image)
    return nrrd.write(filename,data,header=header)

def _write_nifti(image,filename,dtype): #image : DWI
    data,affine,bvals,bvecs=export_to_nifti(image)
    out_dir=Path(filename).parent
    filename_stem=Path(filename).name.split('.')[0]
    bvals_filename=out_dir.joinpath(filename_stem+".bval")
    bvecs_filename=out_dir.joinpath(filename_stem+".bvec")
    data=data.astype(dtype)
    out_image_object=nib.Nifti1Image(data,affine)
    nib.save(out_image_object,str(filename))
    ## wrting bvals, bvecs
    with open(bvals_filename.__str__(),'w') as f:
        f.writelines(bvals)
    with open(bvecs_filename.__str__(),'w') as f:
        f.writelines(bvecs)


def _write_dwi(filename,image , dest_type='nrrd',dtype='short'): ## image : image object (common.dwi.DWI)
    if dest_type.lower()=='nrrd': ## load nrrd dwi image
        return _write_nrrd(image,filename,dtype=dtype)
    elif dest_type.lower()=='nifti':
        return _write_nifti(image, filename,dtype=dtype)
    else:
        logger("Not a supported image type",common.Color.ERROR)
        raise Exception("Not a supported image type")
        return False
    
class DWI:
    def __init__(self,filename=None,b0_threshold=10,filetype=None,**kwargs):
        ## file information
        kwargs.setdefault('logger',common.logger);
        self.logger = kwargs['logger']
        global logger
        logger = self.logger.write

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
        if self.filename is not None:
            self.loadImage(self.filename,self.image_type)
        
    def __getitem__(self,index):
        return self.images[index,:,:,:], self.gradients[index]
    def __len__(self):
        return len(self.gradients)
    
    def copyFrom(self,dwi,image=False,gradients=False):
        self.filename = dwi.filename
        if image:
            self.images=dwi.images
        if gradients:
            self.gradients=dwi.gradients
        self.information = dwi.information
        self.image_type = dwi.image_type
        self.oritinal_data = dwi.original_data

    @staticmethod
    def mergeImages(*imgs):
        merged=copy.copy(imgs[0])
        num_grads = merged.images.shape[-1]
        for idx,img in enumerate(imgs):
            if idx>0:
                temp_ngrads = img.images.shape[-1]
                num_grads = num_grads + temp_ngrads
                merged.images = np.concatenate((merged.images,img.images),axis=-1)
                merged.gradients = merged.gradients+img.gradients
        logger('Images merged',common.Color.OK)
        return merged

    def updateImage3D(self, img):
        self.images = img
        self.information['sizes'] = list(img.shape)
        self.information['dimension'] = len(img.shape)
        self.information['kinds'] = ['domain','domain','domain']
        self.information['original_kinds'] = ['domain','domain','domain']

    def setImage(self,img, modality='DWMRI', kinds = ['space','space','space','list']):
        self.information['sizes'] = list(img.shape)
        self.information['kinds'] = kinds
        self.information['original_kinds'] = kinds
        self.information['dimension'] = len(img.shape)
        self.information['modality'] = modality
        self.images = img
        self.gradients=[]

    @common.measure_time
    def writeImage(self,filename,dest_type=None,dtype='short'):
        if not dest_type:
            if '.nrrd' in filename.lower(): 
                dest_type='nrrd'
            if '.nii' in filename.lower(): 
                dest_type='nifti'
        
        logger("Writing image {} to : {}".format(dest_type,str(filename)),common.Color.PROCESS)
        _write_dwi(filename,self,dest_type=dest_type,dtype=dtype)
        logger("Image written.",common.Color.OK)

    @common.measure_time
    def loadImage(self,filename,filetype=None):
        # print(self.filename)
        if '.nrrd' in filename.lower(): self.image_type='nrrd'
        if '.nii' in filename.lower(): self.image_type='nifti'
        if filetype is not None:
            self.image_type=filetype
        self.images,self.gradients,self.information ,self.original_data = _load_dwi(filename,self.image_type)
        self.images = self.images.astype(float)
        logger("Image - {} loaded".format(self.filename),common.Color.OK,terminal_only=True)


    def getAffineMatrixForNifti(self):
        return self.getAffineMatrixBySpace('right-anterior-superior')


    def getAffineMatrixBySpace(self,target_space="right-anterior-superior"): #target_space left/right, posterior/anterior, inferior/superior e.g. lef-posterior-superior
        space=self.information['space']
        space_directions=copy.copy(self.information['space_directions'])
        spdir=copy.copy(np.array(space_directions))
        # affine=self.getAffineMatrix()
        space_origin=np.array(self.information['space_origin'])
        affine=np.zeros((4,4))
        affine[0:3,0:3] = spdir[0:3,0:3]
        affine[3,0:4] = np.array([[0,0, 0, 1]])
        affine[0:3,3] = np.array([space_origin])
        # affine=np.append(affine,[space_origin],axis=0)
        # affine=affine.transpose()
        # affine=np.append(affine,np.array([[0,0, 0, 1]]),axis=0)
        src_space_elem = space.split('-')
        target_space_elem = target_space.split('-')
        diag_elements = [1,1,1,1]
        for i,v in enumerate(target_space_elem):
            if v != src_space_elem[i]:
                diag_elements[i]=-1
        ijk_to_lps = affine
        src_to_tgt = np.diag(diag_elements)
        ijk_to_ras = np.matmul(src_to_tgt, ijk_to_lps)
        affine=ijk_to_ras
        return affine

    def setSpaceDirection(self, target_space=None):
        if not target_space:
            return
        affine = self.getAffineMatrixBySpace(target_space=target_space)
        at=affine#.transpose()
        self.information['space_directions']=at[:3,:3].tolist()
        self.information['space_origin']=at[:3,3].tolist()
        self.information['space']=target_space

    def setB0Threshold(self,b0_threshold):
        self.b0_threshold=b0_threshold

    def getB0Threshold(self):
        return self.b0_threshold

    def getB0Index(self):
        grads=self.getGradients()
        b0threshold=self.getB0Threshold()
        res=[]
        for idx,g in enumerate(grads):
            if g['b_value'] <= b0threshold:
                res.append(idx)
        return res 

    def setGradients(self,gradients:list):
        _,_,_,g = self.images.shape 
        if g != len(gradients):
            logger("[ERROR] Gradients in the image doesn't match to the direction number of the gradient file",common.Color.ERROR)
            logger("Number of gradients from image file : {}, Number of gradients from gradient file : {}".format(g,len(gradients)),common.Color.ERROR)
            raise Exception("Gradients in the image doesn't match to the direction number of the gradient file")
        else:
            self.gradients=gradients 

    def getGradients(self,b0_threshold=None):
        if b0_threshold is None:
            b0_threshold=self.b0_threshold

        for idx,e in enumerate(self.gradients):
            self.gradients[idx]['index']=idx
            self.gradients[idx]['baseline']=bool(int(round(e['b_value']))<=b0_threshold)

        return self.gradients

    def removeGradients(self):
        self.gradients=[]
        del self.information['modality']

    def loadGradients(self,filename):
        self.gradients=yaml.safe_load(open(filename,'r'))

    def loadImageInformation(self,filename):
        self.information=yaml.safe_load(open(filename,'r'))


    def dumpInformation(self,filename):
        info=self.information
        yaml.safe_dump(info,open(filename,'w'))       

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
        yaml.safe_dump(out_grad,open(filename,'w'))

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

    def extractBaselines(self,b0_threshold=None):
        new_image=copy.copy(self)
        grads,vols=new_image.getBaselines(b0_threshold)
        new_image.images=vols 
        new_image.setGradients(grads)
        return new_image

    def idwi(self,b0_threshold=None):
        gradients=self.getGradients(b0_threshold)
        num_gradients=len(gradients)
        vol_product=np.ones(self.images.shape[:3],dtype=np.float64)
        for idx,g in enumerate(gradients):
            vol_product*= self.images[:,:,:,idx]
        result_volume=pow(vol_product,1.0/num_gradients)
        return result_volume 

    def directAverage(self):
        result_volume=self.images.mean(axis=3)
        return result_volume 

    def reduceTo3D(self,method="direct_average"):
        if method=='idwi':
            return self.idwi()
        else: 
            return self.directAverage()

    def zerorizeBaselines(self,b0_threshold):
        grads=self.getGradients(b0_threshold)
        for idx,g in enumerate(grads):
            if g['baseline']:
                grads[idx]['b_value']=0
        self.setGradients(grads)

    def zeroPad(self,pad_list:list): ## [0,2,0,0] means padding 2 at axis 1 
        x,y,z,g=self.images.shape
        xa,ya,za,ga=pad_list 
        new_image=np.zeros([x+xa,y+ya,z+za,g+ga],dtype=self.images.dtype)
        
        new_image[:x,:y,:z,:g]=self.images
        self.images=new_image 
        self.information['image_size']=[x+xa,y+ya,z+za]
        self.information['sizes']=[x+xa,y+ya,z+za,g+ga]

        if ga >0 : #if gradient volume is added
            for i in range(ga):
                grad=self.gradients[-1]
                self.gradients.append(grad)

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



        
        

