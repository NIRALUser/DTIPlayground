import yaml
from pathlib import Path
import pandas
import os
import fnmatch
import SimpleITK as sitk
import numpy
from PIL import Image
import markdown
from markdown import extensions
from dtiplayground.dmri.common.dwi import DWI

import dtiplayground.dmri.preprocessing as prep

IMAGE_QC_FILES = ('image_qc.tsv', 'image_ndc.tsv', 'image_qc.png') # summary, per volume, figure


class QC_Report(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir,*args,**kwargs)
        global logger
        logger = self.logger.write

    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>
        for name in IMAGE_QC_FILES: ## computed again for this run
            Path(self.output_dir).joinpath(name).unlink(missing_ok=True)
        image_qc = self.imageQC() if self.protocol.get('imageQC', True) else {}
        global_report = ""
        if self.protocol["generatePDF"] == True:
            global_report = self.MergeReports(global_report)
            global_report, number_input_gradients, excluded_gradients, number_of_excluded_gradients = self.AddGeneralInfo(global_report)
            global_report = self.AddImageQCToReport(global_report, image_qc)
            info_display_QCed_gradients = self.CreateImages()
            if number_of_excluded_gradients != 0:
                global_report = self.AddExcludedGradientsImagesToReport(global_report, excluded_gradients)
            global_report = self.AddGradientImagesToReport(global_report, info_display_QCed_gradients[0])
            html_path = self.GenerateReportFiles(global_report)
            self.full_report = global_report # written again after the module report of the base class (makeReport)
            with open(html_path, "r", encoding="utf-8") as f:
                html_data = f.read()
            pdf_path = self.output_dir+"/QC_report.pdf"
            result_file = open(pdf_path, "w+b")
            from xhtml2pdf import pisa
            pisa.CreatePDF(html_data, dest=result_file)
            result_file.close()
            self.addOutputFile(pdf_path, "QC_report")

        if self.protocol["generateCSV"] == True:
            if self.protocol['generatePDF'] == False:
                global_report, number_input_gradients, excluded_gradients, number_of_excluded_gradients = self.AddGeneralInfo(global_report)
            self.CreateCSV(number_input_gradients, number_of_excluded_gradients, image_qc)

        self.result['output']['success']=True
        return self.result

    def MergeReports(self, global_report):        
        for module in self.result_history[1:]:
            if module["module_name"] == "SUSCEPTIBILITY_Correct":
                for report_file in module['report']['module_report_paths'][0]:
                    with open(report_file, 'r') as f:
                        text = f.read()
                        global_report += text
                global_report += "* * * * \n"
                for report_file in module['report']['module_report_paths'][1]:
                    with open(report_file, 'r') as f:
                        text = f.read()
                        global_report += text
                global_report += "* * * * \n"
                with open(module['report']['module_report_paths'][2], 'r') as f:
                    text = f.read()
                    global_report += text
            else:
                with open(module['report']['module_report_paths'], 'r') as f:
                    text = f.read()
                    global_report += text
        global_report += "* * * * \n"
        return(global_report)

    def AddGeneralInfo(self, global_report):
        single_input = True
        for module in self.result_history[1:]:
            if module["module_name"] == "SUSCEPTIBILITY_Correct":
                single_input = False

        if single_input:
            number_input_gradients = self.result_history[1]['report']['csv_data']['original_number_of_gradients']
            excluded_gradients = []
            for module in self.result_history[1:]:
                if module['report']['csv_data']['excluded_gradients']:
                    excluded_gradients += module['report']['csv_data']['excluded_gradients']

        else: #SUSCEPTIBILITY_Correct in protocol
            number_input_gradients = self.result_history[1]['report']['csv_data']['original_number_of_gradients'][0] + self.result_history[1]['report']['csv_data']['original_number_of_gradients'][1]
            excluded_gradients = [[], [], []]
            if self.result_history[1]['report']['csv_data']['excluded_gradients']:
                if self.result_history[1]['report']['csv_data']['excluded_gradients'][0]:
                    excluded_gradients[0] = self.result_history[1]['report']['csv_data']['excluded_gradients'][0]
                if self.result_history[1]['report']['csv_data']['excluded_gradients'][1]:
                    excluded_gradients [1] = self.result_history[1]['report']['csv_data']['excluded_gradients'][1]
                if self.result_history[1]['report']['csv_data']['excluded_gradients'][2]:
                    excluded_gradients [2] = self.result_history[1]['report']['csv_data']['excluded_gradients'][2]
            for module in self.result_history[2:]:
                if module['report']['csv_data']['excluded_gradients']:
                    excluded_gradients[2] += module['report']['csv_data']['excluded_gradients']
        
        global_report += "## Total: \n"
        if len(excluded_gradients) == 0:
            number_of_excluded_gradients = 0
        elif type(excluded_gradients[0]) == list:
            number_of_excluded_gradients = len(excluded_gradients[0])+len(excluded_gradients[1])+len(excluded_gradients[2])
        else:
            number_of_excluded_gradients = len(excluded_gradients)
        if number_of_excluded_gradients == 0:
            global_report += "* 0 gradient excluded or corrected out of " + str(number_input_gradients) + "\n"
        elif number_of_excluded_gradients == 1:
            global_report += "* 1 gradient excluded or corrected out of " + str(number_input_gradients) + "\n"
        else:
            global_report += "* " + str(number_of_excluded_gradients) + " gradients excluded or corrected out of " + str(number_input_gradients) + "\n"
        global_report += "* " + str(round((number_input_gradients - number_of_excluded_gradients)/number_input_gradients*100, 2)) + "% of original gradients are preserved \n"
        global_report += "* * * * \n"
            
        return(global_report, number_input_gradients, excluded_gradients, number_of_excluded_gradients)


    ## Image QC: the same numbers on the raw input and on the preprocessed image

    def imageQCStages(self):
        """[(label, prefix, image)] of the images that are compared: the input of the pipeline (its first image when
        the pipeline has two) and the image of this report."""
        stages = []
        image_name = self.result_history[1]['report']['csv_data']['image_name']
        raw = image_name[0] if isinstance(image_name, list) else image_name
        if raw and Path(raw).exists():
            stages.append(('raw', 'raw', DWI(str(raw))))
        stages.append(('preprocessed', 'qced', self.image))
        return stages

    def imageQC(self):
        """Neighboring DWI correlation, bad slices and the b-table fiber coherence index of the raw input and of the
        preprocessed image (image_qc.tsv summary, image_ndc.tsv per volume, image_qc.png), computed once per run of
        the module. {} if it fails."""
        from dtiplayground.dmri.preprocessing import qc_metrics
        out = Path(self.output_dir)
        paths = [out.joinpath(n) for n in IMAGE_QC_FILES]
        try:
            if not all(p.exists() for p in paths):
                summary, per_volume, stages = {}, [], {}
                for label, prefix, image in self.imageQCStages():
                    logger("Image QC of the {} image ...".format(label), prep.Color.PROCESS)
                    gradients = image.getGradients()
                    bvals = numpy.array([g['b_value'] for g in gradients], dtype=float)
                    ## the components along the voxel axes: the coherence index compares them with the neighboring voxels
                    bvecs = numpy.array([g['nifti_gradient'] for g in gradients], dtype=float)
                    data = image.images
                    spacing = qc_metrics.voxel_spacing(image.information)
                    b0_threshold = min(max(min(bvals), 50), 199)
                    mask = self.imageQCMask(data, bvals, b0_threshold)
                    rows, values = qc_metrics.image_qc(data, bvals, bvecs, mask, spacing=spacing,
                                                       coherence=self.protocol.get('bTableCheck', True),
                                                       b0_threshold=b0_threshold)
                    for i, r in enumerate(rows):
                        r['original_index'] = gradients[i].get('original_index', i)
                        r['stage'] = label
                    summary.update({'{}_{}'.format(prefix, k): v for k, v in values.items()})
                    per_volume += rows
                    stages[label] = rows
                qc_metrics.write_tsv(str(paths[1]), per_volume,
                                     ['stage', 'volume', 'original_index', 'bval', 'neighbor', 'ndc', 'bad_slices'])
                qc_metrics.image_qc_plot(str(paths[2]), stages,
                                         title='Neighboring DWI correlation and bad slices, before and after preprocessing')
                qc_metrics.write_tsv(str(paths[0]), [summary])
            summary = {k: v for k, v in qc_metrics.read_tsv(str(paths[0]))[0].items() if v != ''}
        except Exception as e:
            logger("Image QC could not be computed: {}".format(e), prep.Color.WARNING)
            return {}
        for p, postfix in zip(paths, ('IMAGE_QC', 'IMAGE_ndc', 'IMAGE_QC_plot')):
            self.addOutputFile(str(p), postfix)
        return summary

    def imageQCMask(self, data, bvals, b0_threshold):
        """The brain mask of the pipeline when it fits the image, otherwise a rough one (median_otsu)."""
        from dtiplayground.dmri.preprocessing import qc_metrics
        mask_path = self.getGlobalVariables().get('mask_path')
        if mask_path and Path(mask_path).exists():
            mask = numpy.squeeze(DWI(str(mask_path)).images) > 0
            if mask.shape == data.shape[:3]:
                return mask
        return qc_metrics.brain_mask(data, bvals, b0_threshold)

    def AddImageQCToReport(self, global_report, image_qc):
        if not image_qc:
            return global_report
        def value(name, digits=None):
            v = image_qc.get(name, '')
            return round(float(v), digits) if digits is not None and v != '' else v
        global_report += "## Image QC (raw input / preprocessed): \n"
        global_report += "* Neighboring DWI correlation: {} / {} (each volume with the volume of the same shell in the closest direction)\n".format(
            value('raw_ndc', 4), value('qced_ndc', 4))
        global_report += "* Bad slices: {} ({}%) / {} ({}%)\n".format(
            value('raw_bad_slices'), value('raw_bad_slices_percent'), value('qced_bad_slices'), value('qced_bad_slices_percent'))
        if image_qc.get('qced_coherence', '') != '':
            global_report += "* b-table fiber coherence index: {} / {}\n".format(value('raw_coherence', 4), value('qced_coherence', 4))
            flip = image_qc.get('qced_coherence_best_flip', 'none')
            if flip and flip != 'none':
                global_report += "* **The coherence index is higher with the {} axis of the b-vectors flipped ({} instead of {}): check the gradient directions**\n".format(
                    flip, value('qced_coherence_best', 4), value('qced_coherence', 4))
            else:
                global_report += "* The b-table as given has the highest coherence index (no flipped axis)\n"
        image = Path(self.output_dir).joinpath(IMAGE_QC_FILES[2])
        if image.exists():
            global_report += "\n<img src='{}' width='640'>\n".format(image)
        global_report += "\n* * * * \n"
        return global_report

    def AddExcludedGradientsImagesToReport(self, global_report, excluded_gradients):
        global_report += "\n## Excluded DWIs:\n"
        image_path = self.result_history[1]['report']['csv_data']['image_name']
        if type(excluded_gradients[0]) == int:
            excluded_gradients = [excluded_gradients]
            image_path = [image_path]
        for image_index in range(len(image_path)):
            if len(excluded_gradients[image_index]) != 0:
                images = self.CreateImagesOfExcludedGradients(image_path[image_index], excluded_gradients[image_index])
                # logger(str(self.image[image_index]))
                # casted_image = list(self.image[image_index][0])
                # logger(str(casted_image))
                #images = self.CreateImagesOfExcludedGradients(casted_image, excluded_gradients[image_index])

                global_report += "#### " + str(image_path[image_index]) + "\n"
                global_report += "<table><tbody>\n"
                for gradient_index in range(len(excluded_gradients[image_index])):
                    if gradient_index % 2 == 0:
                        global_report += "<tr>\n"
                    global_report += "<td><figure><img src="+str(images[gradient_index])+" alt='DWI "+str(excluded_gradients[image_index][gradient_index])+"' width='260'><figcaption>DWI "+str(excluded_gradients[image_index][gradient_index])+"</figcaption></figure></td>\n"
        
                    #html = "<figure><img src="+image_path[image_index]+" alt='DWI "+str(gradient_index)+"' style='width:48%'><figcaption>DWI "+str(gradient_index)+"</figcaption></figure>"
                    #global_report += html
                    if gradient_index % 2 != 0:
                        global_report += "</tr>\n"
                global_report += "</tbody></table>\n"
        global_report += "\n* * * * \n"
        return(global_report)




    def AddGradientImagesToReport(self, global_report, number_of_gradients):
        global_report += "\n## QCed volume DWIs: \n"
        global_report += "<table><tbody>\n"
        ## labelled with the original gradient index (the images dwi<i>.jpg follow the remaining volumes)
        gradients = self.source_image.getGradients()
        labels = [g.get('original_index', i) for i, g in enumerate(gradients)] if len(gradients) == number_of_gradients else list(range(number_of_gradients))
        for gradient_index in range(number_of_gradients):  
            if gradient_index % 2 == 0:
                global_report += "<tr>\n"     
            global_report += "<td><figure><img src="+self.output_dir+"/QC_Report_images/dwi"+str(gradient_index)+".jpg alt='DWI "+str(labels[gradient_index])+"' width='260'><figcaption aligh='center'>DWI "+str(labels[gradient_index])+"</figcaption></figure></td>\n"      
            if gradient_index % 2 != 0:
                global_report += "</tr>\n"
        global_report += "</tbody></table>\n"
            
        #global_report += "![DWI" + str(gradient_index) + "](" + image_path + " 'DWI " + str(gradient_index) + "')"
        return(global_report)

    def CreateCSV(self, number_input_gradients, number_of_excluded_gradients, image_qc=None):
        single_input = True
        for module in self.result_history[1:]:
            if module["module_name"] == "SUSCEPTIBILITY_Correct":
                single_input = False

        if single_input:
            columns = ["image_name"]
            values = [self.result_history[1]['report']['csv_data']['image_name']]
        else:
            columns = ["image_name_1", "image_name_2"]
            values = [self.result_history[1]['report']['csv_data']['image_name'][0], self.result_history[1]['report']['csv_data']['image_name'][1]]
        ## original: input of the first module; remaining: the image of this report (after all modules)
        columns += ['original_number_of_gradients', 'remaining_number_of_gradients', 'number_of_excluded_gradients']
        values += [number_input_gradients, len(self.image.getGradients()), number_of_excluded_gradients]
        for module in self.result_history[1:]:
            if module["module_name"] == "EDDYMOTION_Correct":
                columns += ['rms_larger_than_1', 'rms_larger_than_2', 'rms_larger_than_3']
                values += [module['report']['csv_data']['rms_gt_1'], module['report']['csv_data']['rms_gt_2'], module['report']['csv_data']['rms_gt_3']]
            ## noise (DWI_Denoise), Gibbs correction, motion and SNR/CNR (EDDYMOTION_Correct), tensor fit (DTI_Estimate)
            for key in ('denoise_qc', 'gibbs_qc', 'eddy_qc', 'fit_qc'):
                for name, value in (module.get('report', {}).get('csv_data', {}).get(key) or {}).items():
                    if name not in columns:
                        columns.append(name)
                        values.append(value)
        ## image QC of the raw input and of the preprocessed image (this module)
        for name, value in (image_qc or {}).items():
            if name not in columns:
                columns.append(name)
                values.append(value)

        qc_report = pandas.DataFrame([values], columns = columns)
        path_output_directory = Path(self.output_dir).parent.parent
        csv_path = self.output_dir + "/QC_report.csv"
        qc_report.to_csv(csv_path, index=False)
        self.addOutputFile(csv_path, "QC_report")

    def makeReport(self):
        super().makeReport() # writes the generic module report.md/html: put the full report back
        if getattr(self, 'full_report', None) is not None:
            self.GenerateReportFiles(self.full_report)

    def GenerateReportFiles(self, global_report):
        with open(self.output_dir + '/report.md', 'bw+') as f:
            f.write(global_report.encode('utf-8'))
        markdown.markdownFromFile(input=self.output_dir+"/report.md", output=self.output_dir+"/report.html")
        return(self.output_dir + "/report.html")

    ## Images

    def CreateImages(self):
        
        target_space = self.getSourceImageInformation()['space']
        self.source_image.setSpaceDirection(target_space=target_space)

        input_image = sitk.GetImageFromArray(self.source_image.images)
        input_size = list(input_image.GetSize())

        input_number_gradients = list(self.source_image.images.shape)[3]
        
        output_images_directory = self.GetOutputImagesDirectory()
        for iter_gradients in range(input_number_gradients):  

            axial_image = self.AxialView(iter_gradients, input_size, input_image)
            axial_image = axial_image.rotate(270)
            sagittal_image = self.SagittalView(iter_gradients, input_size, input_image)
            sagittal_image = sagittal_image.rotate(90)
            coronal_image = self.CoronalView(iter_gradients, input_size, input_image)
            coronal_image = coronal_image.rotate(90)

            # concatenate
            width = axial_image.width + sagittal_image.width + coronal_image.width
            height = max(axial_image.height, sagittal_image.height, coronal_image.height)
            dwi_image = Image.new('L', (width, height), 0)
            dwi_image.paste(sagittal_image, (0, 0))
            dwi_image.paste(axial_image, (sagittal_image.width, 0))
            dwi_image.paste(coronal_image, (sagittal_image.width + axial_image.width, 0))
            dwi_image.save(output_images_directory + "/dwi" + str(iter_gradients) + ".jpg")
  
        info_display_QCed_gradients = [input_number_gradients, dwi_image.width, dwi_image.height]
        return info_display_QCed_gradients

    # def CreateImagesOfExcludedGradients(self, image_path, excluded_gradients):
    #     input_image = sitk.ReadImage(image_path)
    #     input_size = list(input_image.GetSize())
    #     logger('CreateExcludedGrad')
    #     logger(str(input_size))
    #     dwi_images_list = []
    #     output_images_directory = self.GetOutputImagesDirectory()
    #     for iter_gradients in excluded_gradients:  
    #         axial_image = self.AxialView(iter_gradients, input_size, input_image)
    #         axial_image = axial_image.rotate(180)
    #         sagittal_image = self.SagittalView(iter_gradients, input_size, input_image)
    #         coronal_image = self.CoronalView(iter_gradients, input_size, input_image)
    #         coronal_image = coronal_image.rotate(180)

    #         # concatenate
    #         width = axial_image.width + sagittal_image.width + coronal_image.width
    #         height = max(axial_image.height, sagittal_image.height, coronal_image.height)
    #         dwi_image = Image.new('L', (width, height), 0)
    #         dwi_image.paste(sagittal_image, (0, 0))
    #         dwi_image.paste(axial_image, (sagittal_image.width, 0))
    #         dwi_image.paste(coronal_image, (sagittal_image.width + axial_image.width, 0))
    #         dwi_image.save(output_images_directory + "/excluded_dwi" + str(iter_gradients) + ".jpg")
    #         dwi_images_list += [output_images_directory + "/excluded_dwi" + str(iter_gradients) + ".jpg"]

    #     return dwi_images_list


    def CreateImagesOfExcludedGradients(self, image_path, excluded_gradients):
        #input_image = sitk.ReadImage(image_path)
        loaded_img = DWI(image_path)
        input_image = sitk.GetImageFromArray(loaded_img.images)
        input_size = list(input_image.GetSize())
        # logger('CreateExcludedGrad')
        # logger(str(input_size))
        dwi_images_list = []
        output_images_directory = self.GetOutputImagesDirectory()
        for iter_gradients in excluded_gradients:  
            axial_image = self.AxialView(iter_gradients, input_size, input_image)
            axial_image = axial_image.rotate(180)
            sagittal_image = self.SagittalView(iter_gradients, input_size, input_image)
            coronal_image = self.CoronalView(iter_gradients, input_size, input_image)
            coronal_image = coronal_image.rotate(180)

            # concatenate
            width = axial_image.width + sagittal_image.width + coronal_image.width
            height = max(axial_image.height, sagittal_image.height, coronal_image.height)
            dwi_image = Image.new('L', (width, height), 0)
            dwi_image.paste(sagittal_image, (0, 0))
            dwi_image.paste(axial_image, (sagittal_image.width, 0))
            dwi_image.paste(coronal_image, (sagittal_image.width + axial_image.width, 0))
            dwi_image.save(output_images_directory + "/excluded_dwi" + str(iter_gradients) + ".jpg")
            dwi_images_list += [output_images_directory + "/excluded_dwi" + str(iter_gradients) + ".jpg"]

        return dwi_images_list
    def GetOutputImagesDirectory(self):
        if not os.path.exists(self.output_dir + "/QC_Report_images"):
            os.mkdir(self.output_dir + "/QC_Report_images")
        return str(self.output_dir) + "/QC_Report_images"

    def SagittalView(self, iter_gradients, input_size, input_image):
        slice_extractor = sitk.ExtractImageFilter()  
        slice_extractor.SetSize([input_size[0], input_size[1], 0])
        slice_extractor.SetIndex([0, 0, input_size[2]//2])
        extracted_slice = slice_extractor.Execute(input_image)

        gradient_extractor = sitk.VectorIndexSelectionCastImageFilter()
        gradient_extractor.SetIndex(iter_gradients)
        gradient = gradient_extractor.Execute(extracted_slice)
        
        gradient_array = sitk.GetArrayFromImage(gradient)
        gradient_array_normalized = (gradient_array - numpy.min(gradient_array)) * round(255 / numpy.max(gradient_array), 3)
        gradient_image = Image.fromarray(gradient_array_normalized)
        gradient_image = gradient_image.convert("L")
        dimension = max(gradient_image.height, gradient_image.width)
        square_image = Image.new('L', (dimension, dimension), 0)
        square_image.paste(gradient_image, ((dimension-gradient_image.width)//2, (dimension-gradient_image.height)//2))
        return square_image

    def AxialView(self, iter_gradients, input_size, input_image):
        
        slice_extractor = sitk.ExtractImageFilter()
        # logger(str(input_size))
        slice_extractor.SetSize([0, input_size[1], input_size[2]])

        slice_extractor.SetIndex([input_size[0]//2, 0, 0])
        extracted_slice = slice_extractor.Execute(input_image)

        gradient_extractor = sitk.VectorIndexSelectionCastImageFilter()
        gradient_extractor.SetIndex(iter_gradients)
        gradient = gradient_extractor.Execute(extracted_slice)
        
        gradient_array = sitk.GetArrayFromImage(gradient)
        gradient_array_normalized = (gradient_array - numpy.min(gradient_array)) * round(255 / numpy.max(gradient_array), 3)
        gradient_image = Image.fromarray(gradient_array_normalized)
        gradient_image = gradient_image.convert("L")
        dimension = max(gradient_image.height, gradient_image.width)
        square_image = Image.new('L', (dimension, dimension), 0)
        square_image.paste(gradient_image, ((dimension-gradient_image.width)//2, (dimension-gradient_image.height)//2))
        return square_image

    def CoronalView(self, iter_gradients, input_size, input_image):
        
        slice_extractor = sitk.ExtractImageFilter()  
        slice_extractor.SetSize([input_size[0], 0, input_size[2]])
        slice_extractor.SetIndex([0, input_size[1]//2, 0])
        extracted_slice = slice_extractor.Execute(input_image)

        gradient_extractor = sitk.VectorIndexSelectionCastImageFilter()
        gradient_extractor.SetIndex(iter_gradients)
        gradient = gradient_extractor.Execute(extracted_slice)
        
        gradient_array = sitk.GetArrayFromImage(gradient)
        gradient_array_normalized = (gradient_array - numpy.min(gradient_array)) * round(255 / numpy.max(gradient_array), 3)
        gradient_image = Image.fromarray(gradient_array_normalized)
        gradient_image = gradient_image.convert("L")
        dimension = max(gradient_image.height, gradient_image.width)
        square_image = Image.new('L', (dimension, dimension), 0)
        square_image.paste(gradient_image, ((dimension-gradient_image.width)//2, (dimension-gradient_image.height)//2))
        return square_image
