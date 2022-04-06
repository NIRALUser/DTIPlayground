import dtiplayground.dmri.preprocessing as prep

import numpy as np
import time
from pathlib import Path
import yaml
import os 

logger=prep.logger.write


def ncc_old(x,y):  #normalized correlation
    x=(x-np.mean(x))/np.sqrt(np.sum((x-np.mean(x))**2))
    y=(y-np.mean(y))/np.sqrt(np.sum((y-np.mean(y))**2))
    return np.sum(x*y)

def ncc(x,y): #normalized cross correlation in image (ref: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/ )
    ab=np.sum(x*y)
    a2=np.sum(x**2)
    b2=np.sum(y**2)
    if a2*b2==0.0: 
        return 1.0
    else:
        return ab/np.sqrt(a2*b2)

def _quad_fit(bval, domain=[0,1000], fimage=[3.0,3.5]): #returns std multiple between fimage
    if bval > domain[1] : 
        return fimage[1]
    elif bval < domain[0] : 
        return fimage[0]
    denom=((domain[1]-domain[0])**2)
    a=0
    if denom==0: 
        a=0
    else:
        a= (fimage[1]-fimage[0])/denom
    c= fimage[0]
    return a*(bval**2)+c

def quadratic_fit_generator(domain,fimage):
    def wrapper(bval):
        return _quad_fit(bval,domain,fimage)
    return wrapper

@prep.measure_time
def slice_check(image, computation_dir, # image object containing all the information
                headskip=0.1, 
                tailskip=0.1, 
                baseline_z_Threshold= 3.0, 
                gradient_z_Threshold=3.5, 
                quad_fit=True , 
                subregion_check=False, ## not implemented yet
                subregion_relaxation_factor=1.1):
    
    image_tensor=image.images.astype(float) 
    gradients=image.getGradients()

    ## Generate slice correlation informations over gradients
    gsum=[]
    begin_slice=int(image_tensor.shape[2]*headskip)
    last_slice=int(image_tensor.shape[2]*(1-tailskip))
    for k in range(image_tensor.shape[3]):
        csum=[]
        for i in range(image_tensor.shape[2]):
            if i<=begin_slice or i>=last_slice: continue
            af=image_tensor[:,:,i,k].reshape([1,-1])
            bf=image_tensor[:,:,i-1,k].reshape([1,-1])
            corr=ncc(af,bf)
            if not np.isnan(corr): csum.append(float(corr))
            else: csum.append(0.0)
        gsum.append(csum)
    gsum=np.array(gsum) 

    ## lookup artifacts from the z-threshold criteria over gradients for each slices.
    min_bval=min(list(map(lambda x: x['b_value'],gradients)))
    max_bval=max(list(map(lambda x: x['b_value'],gradients)))
    quadfit= quadratic_fit_generator([min_bval,max_bval],[baseline_z_Threshold,gradient_z_Threshold])
    artifacts={}
    for slice_index in range(gsum.shape[1]):
        gradwise_vec=gsum[:,slice_index]
        avg=np.mean(gradwise_vec)
        std=np.std(gradwise_vec)
        logger("Slice {}, Mean {:.4f}, Std {:.4f}".format(slice_index+begin_slice,avg,std))
        for idx,g in enumerate(gradwise_vec):
            z_threshold=baseline_z_Threshold
            if quad_fit:
                z_threshold=quadfit(gradients[idx]['b_value'])
            elif not gradients[idx]['baseline']:
                z_threshold=gradient_z_Threshold
            if g < avg- z_threshold*std:
                if idx not in artifacts: artifacts[idx]=[]
                artifacts[idx].append({"slice":slice_index+begin_slice,
                                        "correlation":float(g),
                                        'z_threshold':float(z_threshold),
                                        'z_value':float((g-avg)/std),
                                        'b_value':float(gradients[idx]['b_value'])})

    gsum_file=Path(computation_dir).joinpath('correlation_table.yml') # row=gradient index, col = slice index
    yaml.dump(gsum.tolist(),open(gsum_file,'w'))
    artifacts_file=Path(computation_dir).joinpath("artifacts.yml")
    yaml.dump(artifacts,open(artifacts_file,'w'))

    ## recap and return the results
    arte=list(artifacts.items())
    arte_sorted=sorted(arte,key=lambda x: x[0]) ## fitst element is gradient index, second is list of slice indexes with artifacts
    return arte_sorted
