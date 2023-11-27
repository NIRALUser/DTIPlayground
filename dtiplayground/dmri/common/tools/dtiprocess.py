from dtiplayground.dmri.common.tools.base import ExternalToolWrapper


class DTIProcess(ExternalToolWrapper):
    def __init__(self, binary_path=None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path = None
        if binary_path is not None:
            self.binary_path = binary_path
        elif 'softwares' in kwargs:
            self.binary_path = kwargs['softwares']['dtiprocess']['path']

    def measure_scalars(self, inputfile, outputfile, scalar_type='FA', options=[]):
        assert (scalar_type.lower() in ['fa', 'md', 'ad', 'rd'])
        scalar_opt_key = scalar_type.lower()
        scalar_opt_map = {'fa': '-f', 'md': '-m', 'ad': '--lambda1_output', 'rd': '--RD_output'} # maps the scalar_type to the command line option
        scalar_opt = scalar_opt_map[scalar_opt_key]
        arguments = ['--dti_image', inputfile, scalar_opt, outputfile] + options
        self.setArguments(arguments)
        return self.execute(arguments)

    def measure_scalar_list(self, inputfile, outputFileStem, scalar_list=['FA', 'MD', 'AD', 'RD'], options=[]):
        arguments = ['--dti_image', inputfile]
        for scalar in scalar_list:
            assert (scalar.lower() in ['fa', 'md', 'ad', 'rd'])
            scalar_opt_key = scalar.lower()
            scalar_opt_map = {'fa': '-f', 'md': '-m', 'ad': '--lambda1_output', 'rd': '--RD_output'}
            scalar_opt = scalar_opt_map[scalar_opt_key]
            arguments += [scalar_opt, outputFileStem + '_' + scalar + '.nrrd']
        arguments += options
        self.setArguments(arguments)
        return self.execute(arguments)