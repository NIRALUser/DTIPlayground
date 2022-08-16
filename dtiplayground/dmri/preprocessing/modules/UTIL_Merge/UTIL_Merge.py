  
import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.common.dwi import DWI
import yaml
from pathlib import Path
import os
import markdown
logger=prep.logger.write

class UTIL_Merge(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.images (input), self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>
        self.image = DWI.mergeImages(*self.images)
        output_nrrd=Path(self.output_dir).joinpath('output.nrrd').__str__()
        self.writeImageWithOriginalSpace(output_nrrd,'nrrd')
        self.result['output']['success']=True
        return self.result

    def makeReport(self):
        with open(os.path.abspath(self.output_dir) + '/report.md', 'bw+') as f:
            f.write('## {}\n'.format("Module: " + self.result['module_name']).encode('utf-8'))
            for image_iter in range(len(self.result['input'])):
                input_image = self.result['input'][image_iter]['output']['image_path']
                input_image = str(os.path.abspath(input_image))
                f.write('### {}\n'.format("input image: " + str(os.path.abspath(input_image))).encode('utf-8'))
            f.seek(0)
            markdown.markdownFromFile(input=f, output=os.path.abspath(self.output_dir) + '/report.html')


  

