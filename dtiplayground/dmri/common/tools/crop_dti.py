from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class CropDTI(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)

    def crop(self,inputfile,outputfile,size: str):
        arguments=[inputfile,'-o',outputfile,'-size',size]
        self.setArguments(arguments)
        return self.execute(arguments)

