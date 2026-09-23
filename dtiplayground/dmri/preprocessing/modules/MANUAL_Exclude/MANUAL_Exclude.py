  
import os
import markdown

import dtiplayground.dmri.preprocessing as prep


class MANUAL_Exclude(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write
    
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>

        if isinstance(self.protocol['gradientsToExclude'],str):
            temp = list(map(int,self.protocol['gradientsToExclude'].split(',')))
            self.protocol['gradientsToExclude'] = temp
        self.logGradientsToExclude(self.protocol['gradientsToExclude'])
        self.result['output']['excluded_gradients_original_indexes']= self.protocol['gradientsToExclude'] ## this is code to exclude the gradients
        self.result['output']['success']=True
        return self.result

    def logGradientsToExclude(self, original_indexes):
        """What the listed indexes refer to: the volumes of the input of the pipeline (their original index), not the
        positions in the image this module receives. The two differ as soon as an earlier module excluded a volume,
        so the mapping is logged."""
        gradients = self.image.getGradients()
        position = {int(g['original_index']): i for i, g in enumerate(gradients)}
        found = [(int(i), position[int(i)]) for i in original_indexes if int(i) in position]
        missing = [int(i) for i in original_indexes if int(i) not in position]
        for original, pos in found:
            logger("Excluding original gradient {} (volume {} of {} of this image)".format(original, pos, len(gradients)),
                   prep.Color.INFO)
        if any(original != pos for original, pos in found):
            logger("The listed indexes are the original ones (the volumes of the input of the pipeline); an earlier "
                   "module already excluded volumes, so they are not the positions in this image",
                   prep.Color.WARNING)
        if missing:
            logger("Original gradient(s) {} are not in this image (already excluded, or beyond the last one): "
                   "nothing is excluded for them".format(', '.join(map(str, missing))), prep.Color.WARNING)

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
