import sys
import gc
import datetime,time
import uuid

def object_by_id(id_):
    for obj in gc.get_objects():
        if id(obj) == id_:
            return obj
    raise Exception("No found")

def get_timestamp():
    return str(datetime.datetime.now())
    
def get_uuid():
    return str(uuid.uuid4())

def measure_time(func):  
    def wrapper(*args,**kwargs):
        logger.write("[{}] begins ... ".format(func.__qualname__))
        bt=time.time()
        res=func(*args,**kwargs)
        et=time.time()-bt
        logger.write("[{}] Processed time : {:.2f}s".format(func.__qualname__,et))
        return res 
    return wrapper 

class BiLogger(object):
    def __init__(self,timestamp=False):
        self.terminal=sys.stdout
        self.log_to_file=False
        self.timestamp=timestamp
        
    def setLogfile(self,filename):
        self.file=open(filename,'w')
        self.log_to_file=True
    
    def setTimestamp(self,timestamp=True):
        self.timestamp=timestamp 
        
    def write(self,message,terminal_only=False):
        datestr=get_timestamp()
        if self.timestamp:
            message="[{}]\t{}".format(datestr,message)
        else:
            message="{}".format(message)
        self.terminal.write(message + "\n")
        if self.log_to_file and (not terminal_only):
            self.file.write(message+"\n")
            self.flush()

    def flush(self):
        self.file.flush()
        pass


logger=BiLogger()
_debug=True