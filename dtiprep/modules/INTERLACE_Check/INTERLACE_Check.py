#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

from dtiprep.modules import DTIPrepModule
import dtiprep,yaml,traceback 
import INTERLACE_Check.computations as computations 

import numpy as np
import time
logger=dtiprep.logger.write

class INTERLACE_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(INTERLACE_Check)
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos
        return self.protocol
    def process(self): ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        print("Child method begins")
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))
        logger(self.image.images.shape)

        affine=np.transpose(np.append(self.image.information['space_directions'],np.expand_dims(self.image.information['space_origin'],0),axis=0))
        affine=np.append(affine,np.array([[0,0,0,1]]),axis=0)
        affine=computations.affine_3d_to_2d(affine)

        output=[]
        for gidx in range(self.image.images.shape[3]):
            output_for_gradient=[]
            vol=self.image.images[:,:,:,gidx]
            logger("\nGradient {}/{} computing".format(gidx,self.image.images.shape[3]-1))
            grad_et=0.0
            for ix in range(vol.shape[2]):
                if ix < 2 : continue
                moving=vol[:,:,ix]
                static=vol[:,:,ix-2]
                #print(np.sum(moving-static))
                #print(static)
                bt=time.time()
                norm=0.0
                angle=0.0
                try:
                    transformed, out_affine=computations.rigid_2d(static,moving,affine,affine)
                    norm=computations.measure_translation_from_affine_matrix(out_affine)
                except Exception as e:
                    #traceback.print_exc()
                    print("Exception")
                    print("Moving : {}, Static :{}\n".format(np.sum(moving**2),np.sum(static**2)))
                et=time.time()-bt
                grad_et+=et
                print("\r[Slice {} and {}]  Translation: {:.4f} ,Max Angle: {:.4f} ,Time: {:.2f}s, Total: {:.0f}s".format(ix-2,ix,norm,angle,et,grad_et),end='\r')
                # if norm > self.protocol['translationThreshold']:
                #     print("\n")
                output_for_gradient.append(out_affine)
                #logger(out_affine)
            output.append(output_for_gradient)

        #logger(self.image.getGradients())

        self.result['output']['success']=True
        return self.result