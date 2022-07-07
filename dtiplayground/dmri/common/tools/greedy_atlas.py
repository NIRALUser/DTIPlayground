from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class GreedyAtlas(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)

    def compute_deformation_fields(self,xml_file,parsed_file):
        arguments=[
            '-f',xml_file,
            '-o',parsed_file
        ]
        self.setArguments(arguments)
        return self.execute(arguments)