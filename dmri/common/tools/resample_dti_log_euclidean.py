from dmri.common.tools.base import ExternalToolWrapper

class ResampleDTIlogEuclidean(ExternalToolWrapper):
    def __init__(self,binary_path):
        super().__init__(binary_path)

    def filter_dti(self, inputfile, outputfile,correction='zero'):
        self.setArguments([inputfile,outputfile,'--correction',correction])
        return self.execute()

    def implement_affine_registration(self,input_file,affine_file,transform_file,reference_file):
        self.setArguments([input_file,affine_file,'-f',transform_file,'-R',reference_file])
        return self.execute()
