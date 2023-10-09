import dtiplayground.dmri.fiberprofile as base
import dtiplayground.dmri.common as common
import csv
import yaml
logger=common.logger.write

class FIBER_Process(base.modules.DTIFiberProfileModule):
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
        path_to_csv = inputParams["file_path"]
        with open(path_to_csv) as csv_file:
            reader = csv.reader(csv_file)
            header = next(csv_file)
            print(header)
            for row in reader:
                print(row)
                pass


        self.result['output']['success']=True
        return self.result
