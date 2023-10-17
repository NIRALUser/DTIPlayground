import dtiplayground.dmri.fiberprofile as base
import dtiplayground.dmri.common as common
import csv
import yaml
logger=common.logger.write

class EXTRACT_Profile(base.modules.DTIFiberProfileModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs):
        super().process()
        inputParams=self.getPreviousResult()['output']
        opts=args[0] # includes options from command line args
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
