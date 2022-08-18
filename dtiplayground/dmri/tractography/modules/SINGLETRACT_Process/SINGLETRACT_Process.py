  
import dtiplayground.dmri.tractography as base
import yaml, os
from pathlib import Path
import dtiplayground.dmri.common.tools as tools 
import dtiplayground.dmri.common as common

###
import SINGLETRACT_Process.tractography as tractography

logger=common.logger.write
class SINGLETRACT_Process(base.modules.DTITractographyModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        p = self.protocol['NIRALUtilitiesPath'].replace('$NIRALUTILS', self.softwares['niral_utilities']['path'])
        self.protocol['NIRALUtilitiesPath'] = p 

        if 'reference_tract' in self.global_variables:
            self.protocol['referenceTractFile'] = Path(self.global_variables['reference_tract']).resolve().__str__()
        ## todos
        return self.protocol
        
    @common.measure_time
    def process(self,*ar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gs,**kwargs): ## variables : self.global_variables, self.softwares, self.output_dir, self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        protocol_options=args[0]
        self.num_threads=protocol_options['software_info']['parameters']['num_max_threads']
        self.baseline_threshold=protocol_options['baseline_threshold']

        # << TODOS>>
        if self.protocol['method'] == 'NIRAL':
            res = self.singletract_niral(**self.protocol)
        elif self.protocol['method'] == 'dipy':
            res = self.singletract_dipy(**self.protocol)
        else:
            raise Exception("No such method")

        logger(yaml.dump(self.image.information))
        self.result['output']['success']=True

        return self.result

    def singletract_niral(self, **protocol):
        res = {}
        inputDTI = Path(self.output_dir).joinpath('input.nrrd').__str__()
        if 'dti_path' in self.global_variables:
            inputDTI = self.global_variables['dti_path']
        else:
            self.writeImageWithOriginalSpace(inputDTI,'nrrd',dtype='float')
        inputFiberFile = protocol['referenceTractFile']
        displacementField = protocol['displacementFieldFile']
        if not displacementField:
            displacementField = self.global_variables['displacement_field_path']
            if not Path(self.global_variables['displacement_field_path']).exists():
                raise Exception("Couldn't find the displacement field file")

        outputFiberTract = Path(self.output_dir).joinpath('registered_ref_tract.vtk').__str__()
        
    # Register reference tract with the displacement field 
        niralutils = tools.NIRALUtilities(softwares=self.softwares)
        niralutils.dev_mode=True
        arguments = ['--polydata_input', inputFiberFile,
                     '-o', outputFiberTract,
                     '-D', displacementField,
                     '--inverty',
                     '--invertx']
        if self.overwriteFile(outputFiberTract) : output=niralutils.polydatatransform(arguments)
        self.addGlobalVariable('reference_tract_path', outputFiberTract) ## update tract path to the updated one

    ## Dilation and voxelization of the mapped reference tracts , getting labelmap
        labelMapFile = Path(self.output_dir).joinpath('labelmap.nrrd').__str__()
        arguments = ['--voxelize', labelMapFile,
                     '--fiber_file', outputFiberTract,
                     '-T', inputDTI]
        fiberprocess = tools.FiberProcess(softwares=self.softwares)
        fiberprocess.dev_mode = True
        if self.overwriteFile(labelMapFile) : fiberprocess.execute(arguments=arguments)
        self.addGlobalVariable('labelmap_path', labelMapFile)

    ## Dilation and voxelization of the reference tracts
        dilatedLabelmapFile = Path(self.output_dir).joinpath('labelmap_dilated.nrrd').__str__()
        dilationRadius = self.protocol['dilationRadius']
        imagemath = tools.ImageMath(softwares=self.softwares)
        imagemath.dev_mode=True
        arguments = [labelMapFile,
                     '-dilate', str(dilationRadius)+',1',
                     '-outfile', dilatedLabelmapFile
                     ]
        if self.overwriteFile(dilatedLabelmapFile) : imagemath.execute(arguments=arguments)
        self.addGlobalVariable('labelmap_path', dilatedLabelmapFile)
        labelMapImage = common.dwi.DWI(labelMapFile)
        dilatedLabelmapImage = common.dwi.DWI(dilatedLabelmapFile)
        dipyLabelMap = labelMapImage.images + dilatedLabelmapImage.images

    ## Tractography ...
        tensorImage = common.dwi.DWI(inputDTI)
        tractography.compute(tensorImage, self.image, dipyLabelMap, self.output_dir )
        return res 


    def singletract_dipy(self, **protocol):
        res = {}
        return res 
