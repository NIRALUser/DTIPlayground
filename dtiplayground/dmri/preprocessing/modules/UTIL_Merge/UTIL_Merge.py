  
import dtiplayground.dmri.preprocessing as prep
from dtiplayground.dmri.preprocessing.dwi import DWI
import yaml
from pathlib import Path
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
