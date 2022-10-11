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
from xhtml2pdf import pisa

import dtiplayground.dmri.preprocessing as prep

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
        global_report = ""
        if self.protocol["generatePDF"] == True:
            global_report = self.MergeReports(global_report)
            global_report, number_input_gradients, excluded_gradients, number_of_excluded_gradients = self.AddGeneralInfo(global_report)          
            info_display_QCed_gradients = self.CreateImages()
            if number_of_excluded_gradients != 0:
                global_report = self.AddExcludedGradientsImagesToReport(global_report, excluded_gradients)
            global_report = self.AddGradientImagesToReport(global_report, info_display_QCed_gradients[0])
            html_path = self.GenerateReportFiles(global_report)
            with open(html_path, "r", encoding="utf-8") as f:
                html_data = f.read()
            pdf_path = self.output_dir+"/QC_report.pdf"
            result_file = open(pdf_path, "w+b")
            pisa.CreatePDF(html_data, dest=result_file)
            result_file.close()
            self.addOutputFile(pdf_path, "QC_report")

        if self.protocol["generateCSV"] == True:
            if self.protocol['generatePDF'] == False:
                global_report, number_input_gradients, excluded_gradients, number_of_excluded_gradients = self.AddGeneralInfo(global_report)
            self.CreateCSV(number_input_gradients, number_of_excluded_gradients)

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


    def AddExcludedGradientsImagesToReport(self, global_report, excluded_gradients):
        global_report += "\n## Excluded DWIs:\n"
        image_path = self.result_history[1]['report']['csv_data']['image_name']
        if type(excluded_gradients[0]) == int:
            excluded_gradients = [excluded_gradients]
            image_path = [image_path]
        for image_index in range(len(image_path)):
            if len(excluded_gradients[image_index]) != 0:
                images = self.CreateImagesOfExcludedGradients(image_path[image_index], excluded_gradients[image_index])
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
        for gradient_index in range(number_of_gradients):  
            if gradient_index % 2 == 0:
                global_report += "<tr>\n"     
            global_report += "<td><figure><img src="+self.output_dir+"/QC_Report_images/dwi"+str(gradient_index)+".jpg alt='DWI "+str(gradient_index)+"' width='260'><figcaption aligh='center'>DWI "+str(gradient_index)+"</figcaption></figure></td>\n"      
            if gradient_index % 2 != 0:
                global_report += "</tr>\n"
        global_report += "</tbody></table>\n"
            
        #global_report += "![DWI" + str(gradient_index) + "](" + image_path + " 'DWI " + str(gradient_index) + "')"
        return(global_report)

    def CreateCSV(self, number_input_gradients, number_of_excluded_gradients):
        single_input = True
        for module in self.result_history[1:]:
            if module["module_name"] == "SUSCEPTIBILITY_Correct":
                single_input = False

        if single_input:
            columns = ["image_name"]
            values = [self.result_history[1]['report']['module_report_paths']]
        else:
            columns = ["image_name_1", "image_name_2"]
            values = [self.result_history[1]['report']['csv_data']['image_name'][0], self.result_history[1]['report']['csv_data']['image_name'][1]]
        columns += ['original_number_of_gradients', 'number_of_excluded_gradients']
        values += [number_input_gradients, number_of_excluded_gradients]
        for module in self.result_history[1:]:
            if module["module_name"] == "EDDYMOTION_Correct":
                columns += ['rms_larger_than_1', 'rms_larger_than_2', 'rms_larger_than_3']
                values += [module['report']['csv_data']['rms_gt_1'], module['report']['csv_data']['rms_gt_2'], module['report']['csv_data']['rms_gt_3']]

        qc_report = pandas.DataFrame([values], columns = columns)
        path_output_directory = Path(self.output_dir).parent.parent
        csv_path = self.output_dir + "/QC_report.csv"
        qc_report.to_csv(csv_path, index=False)
        self.addOutputFile(csv_path, "QC_report")

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

    def CreateImagesOfExcludedGradients(self, image_path, excluded_gradients):
        input_image = sitk.ReadImage(image_path)
        input_size = list(input_image.GetSize())
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
