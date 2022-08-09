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

import SLICE_Check.computations as computations

logger=prep.logger.write

class SLICE_Check(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    @prep.measure_time
    def process(self,*args,**kwargs):  ## variables : self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        #logger(yaml.dump(inputParams))
        arte_sorted=computations.slice_check(self.image,computation_dir=self.computation_dir,
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