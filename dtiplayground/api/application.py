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
import multiprocessing as mp
mp.set_start_method("fork")
from dtiplayground.config import INFO 
import dtiplayground.dmri.common.dwi as dwi
import cv2
import io
import numpy as np 

class ApplicationAPI:
    def __init__(self,server,**kwargs):
        self.server = server
        self.app=self.server.app
        self.filecache={}
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

        @self.app.route('/api/v1/app',methods=['GET'])
        def _getUserInfo():
            sc=200
            res=None
            request_id=utils.get_request_id()
            try:
                res= self.getAppInfo()
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

        @self.app.route('/api/v1/file-url',methods=['GET'])
        def _getFileUrl():
            sc=200
            res=None
            param_path=request.args.get('path',type=str)
            request_id=utils.get_request_id()
            try:
                url = request.url
                url = url.replace('/api/v1/file-url','/api/v1/download')
                res= { 'download_url' : url }
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp

        @self.app.route('/api/v1/download',methods=['GET'])
        def _getDownload():
            print(request.url)
            sc=200
            res={}
            param_path=request.args.get('path',type=str)
            request_id=utils.get_request_id()
            try:
                path=Path(param_path)
                filename = path.name
                destDir = path.parent
                if path.exists():
                    return send_from_directory(str(destDir), filename, as_attachment=True)
                else:
                    raise Exception("There is no such file")
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)

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

        @self.app.route('/api/v1/files/get-text-whole',methods=['GET'])
        def _getFileWholeContent():
            sc=200
            res=None
            param_path=request.args.get('path',default='/',type=str)
            request_id=utils.get_request_id()
            try:
                res= self.getTextFileContentAsWhole(param_path)
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

        ###### DWI image
        @self.app.route('/api/v1/files/load',methods=['GET'])
        def _loadFileAsCache():
            sc=200
            res=None
            request_id=utils.get_request_id()
            param_path=request.args.get('filename',default=None,type=str)
            param_key=request.args.get('key', default='image', type=str)
            if param_path is None: raise Exception('No file selected')
            try:
                fn = Path(param_path).resolve()
                res= self.loadFileAsCache(fn, param_key)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp        

        ####### Image browsing (DWI)
        @self.app.route('/api/v1/dwi/<img_id>/<grad_idx>/<axis_idx>/<slice_idx>',methods=['GET'])
        def _getFrameFromDWI(img_id,grad_idx,axis_idx,slice_idx): ## img_id is not used, just to prevent browser cacheing
            res=None
            sc=500 
            data=None
            grad_idx=int(grad_idx)
            axis_idx=int(axis_idx)
            slice_idx=int(slice_idx)
            param_min = request.args.get('min',default=0,type=int)
            param_max = request.args.get('max',default=10e6,type=int)
            try:
                # if axis_idx == 0:
                #     res = self.filecache['dwi'].images[int(slice_idx),:,:,int(grad_idx)]
                # elif axis_idx == 1:
                #     res = self.filecache['dwi'].images[:,int(slice_idx),:,int(grad_idx)]
                # elif axis_idx == 2:
                #     res = self.filecache['dwi'].images[:,:,int(slice_idx),int(grad_idx)]
                # else: raise Exception('No such axis')

                # out = (res >= param_min) * res
                # out[out >= param_max] = param_max
                out = self.filecache['dwi'].getImageSlice4D(axis_idx,slice_idx,grad_idx,normalized=True, display_range=[param_min, param_max])
                ok,res=cv2.imencode('.jpeg',out, [int(cv2.IMWRITE_JPEG_QUALITY), 50]) ### compress 
                if ok:                       
                    data=io.BytesIO(res).read() 
                else:
                    raise Exception("Failed to encode")
                sc=200
            except Exception as e:
                msg=traceback.format_exc()
                err_msg="{}:{}".format(str(e),msg)
                print(str(e))
                print(msg)
            finally:
                resp=Response(data,status=sc)
                resp.headers['Content-Type']='application/octet-stream'
                resp.headers['Image-Format']='jpeg'
                return resp

        ####### Multiprocessing

        @self.app.route('/api/v1/process', methods=['GET'])
        def _get_processes():
            sc=200
            res=None
            request_id=utils.get_request_id()
            try:
                res= self.getProcesses()
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp

        @self.app.route('/api/v1/process/<pid>', methods=['DELETE'])
        def _kill_processes(pid):
            sc=200
            res=None
            request_id=utils.get_request_id()
            try:
                res= self.killProcess(pid)
                res= utils.add_request_id(res)
            except Exception as e:
                sc=500
                exc=traceback.format_exc()
                res=utils.error_message("{}\n{}".format(str(e),exc),500,request_id)
            finally:
                resp=Response(json.dumps(res),status=sc)
                resp.headers['Content-Type']='application/json'
                return resp

    def loadFileAsCache(self, filename, filekey):
        meta={}
        if filekey.lower() == 'dwi':
            #load DWI and put it in cache 
            self.filecache[filekey] = dwi.DWI(str(filename))
            meta = {
                'info': self.filecache[filekey].information,
                'gradients': self.filecache[filekey].getGradients()
            }
            del meta['info']['thicknesses']

        out = {
            'filename': str(filename),
            'type': filekey,
            'meta': meta,
        }
        return out

    #### image browsing

    #### Process

    def getProcesses(self):
        res = mp.active_children()
        res = list(map(lambda x: {'pid': x.pid, 'name' : x.name }, res))

        return res

    def killProcess(self, _id): # id can bd pid or execution id
        allprocs = mp.active_children()
        tokill = filter(lambda x: str(x.pid) == _id or x.name == _id,allprocs)
        for p in tokill:
            p.kill()

        res = list(map(lambda x: {'pid': x.pid, 'name' : x.name }, tokill))
        return res

    #### Filesystem DMRIPlayground
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

    def getAppInfo(self):
        import socket
        res = {
            'version' : INFO['dtiplayground']['version'],
            'home_dir': Path.home().__str__(),
            'config_dir' : str(self.server.config_dir),
            'hostname': socket.gethostname()
        }
        return res
