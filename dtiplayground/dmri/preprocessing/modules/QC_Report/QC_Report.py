import yaml
from pathlib import Path
import pandas
import os
import fnmatch
import SimpleITK as sitk
import numpy
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfFileMerger

import dtiplayground.dmri.preprocessing as prep

logger=prep.logger.write

class QC_Report(prep.modules.DTIPrepModule):
    def __init__(self,config_dir,*args,**kwargs):
        super().__init__(config_dir)
        
    def generateDefaultProtocol(self,image_obj):
        super().generateDefaultProtocol(image_obj)
        ## todos
        return self.protocol

    def process(self,*args,**kwargs): ## variables : self.config_dir, self.source_image, self.image (output) , self.result_history , self.result (output) , self.protocol, self.template
        super().process()
        inputParams=self.getPreviousResult()['output']
        # << TODOS>>
        data = self.GetData()
        if self.protocol["generateCSV"] == True:
            self.CreateCSV(data)
        if self.protocol["generatePDF"] == True:
            info_display_QCed_gradients = self.CreateImages()
            self.CreatePDF(data, info_display_QCed_gradients)

        self.result['output']['success']=True
        return self.result

    def GetData(self):
        data = []

        # SINGLE INPUT
        if type(self.result_history[0]["output"]) != list:
            input_image = self.result_history[0]["output"]["image_path"]
            image_data = {'input_image': input_image, 'modules':{}}
            total_excluded_gradients = []     
            number_of_modules = (len(self.result_history) - 1)
            for i in range(1, number_of_modules + 1):
                image_data['modules'][self.result_history[i]["module_name"]] =[]
                # get excluded gradients
                if self.result_history[i]["module_name"] in ["SLICE_Check", "INTERLACE_Check", "MANUAL_Exclude", "EDDYMOTION_Correct"]:
                    excluded_gradients = self.result_history[i]["output"]["excluded_gradients_original_indexes"]
                    image_data['modules'][self.result_history[i]["module_name"]] = excluded_gradients
                    total_excluded_gradients += excluded_gradients
                # get rms 
                if self.result_history[i]["module_name"] == "EDDYMOTION_Correct":
                    path_rms = str(Path(self.output_dir).parent.parent) + "/" + self.result_history[i]["output"]["output_directory"] + "/output_eddied.eddy_movement_rms"
                    data_rms = pandas.read_csv(path_rms, sep = '  ', engine = 'python', usecols = [1])
                    rmsLargerThan1 = data_rms[data_rms > 1.0].count()[0]
                    rmsLargerThan2 = data_rms[data_rms > 2.0].count()[0]
                    rmsLargerThan3 = data_rms[data_rms > 3.0].count()[0]
                    image_data["rms"] = {"largerThan1": rmsLargerThan1, "largerThan2": rmsLargerThan2, "largerThan3": rmsLargerThan3}
            # get original number of gradients
            for number in self.result_history[0]["output"]["image_information"]["sizes"]:
                if number not in self.result_history[0]["output"]["image_information"]["image_size"]:
                    image_data["original_number_of_gradients"] = number
            image_data["number_of_excluded_gradients"] = len(total_excluded_gradients)
            data.append(image_data)
        

        # MULTI INPUT
        else:
            input_images_directory_list = [] 
            for image in self.result_history[0]["output"]:
                if "input" in image:
                    input_images_directory_list.append(str(Path(image["input"]["output_directory"]).parent))
            for input_image in input_images_directory_list:
                image_directory_path = str(Path(self.output_dir).parent.parent) + "/" + input_image
                list_modules_directory = []
                for element in os.scandir(image_directory_path):
                    if element.is_dir():
                        list_modules_directory.append(element.path)
                list_modules_result = []
                for module_directory in list_modules_directory:
                    list_modules_result.append(yaml.safe_load(open(module_directory + "/result.yml", 'r')))
                image_data = {'input_image': list_modules_result[0]["input"]["image_path"], 'modules':{}}
                total_excluded_gradients = []
                number_of_modules = len(list_modules_directory)
                for module_result in list_modules_result:
                    image_data['modules'][module_result["module_name"]] = []
                    # get excluded gradients
                    if module_result["module_name"] in ["SLICE_Check", "INTERLACE_Check", "MANUAL_Exclude", "EDDYMOTION_Correct"]:
                        excluded_gradients = module_result["output"]["excluded_gradients_original_indexes"]
                        image_data['modules'][module_result["module_name"]] = excluded_gradients
                        total_excluded_gradients += excluded_gradients
                # get original number of gradients
                for number in list_modules_result[0]["input"]["image_information"]["sizes"]:
                    if number not in list_modules_result[0]["input"]["image_information"]["image_size"]:
                        image_data["original_number_of_gradients"] = number
                image_data["number_of_excluded_gradients"] = len(total_excluded_gradients)
                data.append(image_data)

            if len(input_images_directory_list) == 0: #no module before fusionning images
                for input_image in self.result_history[0]["output"]:
                    image_data = {'input_image': input_image["output"]["image_path"], 'modules':{}}
                    image_data["number_of_excluded_gradients"] = 0
                    # get original number of gradients
                    for number in input_image["output"]["image_information"]["sizes"]:
                        if number not in input_image["output"]["image_information"]["image_size"]:
                            image_data["original_number_of_gradients"] = number
                    data.append(image_data)

            input_image = self.result_history[1]["output"]["image_path"]
            image_data = {'input_image': input_image, 'modules':{}}
            total_excluded_gradients = []     
            number_of_modules = len(self.result_history) - 1
            for i in range(1, number_of_modules + 1):
                image_data['modules'][self.result_history[i]["module_name"]] =[]
                # get excluded gradients
                if self.result_history[i]["module_name"] in ["SLICE_Check", "INTERLACE_Check", "MANUAL_Exclude", "EDDYMOTION_Correct"]:
                    excluded_gradients = self.result_history[i]["output"]["excluded_gradients_original_indexes"]
                    image_data['modules'][self.result_history[i]["module_name"]] = excluded_gradients
                    total_excluded_gradients += excluded_gradients
                # get rms 
                if self.result_history[i]["module_name"] == "EDDYMOTION_Correct":
                    path_rms = str(Path(self.output_dir).parent.parent) + "/" + self.result_history[i]["output"]["output_directory"] + "/output_eddied.eddy_movement_rms"
                    data_rms = pandas.read_csv(path_rms, sep = '  ', engine = 'python', usecols = [1])
                    rmsLargerThan1 = data_rms[data_rms > 1.0].count()[0]
                    rmsLargerThan2 = data_rms[data_rms > 2.0].count()[0]
                    rmsLargerThan3 = data_rms[data_rms > 3.0].count()[0]
                    image_data["rms"] = {"largerThan1": rmsLargerThan1, "largerThan2": rmsLargerThan2, "largerThan3": rmsLargerThan3}
            # get original number of gradients
            image_data["original_number_of_gradients"] = 0
            image_data["number_of_excluded_gradients"] = len(total_excluded_gradients)
            for input_image_index in data:
                image_data["original_number_of_gradients"] += input_image_index["original_number_of_gradients"]
                image_data["number_of_excluded_gradients"] += input_image_index["number_of_excluded_gradients"]
            data.append(image_data)
        
        return(data)

    ## CSV

    def CreateCSV(self, data):
        if len(data) == 1:
            columns = ["image_name", 'original_number_of_gradients', 'number_of_excluded_gradients']
            values = [data[0]["input_image"], data[0]["original_number_of_gradients"], data[0]["number_of_excluded_gradients"]]
            if "rms" in data[0]:
                columns += ['rms_larger_than_1', 'rms_larger_than_2', 'rms_larger_than_3']
                values += [data[0]["rms"]["largerThan1"], data[0]["rms"]["largerThan2"], data[0]["rms"]["largerThan3"]]
        if len(data) > 1: #3 images due to susceptibility correction module
            columns = ["image_name_1", 'original_number_of_gradients_1', 'number_of_excluded_gradients_1']
            values = [data[0]["input_image"], data[0]["original_number_of_gradients"], data[0]["number_of_excluded_gradients"]]
            if "rms" in data[0]:
                columns += ['rms_larger_than_1_image1', 'rms_larger_than_2_image1', 'rms_larger_than_3_image1']
                values += [data[0]["rms"]["largerThan1"], data[0]["rms"]["largerThan2"], data[0]["rms"]["largerThan3"]]
            columns += ["image_name_2", 'original_number_of_gradients_2', 'number_of_excluded_gradients_2']
            values += [data[1]["input_image"], data[1]["original_number_of_gradients"], data[1]["number_of_excluded_gradients"]]
            if "rms" in data[1]:
                columns += ['rms_larger_than_1_image2', 'rms_larger_than_2_image2', 'rms_larger_than_3_image2']
                values += [data[1]["rms"]["largerThan1"], data[1]["rms"]["largerThan2"], data[1]["rms"]["largerThan3"]]
            columns += ["image_name_combined", 'original_number_of_gradients_combined', 'number_of_excluded_gradients_combined']
            values += [data[2]["input_image"], data[2]["original_number_of_gradients"], data[2]["number_of_excluded_gradients"]]
            if "rms" in data[2]:
                columns += ['rms_larger_than_1_combined', 'rms_larger_than_2_combined', 'rms_larger_than_3_combined']
                values += [data[2]["rms"]["largerThan1"], data[2]["rms"]["largerThan2"], data[2]["rms"]["largerThan3"]]

        qc_report = pandas.DataFrame([values], columns = columns)
        path_output_directory = Path(self.output_dir).parent.parent
        qc_report.to_csv(str(path_output_directory) + "/qc_report.csv", index=False)

    ## PDF

    def CreatePDF(self, data, info_display_QCed_gradients):
        temp_file = False  
        eddymotion_in_protocol = False
        for image in data:
            for module in image["modules"].keys():
                if module == "EDDYMOTION_Correct":
                    eddymotion_in_protocol = True
        if eddymotion_in_protocol:
            eddy_folder_path = Path(self.output_dir).parent
            for dirname in os.listdir(eddy_folder_path):
                if fnmatch.fnmatch(dirname, "*_EDDYMOTION_Correct"):
                    eddy_report_path = str(eddy_folder_path) + "/" + dirname + "/output_eddied.qc/qc.pdf"
                    eddy_report_path_abs = os.path.abspath(eddy_report_path)
                    print(eddy_report_path_abs)
                    if os.path.isfile(eddy_report_path_abs):
                        temp_file = True
                        print("file exists !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1")


        if temp_file:
            pdf_file = self.output_dir + '/temp_QC_Report.pdf'
        else:
            pdf_file = str(Path(self.output_dir).parent.parent) + '/QC_Report.pdf'

        # sumup
        can = canvas.Canvas(pdf_file, pagesize=letter)
        x, y = 20, 750
        dx, dy = 15, 20
        for image in data:
            text = "Image: " + image["input_image"]
            while len(text) % 90 > 0:
                can.drawString(x, y, text[:90])
                text = text[90:]
                y -=10                
            can.drawString(x, y, text)
            y -= dy
            for module in image["modules"]:
                can.drawString(x+dx, y, module)
                y -= dy
                if module in ["SLICE_Check", "INTERLACE_Check", "MANUAL_Exclude"]:
                    excluded_gradients = image["modules"][module]
                    if len(excluded_gradients) == 0:
                        can.drawString(x+2*dx, y, "0 exluded gradient")
                        y -= dy
                    else:
                        excluded_gradients_text = str(excluded_gradients[0]) 
                        for index in range(1, len(excluded_gradients)):
                            excluded_gradients_text = excluded_gradients_text + ", " + str(excluded_gradients[index])
                        text = str(len(excluded_gradients)) + " excluded gradient(s): " + excluded_gradients_text
                        while len(text) % 90 > 0:
                            can.drawString(x+2*dx, y, text[:90])
                            text = text[90:]
                            y -=10              
                        can.drawString(x+2*dx, y, text)
                        y -= dy
                if module == "EDDYMOTION_Correct":
                    can.drawString(x+2*dx, y, str(image["rms"]["largerThan1"]) + " gradients with RMS movement relative to first volume > 1 mm")
                    y -= dy
                    can.drawString(x+2*dx, y, str(image["rms"]["largerThan2"]) + " gradients with RMS movement relative to first volume > 2 mm")
                    y -= dy
                    can.drawString(x+2*dx, y, str(image["rms"]["largerThan3"]) + " gradients with RMS movement relative to first volume > 3 mm")
                    y -= dy
            can.drawString(x+dx, y, "Total: " + str(image["number_of_excluded_gradients"]) + " gradient(s) excluded out of " + str(image["original_number_of_gradients"]))
            y -= dy
            can.drawString(x+dx, y, str(100 - round(image["number_of_excluded_gradients"]/image["original_number_of_gradients"], 2)*100) + "% of original gradients are preserved")
            y -= 2*dy
        can.showPage()

        # QCed volume gradients
        x, y = 20, 750 
        output_number_gradients = info_display_QCed_gradients[0]
        width = info_display_QCed_gradients[1]
        height = info_display_QCed_gradients[2]
        for dwi in range(output_number_gradients):
            image_path = self.output_dir + "/QC_Report_images/dwi" + str(dwi) + ".jpg"
            if dwi % 2 == 0:
                x = (4*612 - 3*width) // 12
            else:
                x = (8*612 + width) // 12
            can.drawString(x, y, "DWI " + str(dwi))
            if dwi % 2 == 0:
                x = (612 - 2*width) // 3
            else:
                x = (2*612 - width) // 3
            can.drawImage(image_path, x, y-height-dy//8, width = width, height = height)
            if dwi % 2 != 0:
                y = y - height - dy
            if y - height <= 45:
                y = 750
                can.showPage()
            x = 20
        can.save()

        if temp_file:
            self.MergePDF(pdf_file, eddy_report_path) #add figures from output_eddied.qc/qc.pdf (fsl)

    def MergePDF(self, temp_PDF_path, eddy_report_path):
        pdf_merger = PdfFileMerger()
        pdf_merger.append(temp_PDF_path)
        pdf_merger.merge(1, str(eddy_report_path), pages=(2, 3))
        pdf_merger.merge(2, str(eddy_report_path), pages=(4, 5))
        pdf_merger.merge(3, str(eddy_report_path), pages=(5, 6))
        pdf_merger.write(str(Path(self.output_dir).parent.parent) + '/QC_Report.pdf')




    ## Images

    def CreateImages(self):
        
        input_image = sitk.GetImageFromArray(self.source_image.images)
        input_size = list(input_image.GetSize())
        input_number_gradients = list(self.source_image.images.shape)[3]
        
        output_images_directory = self.GetOutputImagesDirectory()
        zoom_factor = self.GetZoom(input_size, input_image)

        for iter_gradients in range(input_number_gradients):  

            axial_image = self.AxialView(zoom_factor, iter_gradients, input_size, input_image)
            sagittal_image = self.SagittalView(zoom_factor, iter_gradients, input_size, input_image)
            coronal_image = self.CoronalView(zoom_factor, iter_gradients, input_size, input_image)

            # concatenate
            width = axial_image.height + sagittal_image.width + coronal_image.height
            height = max(axial_image.width, sagittal_image.height, coronal_image.width)
            dwi_image = Image.new('L', (width, height), 0)
            dwi_image.paste(sagittal_image, (0, 0))
            dwi_image.paste(axial_image, (sagittal_image.width, 0))
            dwi_image.paste(coronal_image, (sagittal_image.width + axial_image.height, 0))
            dwi_image.save(output_images_directory + "/dwi" + str(iter_gradients) + ".jpg")
  
        info_display_QCed_gradients = [input_number_gradients, dwi_image.width, dwi_image.height]
        return info_display_QCed_gradients

    def GetOutputImagesDirectory(self):
        if not os.path.exists(self.output_dir + "/QC_Report_images"):
            os.mkdir(self.output_dir + "/QC_Report_images")
        return str(self.output_dir) + "/QC_Report_images"

    
    def GetZoom(self, input_size, input_image):
        
        axial_image = self.AxialView(1, 0, input_size, input_image)
        sagittal_image = self.SagittalView(1, 0, input_size, input_image)
        coronal_image = self.CoronalView(1, 0, input_size, input_image)
        width = axial_image.height + sagittal_image.width + coronal_image.height
        zoom_factor = round((612 -3*20)/(2*width), 2)
        return zoom_factor


    def AxialView(self, zoom_factor, iter_gradients, input_size, input_image):

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
        gradient_image = gradient_image.rotate(90)
        gradient_image_resized = gradient_image.resize((int(zoom_factor*gradient_image.width), int(zoom_factor*gradient_image.height)))
        return gradient_image_resized

    def SagittalView(self, zoom_factor, iter_gradients, input_size, input_image):
        
        slice_extractor = sitk.ExtractImageFilter()
        slice_extractor.SetSize([0, input_size[1], input_size[2]])
        slice_extractor.SetIndex([input_size[0]//2, 0, 0])
        extracted_slice = slice_extractor.Execute(input_image)

        gradient_extractor = sitk.VectorIndexSelectionCastImageFilter()
        gradient_extractor.SetIndex(iter_gradients)
        gradient = gradient_extractor.Execute(extracted_slice)
        
        gradient_array = sitk.GetArrayFromImage(gradient)
        gradient_array_normalized = (gradient_array - numpy.min(gradient_array)) * round(255 / numpy.max(gradient_array), 3)
        gradient_array_normalized = numpy.flipud(gradient_array_normalized)
        gradient_image = Image.fromarray(gradient_array_normalized)
        gradient_image = gradient_image.convert("L")
        gradient_image = gradient_image.rotate(270)
        gradient_image_resized = gradient_image.resize((int(zoom_factor*gradient_image.width), int(zoom_factor*gradient_image.height)))
        return gradient_image_resized

    def CoronalView(self, zoom_factor, iter_gradients, input_size, input_image):
        
        slice_extractor = sitk.ExtractImageFilter()  
        slice_extractor.SetSize([input_size[0], 0, input_size[2]])
        slice_extractor.SetIndex([0, input_size[1]//2, 0])
        extracted_slice = slice_extractor.Execute(input_image)

        gradient_extractor = sitk.VectorIndexSelectionCastImageFilter()
        gradient_extractor.SetIndex(iter_gradients)
        gradient = gradient_extractor.Execute(extracted_slice)
        
        gradient_array = sitk.GetArrayFromImage(gradient)
        gradient_array_normalized = (gradient_array - numpy.min(gradient_array)) * round(255 / numpy.max(gradient_array), 3)
        gradient_array_normalized = numpy.flipud(gradient_array_normalized)
        gradient_image = Image.fromarray(gradient_array_normalized)
        gradient_image = gradient_image.convert("L")
        gradient_image = gradient_image.rotate(90)
        gradient_image_resized = gradient_image.resize((int(zoom_factor*gradient_image.width), int(zoom_factor*gradient_image.height)))
        return gradient_image_resized