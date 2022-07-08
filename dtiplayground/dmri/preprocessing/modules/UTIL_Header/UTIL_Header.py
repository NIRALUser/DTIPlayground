  
import dtiplayground.dmri.preprocessing as prep
import yaml
import os
import markdown
from pathlib import Path 
logger=prep.logger.write

class UTIL_Header(prep.modules.DTIPrepModule):
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
        logger(yaml.dump(self.image.information))
        self.result['output']['success']=True
        return self.result
    
    def postProcess(self,result_obj,opts):
        super().postProcess(result_obj, opts)        
        if self.result['input']['image_path']:
            input_image = os.path.abspath(self.result['input']['image_path'])
            for number in self.result['input']['image_information']['sizes']:
                if number not in self.result['input']['image_information']['image_size']:
                    self.result['report']['csv_data']['original_number_of_gradients'] = number
        elif type(self.result_history[0]["output"]) == dict: #single input
            input_image = os.path.abspath(self.result_history[0]["output"]["image_path"])
        else:
            input_image = None
            input_directory = self.result["input"]["output_directory"]
            while input_image == None:
                previous_result = yaml.safe_load(open(str(Path(self.output_dir).parent.parent) + "/" + input_directory + "/result.yml", 'r'))
                input_image = previous_result["input"]["image_path"]
                if "output_directory" in previous_result["input"]:
                    input_directory = previous_result["input"]["output_directory"]     

        with open(os.path.abspath(self.output_dir) + '/report.md', 'bw+') as f:
            f.write('## {}\n'.format("Module: " + self.result['module_name']).encode('utf-8'))
            f.write('### {}\n'.format("input image: " + str(os.path.abspath(input_image))).encode('utf-8'))
            f.seek(0)
            markdown.markdownFromFile(input=f, output=os.path.abspath(self.output_dir) + '/report.html')
        self.result['report']['csv_data']['image_name'] = str(os.path.abspath(input_image))
        with open(str(Path(self.output_dir).joinpath('result.yml')),'w') as f:
            yaml.dump(self.result,f)