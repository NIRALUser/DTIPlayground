##################################################################################
### Module : utils.py
### Description : Utility functions 
###
###
###
### Written by : scalphunter@gmail.com ,  2021/08/31
### Copyrighted reserved by Sentinel Holdings LC
##################################################################################


import json
from flask import request 

import hmac
import hashlib
import base64
import uuid
import os,traceback
import datetime
import random
import string 
import math

## Exception helper
def check_keys(objToValidate,keys:list):
    for k in keys:
        if k not in objToValidate: raise Exception("Key '{}' is missing".format(k))

## Utilities like loggers 

def get_secret_hash(username,client_id,client_secret):
    msg = username + client_id
    dig = hmac.new(str(client_secret).encode('utf-8'), 
        msg = str(msg).encode('utf-8'), digestmod=hashlib.sha256).digest()
    d2 = base64.b64encode(dig).decode()
    return d2

## json serialize handlers
def datetime_handler(x):
    if isinstance(x, datetime.datetime):
        return x.isoformat()
    raise TypeError("Unknown type")

## public/private
def add_public(doc,public):
    doc['is_public']=public
    return doc
## user id add 
def add_user(doc,user):
    if 'created_by' in doc:
        doc['updated_by']=user.id
        doc['updated_by_name']=user.username
    else:
        doc['created_by']=user.id
        doc['created_by_name']=user.username
        doc['updated_by']=doc['created_by']
        doc['updated_by_name']=user.username
    return doc

## doc status
def set_to_live(doc):
    doc['status']='live'

def set_to_dead(doc):
    doc['status']='dead'
    
## add access_rights
def add_access_rights(doc, user, rights = {}):
    if 'access_rights' not in doc:
        doc['access_rights']=[]
    payload = {
        'user_id': user.id,
        'username': user.username,
        'read': True,
        'write': True,
        'delete': True,
        'admin': True
    }
    payload.update(rights)
    doc['access_rights'].append(payload)
    return doc

def add_access_rights_by_user_id(doc, user_id, username, rights = {}):
    if 'access_rights' not in doc:
        doc['access_rights']=[]
    payload = {
        'user_id': user_id,
        'username': username,
        'read': True,
        'write': True,
        'delete': True,
        'admin': True
    }
    payload.update(rights)
    doc['access_rights'].append(payload)
    return doc
## timestamp
def get_timestamp():
    return datetime.datetime.now().isoformat() 

def add_timestamp(doc):
    if 'created_at' in doc:
        doc['updated_at']=get_timestamp()
    else:
        doc['created_at']=get_timestamp()
        doc['updated_at']=doc['created_at']
    return doc

## uuid

def get_uuid():
    return str(uuid.uuid4())

def add_uuid(doc):
    doc["_id"]=get_uuid()
    return doc

## request id
def get_request_id():
    return "{}_{}".format(get_timestamp(),get_uuid())

def add_request_id(doc,request_id=None):
    if request_id is None : request_id=get_request_id()
    newdoc={}
    newdoc['request_id']=request_id
    newdoc['data']=doc
    return newdoc 
    
# def add_request_id(doc,request_id=None):
#     if request_id is None : request_id=get_request_id()
#     if type(doc) == dict:
#         doc['request_id']=request_id
#         return doc
#     else:
#         newdoc={}
#         newdoc['request_id']=request_id
#         newdoc['data']=doc
#         return newdoc 

## password generator
def generate_password(length=12):
    lower=string.ascii_lowercase
    upper=string.ascii_uppercase
    num=string.digits
    symbols=string.punctuation
    allc=lower+upper+num+symbols
    temp=random.sample(allc,length)
    password="".join(temp)
    return password 

## logger

def get_user_ip():
    headers_list = request.headers.getlist("X-Forwarded-For")
    user_ip = headers_list[0] if headers_list else request.remote_addr
    return user_ip

def log(msg=""):
    username="anonymous"
    try:
        u,g=current_user    
        username=u.username 
    except Exception as e:
        pass

    s="[{} {}] <{}@{}> MSG: {} ".format(request.method,request.path,username,get_user_ip(),msg)
    return s

## dict to attributes

def dict_to_attributes(dict_obj):
    attrs=[]
    for k,v in dict_obj.items():
        attrs.append({
                'Name' : k,
                'Value' : v
            })
    return attrs 

def attributes_to_dict(attr_list):
    return [{x['Name'] : x['Value']} for x in attr_list]

## error message
def result_message(msg,status_code=200,request_id=None):
    if request_id is None: request_id=get_request_id()
    return {"msg":msg,"request_id":request_id,"status_code":status_code}

def error_message(msg,status_code,request_id=None):
    if request_id is None: request_id=get_request_id()
    return {"msg":msg,"request_id":request_id,"status_code":status_code}

