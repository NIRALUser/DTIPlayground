from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class ResampleDTIlogEuclidean(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)


    def filter_dti(self, inputfile, outputfile,correction='zero'):
        arguments=[inputfile,outputfile,'--correction',correction]
        self.setArguments(arguments)
        return self.execute(arguments)

    def implement_affine_registration(self,input_file,affine_file,transform_file,reference_file):
        arguments=[input_file,affine_file,'-f',transform_file,'-R',reference_file]
        self.setArguments(arguments)
        return self.execute(arguments)

    def resample(self,reference_file,
                       deform_field_file,
                       transformation_file,
                       moving_file,
                       output_file,
                       interpolation_type='Linear',
                       interpolation_option=None,
                       tensor_interpolation_type='Non Log Euclidean',
                       tensor_interpolation_option='Zero',
                       tensor_transform='Preservation of the Principal Direction (PPD)'
                       ):
        arguments=[
            '-R',reference_file,
            '-H',deform_field_file,
            '-f',transformation_file,
            moving_file,
            output_file
        ]
        options=[]
        ## options
        if interpolation_type=="Linear" : options+=["-i","linear"]
        if interpolation_type=="Nearest Neighborhood" : options+=["-i","nn"]
        if interpolation_type=="Windowed Sinc":
          if interpolation_option=="Hamming": options+=["-i", "ws", "-W", "h"]
          if interpolation_option=="Cosine" : options+=["-i", "ws", "-W", "c"] 
          if interpolation_option=="Welch"  : options+=["-i", "ws", "-W", "w"] 
          if interpolation_option=="Lanczos": options+=["-i", "ws", "-W", "l"] 
          if interpolation_option=="Blackman":options+=["-i", "ws", "-W", "b"]
        if interpolation_type=="BSpline":
          options+=["-i","bs","-o"] + [m_interpolation_option]  
        if tensor_interpolation_type=="Non Log Euclidean":
          if tensor_interpolation_option=="Zero" :  options+=["--nolog","--correction","zero"] #FinalReSampCommand = FinalReSampCommand + " --nolog --correction zero"
          if tensor_interpolation_option=="None" :  options+=["--nolog","--correction","none"] #FinalReSampCommand = FinalReSampCommand + " --nolog --correction none"
          if tensor_interpolation_option=="Absolute Value" : options+=["--nolog","--correction","abs"] #FinalReSampCommand = FinalReSampCommand + " --nolog --correction abs"
          if tensor_interpolation_option=="Nearest" : options+=["--nolog","--correction","nearest"] #FinalReSampCommand = FinalReSampCommand + " --nolog --correction nearest"
        if tensor_transform=="Preservation of the Principal Direction (PPD)": options+=['-T','PPD']
        if tensor_transform=="Finite Strain (FS)" :  options+=['-T','FS']

        arguments+=options
        self.setArguments(arguments)
        return self.execute(arguments)