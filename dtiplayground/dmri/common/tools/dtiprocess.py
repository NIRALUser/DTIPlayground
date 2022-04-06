from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class DTIProcess(ExternalToolWrapper):
    def __init__(self,binary_path):
        super().__init__(binary_path)

    
    def measure_scalars(self,inputfile,outputfile,scalar_type='FA',options=[]):
        assert(scalar_type.lower() in ['fa','md'])
        scalar_opt='-f' #FA
        if scalar_type.lower()!='fa' : scalar_opt='-m' #MA
        arguments=['--dti_image',inputfile,scalar_opt,outputfile]+options
        self.setArguments(arguments)
        return self.execute(arguments)

