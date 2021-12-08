  
import dmri.preprocessing as prep
from dmri.common import measure_time
import dmri.common.tools as tools 
import yaml
from pathlib import Path
logger=prep.logger.write

class DTI_Estimate(prep.modules.DTIPrepModule):
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
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.software_info=protocol_options['software_info']['softwares']
        self.baseline_threshold=protocol_options['baseline_threshold']
        options = { 'scalar' : self.protocol['scalar'] }
        res=self.runDTI(method=self.protocol['method'],
                          options=options)
        self.result['output']['success']=True
        return self.result

### User defined methods

    def runDTI(self,method, options):
        res = None
        if method.lower() == 'dipy':
            logger("Using {}".format(method),prep.Color.INFO)
            res = self.runDTI_DIPY(options)
        elif method.lower() == 'dtiestim':
            logger("Using {}".format(method),prep.Color.INFO)
            res = self.runDTI_dtiestim(options)
        else:
            raise Exception("Unknown method name : {}".format(method))
    
    def runDTI_DIPY(self, options):
        logger("DIPY Options : {}".format(yaml.dump(options)))
        return None

    def runDTI_dtiestim(self, options):
        logger("dtiestim Options : {}".format(yaml.dump(options)))
        dtiestim=tools.DTIEstim(self.software_info['dtiestim']['path'])
        input_image_path = Path(self.output_dir).joinpath('input.nrrd').__str__()
        output_tensor_path = Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        self.writeImage(str(input_image_path),dest_type='nrrd')
        dtiestim.estimate(input_image_path, output_tensor_path)
        self.addOutputFile(output_tensor_path, 'DTI')
        return None