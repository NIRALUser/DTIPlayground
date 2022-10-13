#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

  
import dtiplayground.dmri.preprocessing as prep

import yaml
from pathlib import Path
import os
import markdown

import numpy as np
import time
import os 




# import SLICE_Check.computations as computations

class SLICE_Check(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    @prep.measure_time
    def process(self,*args,**kwargs):  ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        #logger(yaml.dump(inputParams))
        arte_sorted=self.slice_check(self.image,computation_dir=self.computation_dir,
                                             headskip=self.protocol['headSkipSlicePercentage'],
                                             tailskip=self.protocol['tailSkipSlicePercentage'],
                                             baseline_z_Threshold=self.protocol['correlationDeviationThresholdbaseline'],
                                             gradient_z_Threshold=self.protocol['correlationDeviationThresholdgradient'],
                                             quad_fit=self.protocol['quadFit'],
                                             subregion_check=self.protocol['bSubregionalCheck'],
                                             subregion_relaxation_factor=self.protocol['subregionalCheckRelaxationFactor']
                                             )
        logger("-------------------------------------------------------------",prep.Color.WARNING)
        logger("Abnormal gradients",prep.Color.WARNING)
        logger("-------------------------------------------------------------",prep.Color.WARNING)

        grads=self.image.getGradients()
        for a in arte_sorted:
            grad_index=a[0]
            grad_original_index=grads[a[0]]['original_index']
            vec=grads[a[0]]['gradient']
            isB0=grads[a[0]]['baseline']
            logger("For gradient {} (Org.Idx {}) , Vec {}, isB0 {}".format(grad_index,
                                                                            grad_original_index,
                                                                            vec,
                                                                            isB0))
            for i in range(len(a[1])):
                logger("\t\tSlice.idx {}, Correlation : {:.4f}".format(a[1][i]['slice'],a[1][i]['correlation']))
        gradient_indexes_to_remove=[ix[0] for ix in arte_sorted]

        ## make result and set final image to self.result and self.image (which are to be copied to the next pipeline module as on input)
        ## Excluded original indexes will be automatically deleted in the postProcess
        #logger("Excluded gradient indexes : {}".format(gradient_indexes_to_remove),prep.Color.WARNING) #gradient indexes are not original one , so need to convert
        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        #self.result['output']['image_path']=Path(self.output_dir).joinpath('output.nrrd').__str__()
        self.result['output']['success']=True
        self.image.setSpaceDirection(target_space=self.getSourceImageInformation()['space'])
        return self.result


    @prep.measure_time
    def slice_check(self,
                    image, computation_dir, # image object containing all the information
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
        begin_slice=int(np.floor(image_tensor.shape[2]*headskip))
        last_slice=int(np.floor(image_tensor.shape[2]*(1-tailskip)))
        for k in range(image_tensor.shape[3]):
            csum=[]
            for i in range(image_tensor.shape[2]):
                if i<=begin_slice or i>=last_slice: continue
                af=image_tensor[:,:,i,k].reshape([1,-1])
                bf=image_tensor[:,:,i-1,k].reshape([1,-1])
                corr=self.ncc(af,bf)
                if not np.isnan(corr): csum.append(float(corr))
                else: csum.append(0.0)
            gsum.append(csum)
        gsum=np.array(gsum) 

        ## lookup artifacts from the z-threshold criteria over gradients for each slices.
        min_bval=min(list(map(lambda x: x['b_value'],gradients)))
        max_bval=max(list(map(lambda x: x['b_value'],gradients)))
        quadfit= self.quadratic_fit_generator([min_bval,max_bval],[baseline_z_Threshold,gradient_z_Threshold])
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

    def ncc_old(self,x,y):  #normalized correlation
        x=(x-np.mean(x))/np.sqrt(np.sum((x-np.mean(x))**2))
        y=(y-np.mean(y))/np.sqrt(np.sum((y-np.mean(y))**2))
        return np.sum(x*y)

    def ncc(self,x,y): #normalized cross correlation in image (ref: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/ )
        ab=np.sum(x*y)
        a2=np.sum(x**2)
        b2=np.sum(y**2)
        if a2*b2==0.0: 
            return 1.0
        else:
            return ab/np.sqrt(a2*b2)

    def _quad_fit(self,bval, domain=[0,1000], fimage=[3.0,3.5]): #returns std multiple between fimage
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

    def quadratic_fit_generator(self,domain,fimage):
        def wrapper(bval):
            return self._quad_fit(bval,domain,fimage)
        return wrapper

    def makeReport(self):
        super().makeReport() 
        
        with open(os.path.abspath(self.output_dir) + '/report.md', 'a') as f:
            if len(self.result['output']['excluded_gradients_original_indexes']) == 0:
                f.write('* 0 excluded gradients\n')
            else:
                excluded_gradients = str(len(self.result['output']['excluded_gradients_original_indexes'])) + " excluded gradient(s): "
                for gradient_index in self.result['output']['excluded_gradients_original_indexes'][:-1]:
                    excluded_gradients = excluded_gradients + str(gradient_index) + ", "
                excluded_gradients += str(self.result['output']['excluded_gradients_original_indexes'][-1])
                f.write('* ' + excluded_gradients + '\n')
        self.result['report']['csv_data']['excluded_gradients'] = self.result['output']['excluded_gradients_original_indexes']
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)


