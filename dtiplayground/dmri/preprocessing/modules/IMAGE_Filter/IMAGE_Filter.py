import dtiplayground.dmri.preprocessing as prep
import dtiplayground.dmri.common as common
import yaml,os
from pathlib import Path
import dtiplayground.dmri.common.dwi as dwi 
import dtiplayground.dmri.common.tools as tools 

import sys

### Functions of Filter ###


### Function with two parameters : exclude gradients which are not in the range ###

def filter_bmin_bmax (b_min, b_max, image, inside=True):

    ## new code

    exclude_indexes = []
    grads = image.getGradients()
    for idx, g in enumerate(grads):
        if inside:
            if float(g['b_value']) > float(b_max) or float(g['b_value']) < float(b_min):
                exclude_indexes.append(idx)
        else:
            if float(g['b_value']) <= float(b_max) and float(g['b_value']) >= float(b_min):
                exclude_indexes.append(idx)

    return exclude_indexes


    # ## old code
    # liste=[]
    # for i in range (len(image.gradients)):
    #     liste.append(image.gradients[i].get('b_value'))
    #     #print("index : ",image.gradients[i].get('index'))
    #     #print("b_value : ",image.gradients[i].get('b_value'))
    # #image.gradients

    # new_list=[]
    # list2=liste
    # list_to_exclude=[]

    # logger("Filtering",prep.Color.INFO)
    # for j in range (len(image.gradients)):
    #     if image.gradients[j].get('b_value')<=b_min or image.gradients[j].get('b_value')>=b_max:
    #         #image.gradients.pop(j)
    #         #print("to exlcude : ", j)
    #         list2[j]=0
    #         new_list.append(j)
    #     #else :
        
    #         #list_to_exclude.append(j)
    #         #print("inside : ", j)
    # logger("Creating new gradient table",prep.Color.INFO)
    # for i in range(0,len(list2)):
    #     if list2[i]==0:
    #         #print("i : ",i)
    #         #print(image.gradients[i])
    #         image.gradients[i]={}
    #         #print(len(image.gradients))
    #         #image.gradients
    # logger("Image with new gradient table",prep.Color.INFO)
    # image.gradients= [i for i in image.gradients if i!={}]
    # for i in range(0, len(image.gradients)):
    #     #print(i)
    #     image.gradients[i][('index')]=i
    # #image.gradients

    # image.information['sizes'][3]=len(image.gradients)
    # logger("New len of gradient table : {}".format(len(image.gradients)),prep.Color.INFO)
    # #return image

### Function with two parameters : exclude gradients which are between bmin and bmax ###

# def exclude_between_bmin_bmax (b_min, b_max, image):
#     liste=[]
#     for i in range (len(image.gradients)):
#         liste.append(image.gradients[i].get('b_value'))
#         #print("index : ",image.gradients[i].get('index'))
#         #print("b_value : ",image.gradients[i].get('b_value'))
    
#     #image.gradients
    
#     new_list=[]
#     list2=liste
#     list_to_exclude=[]
    

#     logger("Filtering",prep.Color.INFO)
#     for j in range (len(image.gradients)):
#         if image.gradients[j].get('b_value')>=b_min and image.gradients[j].get('b_value')<=b_max:
#             #print("to exlcude : ", j)
#             list2[j]=0
#             new_list.append(j)
#         #else :
        
#             #list_to_exclude.append(j)
#             #print("inside : ", j)

#     logger("Creating new gradient table",prep.Color.INFO)
#     for i in range(0,len(list2)):
#         if list2[i]==0:
#             #print("i : ",i)
#             #print(image.gradients[i])
#             image.gradients[i]={}
#             #print(len(image.gradients))
#             #image.gradients
#     logger("Image with new gradient table",prep.Color.INFO)
#     image.gradients= [i for i in image.gradients if i!={}]
#     for i in range(0, len(image.gradients)):
#         #print(i)
#         image.gradients[i][('index')]=i
#     #image.gradients

#     image.information['sizes'][3]=len(image.gradients)
#     logger("New len of gradient table : {}".format(len(image.gradients)),prep.Color.INFO)
#     #return image

# ### Function with one parameter : exclude gradients which have b_values below this parameter b_min ###

