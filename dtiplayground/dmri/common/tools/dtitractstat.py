from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class DTITractStat(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['dtitractstat']['path']

    """
    DTI Fiber Tract Statistics Tool Parameters:

    - input_fiber_file: --input_fiber_file, -i
      Input fiber file in .vtk format

    - output_stats_file: --ouput_stats_file, -o
      Output statistics file in .fvp format along the fiber

    - output_parametrized_fiber_file: --output_parametrized_fiber_file, -f
      Output parametrized fiber file

    - output_original_fibers_parametrized: --output_original_fibers_parametrized, -d
      Output original fibers with arclength to plane

    - plane_file: --plane_file
      File specifying the plane

    - auto_plane_origin: --auto_plane_origin
      Way to calculate auto plane origin (default: cog)

    - window_file: --window_file
      CSV file with histogram values for the chosen kernel window

    - image_space: --image_space
      Set if the fiber file is in image space (default: False)

    - step_size: --step_size
      Step size for sampling the fiber file (default: 1)

    - processing_rodent: --rodent
      Set when processing rodent images (default: False)

    - window: --window
      Window value for visualization (-1 means no window chosen, default: -1)

    - bandwidth: --bandwidth
      Bandwidth or std for the kernel used in noise model (default: 1)

    - parameter_list: --parameter_list
      List of scalar diffusion properties (default: fa,md,ad,l2,l3,fro,rd,ga)

    - scalarName: --scalarName
      Optional scalar properties present in the fiber file

    - noise_model: --noise_model
      Noise model used (default: gaussian)

    - stat_type: --stat_type
      Type of maximum likelihood estimate (default: mean)

    - q_perc: --quantile_percentage
      Quantile percentage [0,100] (default: 50)

    - useNonCrossingFibers: --use_non_crossing_fibers
      Use non-crossing fibers (default: False)

    - removeNanFibers: --remove_nan_fibers
      Remove fibers that contain NaN values (default: False)

    - removeCleanFibers: --remove_clean_fiber
      Remove clean fiber files saved on the hard drive (default: False)
    """

    def run(self, input_fiber_file: str, output_stats_file: str, options=[]):
        arguments=[]
        arguments+=['--input_fiber_file',input_fiber_file]
        arguments+=['-o',output_stats_file]
        arguments+=options
        self.setArguments(arguments)
        return self.execute(arguments)
