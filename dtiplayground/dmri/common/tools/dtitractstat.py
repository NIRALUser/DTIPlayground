from dtiplayground.dmri.common.tools.base import ExternalToolWrapper

class DTITractStat(ExternalToolWrapper):
    def __init__(self,binary_path= None, **kwargs):
        super().__init__(binary_path, **kwargs)
        self.binary_path=None
        if binary_path is not None:
            self.binary_path=binary_path
        elif 'softwares' in kwargs:
            self.binary_path=kwargs['softwares']['dtitractstat']['path']

    def run(self, datasheet_path, atlas_path, tracts, properties_to_profile, output_path, options=[]):
        arguments=[]
        arguments+=['--datasheet',datasheet_path]
        arguments+=['--atlas',atlas_path]
        arguments+=['--tracts',tracts]
        arguments+=['--propertiesToProfile',properties_to_profile]
        arguments+=['--output',output_path]
        arguments+=options
        self.setArguments(arguments)
        return self.execute(arguments)
