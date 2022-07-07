from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class DTIAverage(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['dtiaverage']['path']

    def average(self,input_file_list:list,output_file,options=[]):
        arguments=[]
        for fn in input_file_list:
            arguments+=['--inputs',fn]
        arguments+=['--tensor_output',output_file]
        arguments+=options
        self.setArguments(arguments)
        return self.execute(arguments)
        