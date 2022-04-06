from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class CropDTI(ExternalToolWrapper):
    def __init__(self,binary_path):
        super().__init__(binary_path)

    def crop(self,inputfile,outputfile,size:list):
        arguments=[inputfile,'-o',outputfile,'-size',",".join(size)]
        self.setArguments(arguments)
        return self.execute(arguments)

