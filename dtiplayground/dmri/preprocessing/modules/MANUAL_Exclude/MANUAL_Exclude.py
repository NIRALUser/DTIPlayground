  
import dtiplayground.dmri.preprocessing as prep

logger=prep.logger.write

class MANUAL_Exclude(prep.modules.DTIPrepModule):
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

        self.result['output']['excluded_gradients_original_indexes']= self.protocol['gradientsToExclude'] ## this is code to exclude the gradients 
        self.result['output']['success']=True
        return self.result
