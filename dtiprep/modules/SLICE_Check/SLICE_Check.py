#
# Reference : https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/
#
# Written by SK Park , NIRAL, UNC
# 2021-04-18

from pathlib import Path
import numpy
from dtiprep.modules import DTIPrepModule
import dtiprep,yaml
import SLICE_Check.computations as computations

logger=dtiprep.logger.write


class SLICE_Check(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(SLICE_Check)
    def generateDefaultProtocol(self):
        super().generateDefaultProtocol()
        ## todos

        return self.protocol

    @dtiprep.measure_time
    def process(self):  ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        logger(yaml.dump(inputParams))
        logger(str(self.image.images.shape))
        arte_sorted=computations.slice_check(self.image,
                                             headskip=self.protocol['headSkipSlicePercentage'],
                                             tailskip=self.protocol['tailSkipSlicePercentage'],
                                             baseline_z_Threshold=self.protocol['correlationDeviationThresholdbaseline'],
                                             gradient_z_Threshold=self.protocol['correlationDeviationThresholdgradient'],
                                             quad_fit=self.protocol['quadFit'],
                                             subregion_check=self.protocol['bSubregionalCheck'],
                                             subregion_relaxation_factor=self.protocol['subregionalCheckRelaxationFactor'])
        logger("-------------------------------------------------------------")
        logger("Abnormal gradients")
        logger("-------------------------------------------------------------")
        #print(arte_sorted)
        grads=self.image.getGradients()
        for a in arte_sorted:
            logger("For gradient {} , Vec {}, isB0 {}".format(a[0],grads[a[0]]['gradient'],grads[a[0]]['baseline']))
            for i in range(len(a[1])):
                logger("\t\tSlice {}, Corr : {}".format(a[1][i]['slice'],a[1][i]['correlation']))

        gradient_indexes_to_remove=[ix[0] for ix in arte_sorted]

        #outimg_filename=self.result['output']['image_path']
        #self.image.writeImage(outimg_filename)
        ## make result and set final image to self.result and self.image (which are to be copied to the next pipeline module as on input)
        self.image.deleteGradients(gradient_indexes_to_remove)
        logger("Excluded gradient indexes : {}".format(gradient_indexes_to_remove))

        self.result['output']['image_path']=Path(self.output_dir).joinpath('output.nrrd').__str__()
        self.result['output']['success']=True
        self.result['output']['parameters']={
            "GradientNum": None, #int
            "SliceNum" : None,  #int
            "Correlation" : None    #float
        }

        return self.result