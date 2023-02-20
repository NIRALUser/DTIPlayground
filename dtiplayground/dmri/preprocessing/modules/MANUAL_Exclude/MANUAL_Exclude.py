  
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
        self.result['output']['excluded_gradients_original_indexes']= self.protocol['gradientsToExclude'] ## this is code to exclude the gradients 
        self.result['output']['success']=True
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
