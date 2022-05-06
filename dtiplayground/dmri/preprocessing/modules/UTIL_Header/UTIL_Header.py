  
import dtiplayground.dmri.preprocessing as prep
import yaml
import os
import markdown
logger=prep.logger.write

class UTIL_Header(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>
        logger(yaml.dump(self.image.information))
        self.result['output']['success']=True
        return self.result

    @prep.measure_time
    def postProcess(self,result_obj,opts):
        super().postProcess(result_obj, opts)        
        
        if self.result['input']['image_path']:
            input_image = os.path.abspath(self.result['input']['image_path'])
        else:
            input_image = None        

        with open(os.path.abspath(self.output_dir) + '/report.md', 'bw+') as f:
            f.write('## {}\n'.format("Module: " + self.result['module_name']).encode('utf-8'))
            f.write('### {}\n'.format("input image: " + str(input_image)).encode('utf-8'))
            f.seek(0)
            markdown.markdownFromFile(input=f, output=os.path.abspath(self.output_dir) + '/report.html')