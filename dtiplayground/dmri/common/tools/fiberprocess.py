from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class FiberProcess(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['fiberprocess']['path']

    """
    FiberProcess Command Line Tool

    Usage:
      fiberprocess [options]

    Options:
      # I/O
      --fiber_file, -fiberFile           Input DTI fiber file. (Required)
      --fiber_output, -o                 Output fiber file. May be warped or updated with new data. (Required)
      --tensor_volume, -T                Input tensor volume. Interpolate tensor values from this field. (tensor or scalar required) 
      --scalarImage, -S                  Input scalar image file. Samples scalar values at fiber locations. (tensor or scalar required) 
      --scalarName                        Name for the pointData field in the output fiber file.
      --h_field, -H                      Input HField for warp and statistics lookup. (alternative to displacement field)
      --displacement_field, -D           Input Displacement Field for warp and statistics lookup. (usually needed to move images into atlas space)

      # Options
      --saveProperties, -p               Save tensor property as scalar data into the VTK (for VTK fiber files).
      --no_warp, -n                      Do not warp the geometry of tensors, only obtain new statistics.
      --fiber_radius, -R                 Set the radius of all fibers to this value.
      --index_space, -indexSpace         Use index-space for fiber output coordinates; otherwise, use world space.

      # Voxelize
      --voxelize, -V                     Voxelize fiber into a label map. Deformation is applied before voxelization.
      --voxelize_count_fibers           Count the number of fibers per voxel instead of just setting to 1.
      --voxel_label                       Label for voxelized fiber (default is 1).

      # Advanced Options
      --verbose, -v                      Produce verbose output.
      --noDataChange                     Do not change data.
    """
    """
    Calls the FiberProcess binary using the Python wrapper in the common tools. Uses arguments described above.
    """
    def run(self, fiber_file, output_path, options=[]):
        arguments=[]
        arguments+=['--fiber_file',fiber_file]
        arguments+=['--fiber_output', output_path]
        arguments+=options
        self.setArguments(arguments)
        return self.execute(arguments)

