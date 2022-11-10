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

class ApplicationAPI:
    def __init__(self,server,**kwargs):
        self.server = server
        self.app=self.server.app
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
