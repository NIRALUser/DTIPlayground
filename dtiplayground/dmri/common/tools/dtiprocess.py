from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class DTIProcess(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['dtiprocess']['path']

    def measure_scalars(self,inputfile,outputfile,scalar_type='FA',options=[]):
        assert(scalar_type.lower() in ['fa','md'])
        scalar_opt='-f' #FA
        if scalar_type.lower()!='fa' : scalar_opt='-m' #MA
        arguments=['--dti_image',inputfile,scalar_opt,outputfile]+options
        self.setArguments(arguments)
        return self.execute(arguments)

