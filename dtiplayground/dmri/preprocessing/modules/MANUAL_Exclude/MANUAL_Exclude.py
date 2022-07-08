  
import os
import markdown

import dtiplayground.dmri.preprocessing as prep

logger=prep.logger.write

class MANUAL_Exclude(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>

        self.result['output']['excluded_gradients_original_indexes']= self.protocol['gradientsToExclude'] ## this is code to exclude the gradients 
        self.result['output']['success']=True
        return self.result

    def postProcess(self,result_obj,opts):
        super().postProcess(result_obj, opts)        
        
        if self.result['input']['image_path']:
            input_image = os.path.abspath(self.result['input']['image_path'])
        else:
            input_image = None

        with open(os.path.abspath(self.output_dir) + '/report.md', 'bw+') as f:
            f.write('## {}\n'.format("Module: " + self.result['module_name']).encode('utf-8'))
            f.write('### {}\n'.format("input image: " + str(input_image)).encode('utf-8'))
            if len(self.result['output']['excluded_gradients_original_indexes']) == 0:
                f.write('* {}\n'.format('0 excluded gradients').encode('utf-8'))
            else:
                excluded_gradients = str(len(self.result['output']['excluded_gradients_original_indexes'])) + " excluded gradient(s): "
                for gradient_index in self.result['output']['excluded_gradients_original_indexes'][:-1]:
                    excluded_gradients = excluded_gradients + str(gradient_index) + ", "
                excluded_gradients += str(self.result['output']['excluded_gradients_original_indexes'][-1])
                f.write('* {}\n'.format(excluded_gradients).encode('utf-8'))
            f.seek(0)
            markdown.markdownFromFile(input=f, output=os.path.abspath(self.output_dir) + '/report.html')
