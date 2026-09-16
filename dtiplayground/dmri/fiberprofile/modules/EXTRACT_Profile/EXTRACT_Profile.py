import os.path
import shutil
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

import dtiplayground.dmri.common as common
import dtiplayground.dmri.fiberprofile as base
import dtiplayground.dmri.common.fibers as fibers

logger = common.logger.write

TENSOR_PROPERTIES = ['FA', 'MD', 'AD', 'RD']

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
            tensor_interpolation: str = self.protocol.get("tensorInterpolation", "logEuclidean")
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
            # properties are computed from the tensors interpolated along the fibers
            unsupported = [prop for prop in properties_to_profile if prop.upper() not in TENSOR_PROPERTIES]
            if len(unsupported) > 0:
                raise Exception(f"Properties {unsupported} can't be computed from a DTI (supported: {', '.join(TENSOR_PROPERTIES)})")

        # tract geometry (atlas space) is the same for all subjects: mask, plane, arc lengths and sample positions
        parameterized_fibers_path = Path(output_base_dir).joinpath('parameterized_fibers')
        parameterized_fibers_path.mkdir(parents=True, exist_ok=True)
        use_mask = mask is not None and str(mask).strip() != ''
        tract_infos = []
        for tract in tracts:
            tract_name_stem: str = Path(tract).stem
            if os.path.isabs(tract):
                tract_absolute_filename = Path(tract)
            else:
                tract_absolute_filename = Path(atlas_path).joinpath(tract)  # concatenate the atlas path with the tract name
            logger(f"Preparing tract {tract_absolute_filename}")
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
            tract_infos.append({'tract': tract, 'name': tract_name_stem, 'bundle': bundle, 'arcs': arcs, 'grid': grid})

        profiles = {(info['name'], prop): {} for info in tract_infos for prop in properties_to_profile}  # subject id -> profile values
        intermediate_dirs = []
        for row_index, row in df.iterrows():
            subject_id = str(row[parameter_to_col_map['Case ID']])
            displacement_field = None
            images = {}  # images of this subject, read once for all tracts
            for info in tract_infos:
                tract = info['tract']
                todo = []
                for prop in properties_to_profile:
                    tract_output_path: Path = Path(output_base_dir).joinpath(prop).joinpath(info['name'])
                    tract_output_path.mkdir(parents=True, exist_ok=True)
                    if tract_output_path not in intermediate_dirs:
                        intermediate_dirs.append(tract_output_path)
                    profile_name = f'{subject_id}_' + Path(tract).name.replace('_extracted_done', f'_{prop}_profile')  ## file name only, tract may be an absolute path
                    fiber_output_path = tract_output_path.joinpath(profile_name)
                    fvp_output_path = tract_output_path.joinpath(Path(profile_name).stem + '.fvp')
                    if fvp_output_path.exists() and not overwrite:
                        fvp_data = pd.read_csv(fvp_output_path, skiprows=[0, 1, 2, 3])
                        if len(fvp_data) == len(info['grid']) and np.allclose(fvp_data["Arc_Length"].to_numpy(), info['grid'], atol=1e-4):
                            logger(f"Skipping profile of {prop} for subject {subject_id} and tract {tract}, using {fvp_output_path}")
                            profiles[(info['name'], prop)][subject_id] = fvp_data["Parameter_Value"].to_numpy()
                            continue
                    todo.append((prop, fiber_output_path, fvp_output_path))
                if len(todo) == 0:
                    continue

                if use_displacement_field and displacement_field is None:
                    displacement_field_path = row[parameter_to_col_map['Deformation Field']]
                    if not isinstance(displacement_field_path, str) or displacement_field_path.strip() == '':
                        raise Exception(f"No deformation field for subject {subject_id} (column '{parameter_to_col_map['Deformation Field']}')")
                    displacement_field = fibers.Image(displacement_field_path)
                logger(f"Sampling {', '.join(p for p, _, _ in todo)} of subject {subject_id} along tract {tract}")
                if input_is_dti:
                    if 'dti' not in images:
                        images['dti'] = fibers.TensorImage(row[parameter_to_col_map['Original DTI Image']])
                    tensors = fibers.sample_tensors(info['bundle'], images['dti'], displacement_field, tensor_interpolation)
                    scalars = fibers.tensor_scalars(tensors)
                    sampled = {prop: scalars[prop.upper()] for prop, _, _ in todo}
                else:
                    sampled = {}
                    for prop, _, _ in todo:
                        if prop not in images:
                            images[prop] = fibers.Image(row[parameter_to_col_map[prop]])
                        sampled[prop] = fibers.sample_scalar(info['bundle'], images[prop], displacement_field)

                for prop, fiber_output_path, fvp_output_path in todo:
                    subject_bundle = fibers.FiberBundle(info['bundle'].points, info['bundle'].offsets, {prop: sampled[prop], 'ArcLength': info['arcs']})
                    if noNaN:
                        keep = fibers.fibers_without_nan(info['bundle'], sampled[prop])
                        if not np.all(keep):
                            logger(f"Removing {int(np.sum(~keep))} fibers with NaN {prop} values for subject {subject_id} and tract {tract}")
                        subject_bundle = subject_bundle.select(keep)
                    fibers.write_fibers(subject_bundle, fiber_output_path)
                    profile = fibers.gaussian_profile(subject_bundle.point_data['ArcLength'], subject_bundle.point_data[prop], info['grid'], support_bandwidth)
                    fibers.write_fvp(fvp_output_path, profile, prop, step_size, support_bandwidth)
                    profiles[(info['name'], prop)][subject_id] = profile['mean']
                    if cleanupMethod == CleanupMethod.DURING:
                        fiber_output_path.unlink()
                        fvp_output_path.unlink()

        # save the profiles of all subjects (same arc length samples) to a csv per tract and property
        for info in tract_infos:
            for prop in properties_to_profile:
                subject_profiles = profiles[(info['name'], prop)]
                if result_case_columnwise:
                    tract_stat_df = pd.DataFrame({"Arc Length": info['grid'], **subject_profiles})
                else:
                    tract_stat_df = pd.DataFrame([[subject_id] + list(values) for subject_id, values in subject_profiles.items()],
                                                 columns=['case_id'] + ['{:g}'.format(a) for a in info['grid']])
                tract_stat_df.to_csv(Path(output_base_dir).joinpath(prop).joinpath(f"{info['name']}_{prop}.csv"), index=False, float_format='%.6g')  ## same precision as the .fvp files

        if cleanupMethod == CleanupMethod.END or cleanupMethod == CleanupMethod.DURING:
            for d in intermediate_dirs:
                if d.exists():
                    shutil.rmtree(d)
        self.result['output']['success'] = True
        return self.result




