from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class UNU(ExternalToolWrapper):
    def __init__(self,binary_path):
        super().__init__(binary_path)

    def convert_to_float(self,input_file,output_file):
        arguments=[
            'convert',
            '-t','float',
            '-i',input_file,
        ]
        self.setArguments(arguments)
        pipe_output=self.execute_pipe()
        arguments=[
            'save',
            '-f','nrrd',
            '-e','gzip',
            '-o',output_file
        ]
        self.setArguments(arguments)
        return self.execute(stdin=pipe_output.stdout)