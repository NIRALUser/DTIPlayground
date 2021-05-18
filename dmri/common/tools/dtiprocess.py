from dmri.common.tools.base import ExternalToolWrapper

class DTIProcess(ExternalToolWrapper):
    def __init__(self,binary_path):
        super().__init__(binary_path)

    
    def measure_scalars(self,inputfile,outputfile,scalar_type='FA'):
        assert(scalar_type.lower() in ['fa','ma'])
        scalar_opt='-f' #FA
        if scalar_type.lower()!='fa' : scalar_opt='-m' #MA
        self.setArguments(['--dti_image',inputfile,scalar_opt,outputfile])
        return self.execute()

