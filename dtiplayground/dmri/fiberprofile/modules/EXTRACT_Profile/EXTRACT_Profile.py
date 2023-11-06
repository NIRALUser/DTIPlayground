import dtiplayground.dmri.fiberprofile as base
import dtiplayground.dmri.common as common
import csv
import yaml

from pathlib import Path

from dtiplayground.dmri.common import tools

logger=common.logger.write

class EXTRACT_Profile(base.modules.DTIFiberProfileModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol
    """
    Main function called by the pipeline when this module runs.
    """
    def process(self,*args,**kwargs):
        super().process()
        inputParams=self.getPreviousResult()['output']
        opts=args[0] # includes options from command line args
        # << TODOS>>
        path_to_csv = inputParams["file_path"]
        with open(path_to_csv) as csv_file:
            reader = csv.reader(csv_file)
            header = next(csv_file)
            print(header)
            for row in reader:
                print(row)

        # run fiberprocess
        self.runFiberProcess()
        # call fiberpostprocess
        # self.runFiberProcess()
        # call dtitractstat
        # self.runDTITractStat()

        self.result['output']['success']=True
        return self.result
    """
    Runs the fiberprocess binary using the Python wrapper in the common tools.
    """
    def runFiberProcess(self, args=None):
        inputParams = self.getPreviousResult()['output']
        path_to_csv = inputParams["file_path"]
        atlas_path = self.protocol["atlas"]
        tracts = self.protocol["tracts"]

        properties_to_profile = self.protocol["propertiesToProfile"]

        # call fiberprocess
        fiberprocess = tools.DTIEstim(self.software_info['fiberprocess']['path'])
        # TODO: what type of file is the output of fiberprocess?
        fiberprocess_output_path = Path(self.output_dir).joinpath('fiberprocess_out.csv').__str__()
        options = []
        fiberprocess.run(path_to_csv, atlas_path, tracts, properties_to_profile, fiberprocess_output_path,
                         options=options)

    """
    Runs the fiberpostprocess binary using the Python wrapper in the common tools.
    """
    def runFiberPostProcess(self, args=None):
        inputParams = self.getPreviousResult()['output']
        path_to_csv = inputParams["file_path"]
        atlas_path = self.protocol["atlas"]
        tracts = self.protocol["tracts"]

        properties_to_profile = self.protocol["propertiesToProfile"]

        # call fiberpostprocess
        fiberpostprocess = tools.FiberPostProcses(self.software_info['fiberpostprocess']['path'])
        fiberpostprocess_output_path = Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        options = []
        fiberpostprocess.run(path_to_csv, atlas_path, tracts, properties_to_profile, fiberpostprocess_output_path,
                         options=options)
    """
    Runs the dtitractstat binary using the Python wrapper in the common tools.
    """
    def runDTITractStat(self, args=None):
        inputParams = self.getPreviousResult()['output']
        path_to_csv = inputParams["file_path"]
        atlas_path = self.protocol["atlas"]
        tracts = self.protocol["tracts"]

        properties_to_profile = self.protocol["propertiesToProfile"]

        # call dtitractstat
        dtitractstat = tools.DTITractStat(self.software_info['dtitractstat']['path'])
        dtitractstat_output_path = Path(self.output_dir).joinpath('tensor.nrrd').__str__()
        options = []
        dtitractstat.run(path_to_csv, atlas_path, tracts, properties_to_profile, dtitractstat_output_path,
                         options=options)