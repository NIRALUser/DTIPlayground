import os.path
import shutil
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

import dtiplayground.dmri.common as common
import dtiplayground.dmri.fiberprofile as base
from dtiplayground.dmri.common import tools
import dtiplayground.dmri.common.fibers as fibers

logger = common.logger.write

class CleanupMethod():
    DURING = 'duringProcessing'
    END = 'endOfProcessing'
    NONE = 'noCleanup'
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

            tracts_string: str = self.protocol["tracts"]
            if not isinstance(tracts_string, str):
                raise ValueError("Tracts must be a string of comma delimited tracts to profile")
            tracts: List[str] = [tract.strip() for tract in tracts_string.split(',') if tract.strip() != '']
            if len(tracts) == 0:
                raise ValueError("Tracts must be a non-empty list of tracts to profile")
            atlas_path: str = self.protocol["atlas"]
            if not isinstance(atlas_path, str):
                for tract in tracts:
                    if not os.path.isabs(tract):
                        raise ValueError(
                            f"Tract paths must all be absolute if no atlas path is provided. Atlas path current value: {atlas_path}. Either provide atlas dir or convert this path to absolute: {tract}")
            properties_to_profile: List[str] = [x.strip() for x in self.protocol["propertiesToProfile"].split(',') if x.strip() != '']
            result_case_columnwise: bool = self.protocol["resultCaseColumnwise"]
            input_is_dti: bool = self.protocol["inputIsDTI"]
            overwrite: bool = self.options['overwrite']
            use_displacement_field: bool = self.protocol["useDisplacementField"]
            step_size: float = float(self.protocol["stepSize"])
            plane_of_origin: str = self.protocol["planeOfOrigin"]
            support_bandwidth: float = float(self.protocol["supportBandwidth"])
            noNaN: bool = self.protocol["noNaN"]
            mask: str = self.protocol["mask"]
            mask_threshold: float = float(self.protocol.get("maskThreshold", 0.5))
            cleanupMethod: str = self.protocol["cleanup"]
            if cleanupMethod not in [CleanupMethod.DURING, CleanupMethod.NONE, CleanupMethod.END]:
                raise ValueError(f"Invalid cleanup method: {cleanupMethod}")
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
        use_mask = mask is not None and str(mask).strip() != ''
        intermediate_dirs = []
        for tract in tracts:
            tract_name_stem: str = Path(tract).stem
            if os.path.isabs(tract):
                tract_absolute_filename = Path(tract)
            else:
                tract_absolute_filename = Path(atlas_path).joinpath(tract)  # concatenate the atlas path with the tract name
            logger(f"Preparing tract {tract_absolute_filename}")

            # tract geometry (atlas space) is the same for all subjects: mask, plane, arc lengths and sample positions
            bundle = fibers.read_fibers(tract_absolute_filename)
            if use_mask:
                keep = fibers.fiber_mask_average(bundle, mask) > mask_threshold
                logger(f"Mask {mask}: {int(np.sum(keep))} of {bundle.number_of_fibers} fibers have an average mask value above {mask_threshold}")
                if not np.any(keep):
                    raise Exception(f"No fiber of tract {tract} is inside the mask {mask}")
                bundle = bundle.select(keep)
            origin, normal = fibers.find_plane(bundle, plane_of_origin)
            logger(f"Plane of origin ({plane_of_origin}) : origin {origin.tolist()}, normal {normal.tolist()}")
            arcs = fibers.arc_lengths(bundle, origin, normal)
            grid = fibers.profile_grid(arcs, step_size)

            parameterized_fiber_output_path: Path = parameterized_fibers_path.joinpath(tract_name_stem + "_parameterized.vtk")
            if parameterized_fiber_output_path.exists() and not overwrite:
                logger(f"Skipping parameterized fiber generation of tract {tract}")
            else:
                logger(f"Generating parameterized fibers for tract {tract}")
                fibers.write_parameterized_fibers(bundle, arcs, grid, parameterized_fiber_output_path)

            for prop in properties_to_profile:
                logger(f"Extracting property {prop} from column header '{parameter_to_col_map[prop]}' for tract {tract}")
                prop_output_path: Path = Path(output_base_dir).joinpath(prop)
                tract_output_path: Path = prop_output_path.joinpath(tract_name_stem)
                tract_output_path.mkdir(parents=True, exist_ok=True)
                intermediate_dirs.append(tract_output_path)
                profiles = {}  # subject id -> profile values on the grid
                for row_index, row in df.iterrows():
                    subject_id = str(row[parameter_to_col_map['Case ID']])
                    profile_name = f'{subject_id}_' + Path(tract).name.replace('_extracted_done', f'_{prop}_profile')  ## file name only, tract may be an absolute path
                    fiber_output_path = tract_output_path.joinpath(profile_name)
                    fvp_output_path = tract_output_path.joinpath(Path(profile_name).stem + '.fvp')

                    values = None
                    if fvp_output_path.exists() and not overwrite:
                        fvp_data = pd.read_csv(fvp_output_path, skiprows=[0, 1, 2, 3])
                        if len(fvp_data) == len(grid) and np.allclose(fvp_data["Arc_Length"].to_numpy(), grid, atol=1e-4):
                            logger(f"Skipping profile of {prop} for subject {subject_id}, using {fvp_output_path}")
                            values = fvp_data["Parameter_Value"].to_numpy()
                    if values is None:
                        displacement_field = None
                        if use_displacement_field:
                            displacement_field = row[parameter_to_col_map['Deformation Field']]
                            if not isinstance(displacement_field, str) or displacement_field.strip() == '':
                                raise Exception(f"No deformation field for subject {subject_id} (column '{parameter_to_col_map['Deformation Field']}')")
                        sampled = fibers.sample_scalar(bundle, row[parameter_to_col_map[prop]], displacement_field)
                        subject_bundle = fibers.FiberBundle(bundle.points, bundle.offsets, {prop: sampled, 'ArcLength': arcs})
                        if noNaN:
                            keep = fibers.fibers_without_nan(bundle, sampled)
                            if not np.all(keep):
                                logger(f"Removing {int(np.sum(~keep))} fibers with NaN {prop} values for subject {subject_id}")
                            subject_bundle = subject_bundle.select(keep)
                        fibers.write_fibers(subject_bundle, fiber_output_path)
                        profile = fibers.gaussian_profile(subject_bundle.point_data['ArcLength'], subject_bundle.point_data[prop], grid, support_bandwidth)
                        fibers.write_fvp(fvp_output_path, profile, prop, step_size, support_bandwidth)
                        values = profile['mean']
                        if cleanupMethod == CleanupMethod.DURING:
                            logger(f"Cleaning up intermediate files for subject {subject_id} and tract {tract}")
                            fiber_output_path.unlink()
                            fvp_output_path.unlink()
                    profiles[subject_id] = values

                # save the profiles of all subjects (same arc length samples) to a csv
                if result_case_columnwise:
                    tract_stat_df = pd.DataFrame({"Arc Length": grid, **profiles})
                else:
                    tract_stat_df = pd.DataFrame([[subject_id] + list(values) for subject_id, values in profiles.items()],
                                                 columns=['case_id'] + ['{:g}'.format(a) for a in grid])
                tract_stat_df.to_csv(prop_output_path.joinpath(f'{tract_name_stem}_{prop}.csv'), index=False, float_format='%.6g')  ## same precision as the .fvp files

        if cleanupMethod == CleanupMethod.END or cleanupMethod == CleanupMethod.DURING:
            for d in dict.fromkeys(intermediate_dirs):
                if d.exists():
                    shutil.rmtree(d)
        self.result['output']['success'] = True
        return self.result




