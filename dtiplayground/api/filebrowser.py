##################################################################################
### Module : filebrowser.py
### Description : Remote(Local) File browser 
###
###
###
### Written by : scalphunter@gmail.com ,  2022/10/07
### Copyrights reserved by NIRAL
##################################################################################

import sys, traceback

### API
from flask import request, Response , send_from_directory, jsonify
import json
from . import utils
from pathlib import Path

class FileBrowserAPI:
    def __init__(self,app,**kwargs):
        self.app=app
        self.initEndpoints()

##### Endpoints

    def initEndpoints(self):
        @self.app.route('/api/v1/version',methods=['GET'])
        def _checkAppVersion():
            sc=200
            res=None
            request_id=utils.get_request_id()
            try:
                res= self.checkAppVersion()
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp  

        @self.app.route('/api/v1/files',methods=['GET'])
        def _getFileList():
            sc=200
            res=None
            param_rootdir=request.args.get('root_dir',default='/',type=str)
            request_id=utils.get_request_id()
            try:
                res= self.browseDirectory(param_rootdir)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp

        @self.app.route('/api/v1/files/get-text',methods=['GET'])
        def _getFileTextContent():
            sc=200
            res=None
            param_path=request.args.get('path',default='/',type=str)
            param_last_line=request.args.get('last_line',default=0,type=int)
            request_id=utils.get_request_id()
            try:
                res= self.getTextFileContentAsArray(param_path,param_last_line)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp

        @self.app.route('/api/v1/files/get-readme',methods=['GET'])
        def _getReadMe():
            sc=200
            res=None
            request_id=utils.get_request_id()
            try:
                import dtiplayground
                path = Path(dtiplayground.__file__).resolve().parent.parent.joinpath('README.md');
                res= self.getTextFileContentAsWhole(path)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp

    def checkAppVersion(self):
        return { 'version' : "0.0.1" }

    def browseDirectory(self, rootdir):
        p = Path(rootdir).glob("*")
        parent = Path(rootdir).parent.__str__()
        fixed_paths = [
            {
                'path': parent,
                'is_dir': True,
                'name' : '..',
                'is_real': False
            }
        ]
        paths = ({'path': str(x), 'is_dir': x.is_dir(), "name": x.name, 'is_real': True } for x in p)
        paths = list(paths)
        paths.sort(key=lambda x: (not x['is_dir'], x['name']))
        return fixed_paths + list(paths) 

    def getTextFileContentAsArray(self, path, lastline):
        p = Path(path)
        with open(p,'r') as f:
            content=f.readlines()
        return content[lastline:-1]

    def getTextFileContentAsWhole(self, path):
        p = Path(path)
        with open(p,'r') as f:
            content=f.read()
        return content

