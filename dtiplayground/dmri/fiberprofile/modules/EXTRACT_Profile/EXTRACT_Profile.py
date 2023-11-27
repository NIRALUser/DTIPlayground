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

        input_is_dti = True

        scalar_to_col_map = {}

        if input_is_dti:
            # check to see if the scalar images have already been generated
            # if not, generate them
            dtiprocess = tools.DTIProcess(self.software_info['dtiprocess']['path'])
            dtiprocess.setArguments(['--dti_image', '/proj/NIRAL/studies/IBIS/VSA/Data_DTIAtlas/Data_CMRR/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI.nrrd', '-m', '/proj/NIRAL/users/alecjn/test/out/test/00_EXTRACT_Profile/scalar_images/1/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI_MD.nrrd', '--lambda1_output', '/proj/NIRAL/users/alecjn/test/out/test/00_EXTRACT_Profile/scalar_images/1/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI_AD.nrrd', '--RD_output', '/proj/NIRAL/users/alecjn/test/out/test/00_EXTRACT_Profile/scalar_images/1/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI_RD.nrrd', '--correction', 'nearest'])
            dtiprocess.execute(['--dti_image', '/proj/NIRAL/studies/IBIS/VSA/Data_DTIAtlas/Data_CMRR/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI.nrrd', '-m', '/proj/NIRAL/users/alecjn/test/out/test/00_EXTRACT_Profile/scalar_images/1/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI_MD.nrrd', '--lambda1_output', '/proj/NIRAL/users/alecjn/test/out/test/00_EXTRACT_Profile/scalar_images/1/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI_AD.nrrd', '--RD_output', '/proj/NIRAL/users/alecjn/test/out/test/00_EXTRACT_Profile/scalar_images/1/107524_VSA-CVD_CMRR_APPA_final_lowShell_DTI_RD.nrrd', '--correction', 'nearest'])
            # Determine which scalars need to be generated
            scalars_to_generate = []
            for scalar in ['FA', 'MD', 'AD', 'RD']:
                scalar_col = f'{scalar} from original'
                if scalar_col not in df.columns:
                    # generate the scalar image
                    scalars_to_generate.append(scalar)

            for index, row in df.iterrows():
                subject_id = str(row.iloc[0])
                path_to_original_dti_image = row.iloc[1]
                scalar_img_folder_path = Path(output_base_dir).joinpath("scalar_images").joinpath(subject_id)
                scalar_img_folder_path.mkdir(parents=True, exist_ok=True)
                output_stem = scalar_img_folder_path.joinpath(Path(path_to_original_dti_image).stem).__str__()
                options = [
                    '--correction', 'nearest', '--scalar_float'
                ]
                # run dtiprocess to generate scalar images
                dtiprocess.measure_scalar_list(path_to_original_dti_image, output_stem, scalars_to_generate, options)
                # update the dataframe with the paths to the scalar images
                for scalar in scalars_to_generate:
                    scalar_col = f'{scalar} from original'
                    scalar_img_path = output_stem.__str__() + '_' + scalar + '.nrrd'
                    df.at[index, scalar_col] = scalar_img_path

        # write the modified dataframe to the output directory
        df.to_csv(Path(output_base_dir).joinpath(path_to_csv.stem + '_with_scalars.csv'), index=False)
        # iterate over the rows of the CSV
        for _, row in df.iterrows():
            subject_id = row.iloc[0]
            path_to_original_dti_image = row.iloc[1]
            # For each property to profile,
            for property in properties_to_profile:
                print("property: ", property)
                # Find path to scalar image in the dataframe
                scalar_img_col = f'{property} from original'
                scalar_img_path = row[scalar_img_col]
                # create the file path for the output
                for tract in tracts:
                    # create the directory for the output for the scalar property
                    scalar_dir_output_path = Path(output_base_dir).joinpath(property).joinpath(Path(tract).stem)
                    scalar_dir_output_path.mkdir(parents=True, exist_ok=True)
                    print("tract: ", tract)
                    tract_absolute_filename = Path(atlas_path).joinpath(tract) # concatenate the atlas path with the tract name
                    fiberprocess_output_path = scalar_dir_output_path.joinpath(f'{subject_id}_' + tract.replace('_extracted_done',
                                                                                                  f'_{property}_profile'))
                    scalar_name = property
                    options = []
                    options += ['--scalarName', scalar_name]
                    options += ['--ScalarImage', scalar_img_path]
                    options += ['--no_warp']
                    fiberprocess = tools.FiberProcess(self.software_info['fiberprocess']['path'])
                    fiberprocess.run(tract_absolute_filename.__str__(), fiberprocess_output_path.__str__(),
                                     options=options)
                    # run fiberpostprocess
                    options = []
                    fiberpostprocess = tools.FiberPostProcses(self.software_info['fiberpostprocess']['path'])
                    fiberpostprocess_output_path = fiberprocess_output_path.__str__().replace('.vtk', '_processed.vtk')
                    fiberpostprocess.run(fiberprocess_output_path, fiberpostprocess_output_path, options=options)


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
