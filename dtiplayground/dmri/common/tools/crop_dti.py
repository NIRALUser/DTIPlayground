from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class CropDTI(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)

    def crop(self,inputfile,outputfile,size:list):
        arguments=[inputfile,'-o',outputfile,'-size',",".join(size)]
        self.setArguments(arguments)
        return self.execute(arguments)