# def filter_bmin(b_min, image):
#     liste=[]
#     for i in range (len(image.gradients)):
#         liste.append(image.gradients[i].get('b_value'))
#     #image.gradients
    
#     new_list=[]
#     list2=liste
#     list_to_exclude=[]
#     logger("Filtering",prep.Color.INFO)
#     for j in range (len(image.gradients)):
#         if image.gradients[j].get('b_value')<=b_min:
#             #print("to exlcude : ", j)
#             list2[j]=0
#             new_list.append(j)
#         #else :
#         #    print("inside : ", j)
#     logger("Creating new gradient table",prep.Color.INFO)      
#     for i in range(0,len(list2)):
#         if list2[i]==0:
#             image.gradients[i]={}
#     logger("Image with new gradient table",prep.Color.INFO)
#     image.gradients= [i for i in image.gradients if i!={}]
#     for i in range(0, len(image.gradients)):
#         image.gradients[i][('index')]=i

#     image.information['sizes'][3]=len(image.gradients)
#     logger("New len of gradient table : {}".format(len(image.gradients)),prep.Color.INFO)
#     #return image


### Function with one parameter : exclude gradients which have b_values above this parameter b_max ###

# def filter_bmax(b_max, image):
#     liste=[]
#     for i in range (len(image.gradients)):
#         liste.append(image.gradients[i].get('b_value'))
#     #image.gradients
    
#     new_list=[]
#     list2=liste
#     list_to_exclude=[]
#     logger("Filtering",prep.Color.INFO)
#     for j in range (len(image.gradients)):
#         if image.gradients[j].get('b_value')>=b_max:
#             #print("to exlcude : ", j)
#             list2[j]=0
#             new_list.append(j)
#         #else :
#         #    print("inside : ", j)
#     logger("Creating new gradient table",prep.Color.INFO)   
#     for i in range(0,len(list2)):
#         if list2[i]==0:
#             image.gradients[i]={}
#     logger("Image with new gradient table",prep.Color.INFO)
#     image.gradients= [i for i in image.gradients if i!={}]
#     for i in range(0, len(image.gradients)):
#         image.gradients[i][('index')]=i

#     image.information['sizes'][3]=len(image.gradients)
#     logger("New len of gradient table : {}".format(len(image.gradients)),prep.Color.INFO)
    #return image


class IMAGE_Filter(prep.modules.DTIPrepModule):
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
        gradient_indexes_to_remove=[]

        logger("Choosing the b-value thresholding mode : ", prep.Color.INFO)
        if self.protocol['b_lower']<self.protocol['b_upper']:
            if self.protocol['tresholding_mode']=='one_treshold_below':
                gradient_indexes_to_remove= filter_bmin_bmax(b_min=0, b_max=self.protocol['b_tresh'], image=self.image, inside=True)
            elif self.protocol['tresholding_mode']=='one_treshold_above':
                gradient_indexes_to_remove= filter_bmin_bmax(b_min=self.protocol['b_tresh'],b_max=10e9, image=self.image, inside=True)
            elif self.protocol['tresholding_mode']=='two_tresholds_within':
                gradient_indexes_to_remove= filter_bmin_bmax(b_min=self.protocol['b_lower'], b_max=self.protocol['b_upper'], image=self.image, inside=True)
            elif self.protocol['tresholding_mode']=='two_tresholds_outside':
                gradient_indexes_to_remove= filter_bmin_bmax(b_min=self.protocol['b_lower'], b_max=self.protocol['b_upper'], image=self.image, inside=False)
        elif self.protocol['b_lower']>self.protocol['b_upper']:
            logger("Error : b_lower must be lower than b_upper or b_upper must be higher than b_lower", prep.Color.ERROR)
            sys.exit()
        elif self.protocol['b_lower']<0:
            logger("Error : b_lower must be positive", prep.Color.ERROR)
            sys.exit()
        elif self.protocol['b_upper']<0:
            logger("Error : b_upper must be positive", prep.Color.ERROR)
            sys.exit()
        elif self.protocol['b_tresh']<0:
            logger("Error : b_tresh must be positive", prep.Color.ERROR)
            sys.exit()
        logger("Treatment done", prep.Color.INFO)

        self.result['output']['excluded_gradients_original_indexes']=self.image.convertToOriginalGradientIndex(gradient_indexes_to_remove)
        self.result['output']['success']=True
        return self.result

