from pathlib import Path
from typing import List

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

        # Reading some parameters
        try:
            path_to_csv: str = inputParams["file_path"]
            output_base_dir: str = self.output_dir  # output directory string
            atlas_path: str = self.protocol["atlas"]
            if not isinstance(atlas_path, str):
                raise ValueError(f"Atlas path must be a string specifying directory with tracts. Current value: {atlas_path}")
            tracts_string: str = self.protocol["tracts"]
            if not isinstance(tracts_string, str):
                raise ValueError("Tracts must be a string of comma delimited tracts to profile")
            tracts: List[str] = tracts_string.split(',')
            properties_to_profile: List[str] = [x.strip() for x in self.protocol["propertiesToProfile"].split(',')]
            result_case_columnwise: bool = self.protocol["resultCaseColumnwise"]
            input_is_dti: bool = self.protocol["inputIsDTI"]
            overwrite: bool = self.options['overwrite']
            use_displacement_field: bool = self.protocol["useDisplacementField"]
            step_size: str = str(self.protocol["stepSize"])
            plane_of_origin: str = self.protocol["planeOfOrigin"]
            support_bandwidth: str = str(self.protocol["supportBandwidth"])
            noNaN: str = self.protocol["noNaN"]
            mask: str = self.protocol["mask"]
        except KeyError as e:
            self.result['output']['success'] = False
            self.result['output']['error'] = f"Missing parameter {e}"
            logger(f"Missing parameter: {e}")
            exit(1)
        except ValueError as e:
            self.result['output']['success'] = False
            self.result['output']['error'] = f"Invalid parameter {e}"
            logger(f"Invalid parameter: {e}")
            exit(1)

        df = pd.read_csv(path_to_csv)

        recompute_scalars: bool = overwrite


        # Get parameter to col map, overriding with user inputs if necessary
        # Generate default map
        parameter_to_col_map = {'Case ID': 'id', 'Original DTI Image': 'Original DTI image',
                                'Deformation Field': 'Concatenated Deformation field'}
        for scalar in ['FA', 'MD', 'AD', 'RD']:
            scalar_col = f'{scalar} from original'
            parameter_to_col_map[scalar] = scalar_col
        for scalar in properties_to_profile:
            scalar_col = f'{scalar} from original'
            parameter_to_col_map[scalar] = scalar_col

        # Update defaults with user overrides
        user_parameter_to_col_map = self.protocol['parameterToColumnHeaderMap']
        if user_parameter_to_col_map is not None:
            parameter_to_col_map.update(user_parameter_to_col_map)

        if input_is_dti:
            # check to see if the scalar images have already been generated
            # if not, generate them

            dtiprocess = tools.DTIProcess(self.software_info['dtiprocess']['path'])
            # Determine which scalars need to be generated
            scalars_to_generate = []
            for scalar in ['FA', 'MD', 'AD', 'RD']:
                scalar_col_header = parameter_to_col_map[scalar]
                scalars_to_generate.append(scalar)
                df[scalar_col_header] = ''  # initialize the column as a string

            for index, row in df.iterrows():
                subject_id = str(row[parameter_to_col_map['Case ID']])
                path_to_original_dti_image = row[parameter_to_col_map['Original DTI Image']]
                scalar_img_folder_path = Path(output_base_dir).joinpath("scalar_images").joinpath(subject_id)
                output_stem = scalar_img_folder_path.joinpath(Path(path_to_original_dti_image).stem).__str__()
                # check if scalar_img_folder_path already exists
                if scalar_img_folder_path.exists() and not recompute_scalars:
                    logger(f"Skipping recomputation of scalars {', '. join(scalars_to_generate)} for subject " + subject_id)
                else:
                    scalar_img_folder_path.mkdir(parents=True, exist_ok=True)
                    options = ['--correction', 'none', '--saveScalarsAsFloat']
                    # run dtiprocess to generate scalar images
                    dtiprocess.measure_scalar_list(path_to_original_dti_image, output_stem, scalars_to_generate, options)

                # update the dataframe with the paths to the scalar images
                for scalar in scalars_to_generate:
                    scalar_col = parameter_to_col_map[scalar]
                    scalar_img_path_str = output_stem.__str__() + '_' + scalar + '.nrrd'
                    df.at[index, scalar_col] = scalar_img_path_str

        # write the modified dataframe to the output directory
        df.to_csv(Path(output_base_dir).joinpath(Path(path_to_csv).stem.__str__() + '_with_scalars.csv'), index=False)

        parameterized_fibers_path = Path(output_base_dir).joinpath('parameterized_fibers')
        parameterized_fibers_path.mkdir(parents=True, exist_ok=True)
        # iterate over the rows of the CSV
        for prop in properties_to_profile:
            logger(f"Extracting property {prop} from column header '{parameter_to_col_map[prop]}'")
            prop_output_path: Path = Path(output_base_dir).joinpath(prop)
            for tract in tracts:
                # create the directory for the output for the scalar property
                tract_name_stem: str = Path(tract).stem
                tract_output_path: Path = prop_output_path.joinpath(tract_name_stem)
                tract_output_path.mkdir(parents=True, exist_ok=True)
                logger(f"Extracting profile for tract {tract}")
                tract_absolute_filename = Path(atlas_path).joinpath(
                    tract)  # concatenate the atlas path with the tract name
                # Create dataframe to track statistics for this tract
                tract_stat_df: pd.DataFrame = None
                for row_index, row in df.iterrows():
                    subject_id = row.iloc[0]
                    # Find path to scalar image in the dataframe
                    scalar_img_path = row[parameter_to_col_map[prop]]
                    fiberprocess_output_path: str = tract_output_path.joinpath(
                        f'{subject_id}_' + tract.replace('_extracted_done', f'_{prop}_profile')).__str__()
                    fiberpostprocess_output_path: str = fiberprocess_output_path.__str__().replace('.vtk',
                                                                                                   '_processed.vtk')
                    dtitractstat_output_path: str = fiberpostprocess_output_path.replace('.vtk', '.fvp')
                    scalar_name = prop
                    if Path(fiberprocess_output_path).exists() and not recompute_scalars:
                        logger(f"Skipping fiberprocess of scalar {prop} for subject {subject_id}")
                    else:
                        # run fiberprocess
                        options = []
                        options += ['--scalarName', scalar_name]
                        options += ['--ScalarImage', scalar_img_path]
                        options += ['--no_warp']
                        if use_displacement_field:
                            options += ['--displacement_field', row[parameter_to_col_map['Deformation Field']]]
                        fiberprocess = tools.FiberProcess(self.software_info['fiberprocess']['path'])
                        fiberprocess.run(tract_absolute_filename.__str__(), fiberprocess_output_path,
                                         options=options)


                    if Path(fiberpostprocess_output_path).exists() and not recompute_scalars:
                        logger(f"Skipping fiberpostprocess of scalar {prop} for subject {subject_id}")
                    else:
                        # run fiberpostprocess
                        options = []
                        if mask is not None:
                            options += ['--mask', mask]
                        if noNaN:
                            options += ['--noNan']
                        fiberpostprocess = tools.FiberPostProcess(self.software_info['fiberpostprocess']['path'])
                        fiberpostprocess.run(fiberprocess_output_path.__str__(), fiberpostprocess_output_path, options=options)
                    if Path(dtitractstat_output_path).exists() and not recompute_scalars:
                        logger(f"Skipping dtitractstat of scalar {prop} for subject {subject_id}")
                    else:
                        # run dtitractstat
                        options = ['--parameter_list', prop, '--scalarName', prop]
                        if row_index == 0:
                            logger(f"Generating parameterized fiber profile for tract {tract}")
                            tract_name_stem: str = Path(tract).stem
                            parameterized_fiber_output_path: Path = Path(parameterized_fibers_path).joinpath(
                                tract_name_stem + "_parameterized.vtk")
                            if parameterized_fiber_output_path.exists() and not recompute_scalars:
                                logger(f"Skipping parameterized fiber generation of tract {tract}")
                            else:
                                logger(f"Generating parameterized fiber profile for tract {tract}")
                                tract_absolute_filename = Path(atlas_path).joinpath(
                                    tract)
                                options += ['-f', parameterized_fiber_output_path.__str__()]
                                options += ['--step_size', step_size]
                                options += ['--bandwidth', support_bandwidth]
                                options += ['--auto_plane_origin', plane_of_origin.lower()]
                                if noNaN:
                                    options += ['--remove_nan_fibers']
                        dtitractstat = tools.DTITractStat(self.software_info['dtitractstat']['path'])
                        dtitractstat.run(fiberpostprocess_output_path, dtitractstat_output_path, options=options)

                    # extract fvp data
                    fvp_data = pd.read_csv(dtitractstat_output_path, skiprows=[0, 1, 2, 3])

                    # write fvp data to csv
                    if tract_stat_df is None:
                        if result_case_columnwise:
                            tract_stat_df = pd.DataFrame(columns=["Arc Length"])
                            tract_stat_df["Arc Length"] = fvp_data["Arc_Length"].tolist()
                        else:
                            col_list = ['case_id'] + fvp_data["Arc_Length"].tolist()
                            tract_stat_df = pd.DataFrame(columns=col_list)

                    if result_case_columnwise:
                        new_col = fvp_data["Parameter_Value"].tolist()
                        tract_stat_df[subject_id] = new_col
                    else:
                        new_row_list = [subject_id] + fvp_data["Parameter_Value"].tolist()
                        tract_stat_df.loc[len(tract_stat_df)] = dict(zip(tract_stat_df.columns, new_row_list))

                tract_stat_df.to_csv(prop_output_path.joinpath(f'{tract_name_stem}_{prop}.csv'), index=False)

        self.result['output']['success'] = True
        return self.result




