from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class FiberPostProcess(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['fiberpostprocess']['path']

    """
    FiberPostProcess Command Line Tool

    Usage:
    fiberpostprocess --inputFiberFile <input_fiber_filename> --outputFiberFile <output_fiber_filename> 
                     --attributeFile <attribute_filename> --thresholdMode <threshold_mode> --threshold <threshold>
                     [--mask] [--crop] [--clean] [--noNan] [--visualize] [--lengthMatch <length_match_filename>]

    Arguments:
      --inputFiberFile <input_fiber_filename>  : Input fiber filename in .vtk or .vtp
      --outputFiberFile <output_fiber_filename> : Output fiber filename in .vtk or .vtp
      --attributeFile <attribute_filename>     : Attribute filename in .nrrd, .nhdr, etc, such as a probability mask, or FA, MD, etc.
                                                  Set by default as a binary mask. This parameter is used to crop the beginning and the 
                                                  end of each fiber or to mask the fiber bundle and remove any fiber considered outside 
                                                  of this mask (determined by the threshold parameter).
      --thresholdMode <threshold_mode>          : Set to 'above' or 'below'. Determines if the mask is considered as an inclusion mask 
                                                  or as an exclusion mask.
      --threshold <threshold>                   : Threshold value between 0 and 1. If the attribute value averaged along fiber is below 
                                                  or above threshold, the corresponding fiber is excluded.

    Options:
      --mask          : Enables the masking of the fiber bundle. If toggled, the mask is applied to the fiber bundle. By default, 
                       the output will contain additional cell datas but fibers will not be removed. Use the --clean flag to remove 
                       the fibers that are supposed to be excluded.
      --crop          : Output file contains the fiber bundle cropped if a mask has been given as an input. If toggled, the output file 
                       is a fiber bundle cropped. If not, the fiber file contains the same fiber bundle than the input, with appended 
                       cell datas and point datas.
      --clean         : Enables the cleaning of the fiber bundle. If this flag and the mask flag are toggled, the output bundle will 
                       be a fiber bundle masked, fibers are excluded depending on the threshold.
      --noNan         : The output fiber file will not contain fibers that can have NaN values. If toggled, remove any fibers that can 
                       contain NaN values.
      --visualize     : Write a visualizable output file (file name = outputfileName + "-visu"). If toggled, enable to visualize which 
                       parts of the fiber bundles are outside of the mask.
      --lengthMatch <length_match_filename>     : Use the file given to match the length of the fibers of the input fiber bundle file.

    Description:
      Removes fibers outside of a mask.

    Version: 1.2.2
    Contributors: Jean-Yves Yang, Juan Carlos Prieto
    """

    def run(self, input_fiber_path: str, output_file_path: str, options=[]):
        arguments=[]
        arguments+=['--inputFiberFile',input_fiber_path]
        arguments+=['--outputFiberFile', output_file_path]
        arguments+=options
        self.setArguments(arguments)
        return self.execute(arguments)

