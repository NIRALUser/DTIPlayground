from pathlib import Path

import pandas as pd

import dtiplayground.dmri.common as common
import dtiplayground.dmri.fiberprofile as base
from dtiplayground.dmri.common import tools

logger = common.logger.write


class EXTRACT_Profile(base.modules.DTIFiberProfileModule):
    def __init__(self, config_dir, *args, **kwargs):
        super().__init__(config_dir)

    def generateDefaultProtocol(self, image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    """
    Main function called by the pipeline when this module runs.
    """

    def process(self, *args, **kwargs):
        super().process()
        inputParams = self.getPreviousResult()['output']
        protocol_options = args[0]
        self.software_info = protocol_options['software_info']['softwares']
        # << TODOS>>
        path_to_csv = inputParams["file_path"]
        df = pd.read_csv(path_to_csv)
        atlas_path = self.protocol["atlas"]
        tracts = self.protocol["tracts"].split(',')
        output_base_dir = self.output_dir  # output directory string
        properties_to_profile = self.protocol["propertiesToProfile"].split(',')

        row = df.iloc[1]
        path_to_dti_image = row.iloc[1]
        # for index, row in df.itterows():
        #     path_to_dti_image = row.iloc[0]

        # For each subject

        # For each property to profile,
        print(self.software_info)
        for property in properties_to_profile:
            print("property: ", property)
            # create the directory for the output for the scalar property
            scalar_dir_output_path = Path(output_base_dir).joinpath(property)
            scalar_dir_output_path.mkdir(parents=True, exist_ok=True)
            scalar_img_path = row.iloc[2]
            # create the file path for the output
            for tract in tracts:
                print("tract: ", tract)
                tract_absolute_filename = atlas_path + tract # concatenate the atlas path with the tract name
                fiber_output_path = scalar_dir_output_path.__str__() + '/' + tract.replace('_extracted_done',
                                                                                              f'_{property}_profile')
                fiber_output_path_str = fiber_output_path
                scalar_name = property
                options = []
                options += ['--scalarName', scalar_name]
                options += ['--ScalarImage', scalar_img_path]
                options += ['--no_warp']
                fiberprocess = tools.FiberProcess(self.software_info['fiberprocess']['path'])
                fiberprocess.run(tract_absolute_filename, fiber_output_path_str,
                                 options=options)

            # Extract the filename without the path

            # call fiberprocess
            self.runFiberProcess()
            # call fiberpostprocess
            self.runFiberPostProcess()
            # call dtitractstat
            self.runDTITractStat()

            # create the file path for the output

        for index, row in df.itterows():
            path_to_dti_image = row.iloc[0]

        # run fiberprocess
        self.runFiberProcess()
        # call fiberpostprocess
        # self.runFiberProcess()
        # call dtitractstat
        # self.runDTITractStat()

        self.result['output']['success'] = True
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
        print(self.software_info)

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
