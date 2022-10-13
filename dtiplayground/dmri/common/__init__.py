import sys
import gc
import datetime,time
import uuid
from pathlib import Path
import yaml
import stat

class Color:

   ## foreground 

   LIGHTPURPLE = '\033[95m'
   PURPLE = '\033[35m'
   LIGHTCYAN = '\033[96m'
   CYAN = '\033[36m'
   LIGHTBLUE = '\033[94m'
   LIGHTGREEN = '\033[92m'
   GREEN = '\033[32m'
   LIGHTYELLOW = '\033[93m'
   YELLOW = '\033[33m'
   LIGHTRED = '\033[91m'
   RED = '\033[31m'
   BLUE = '\033[34m'
   GREEN = '\033[32m'
   GRAY = '\033[90m'
   BLACK = '\033[30m'

   
   ## background

   BG_LIGHTPURPLE = '\033[105m'
   BG_PURPLE = '\033[45m'
   BG_LIGHTCYAN = '\033[106m'
   BG_CYAN = '\033[46m'
   BG_LIGHTBLUE = '\033[104m'
   BG_LIGHTGREEN = '\033[102m'
   BG_GREEN = '\033[42m'
   BG_LIGHTYELLOW = '\033[103m'
   BG_YELLOW = '\033[43m'
   BG_LIGHTRED = '\033[101m'
   BG_RED = '\033[41m'
   BG_BLUE = '\033[44m'
   BG_GREEN = '\033[42m'
   BG_GRAY = '\033[100m'
   BG_BLACK = '\033[30m'

   ## style

   BOLD = '\033[1m'
   UNDERLINE = '\033[4m'
   END = '\033[0m'

   ## message type

   DEV = GRAY
   OK = GREEN
   SUCCESS = GREEN
   INFO = PURPLE
   PROCESS = BLUE
   WARNING = LIGHTRED
   ERROR = BOLD+RED 


### util functions 
def object_by_id(id_):
    for obj in gc.get_objects():
        if id(obj) == id_:
            return obj
    raise Exception("No found")

def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    
def get_uuid():
    return str(uuid.uuid4())

### decorators
def measure_time(func):  ## decorator
    def wrapper(*args,**kwargs):
        logger.write("[{}] begins ... ".format(func.__qualname__),Color.DEV)
        bt=time.time()
        res=func(*args,**kwargs)
        et=time.time()-bt
        logger.write("[{}] Processed time : {:.2f}s".format(func.__qualname__,et),Color.DEV)
        return res 
    return wrapper 

def is_executable(p):
    if not p.exists(): return False
    if p.is_dir(): return False
    mode = p.stat().st_mode
    if 'x' in stat.filemode(mode): return True
    return False

def isInBin(p):
    return '/bin/' in str(p)

def not_ants(p):
    return 'ANTs' not in str(p)

def get_executables_dpg(root_path):
    r=root_path
    pg = filter(lambda x: not x.is_dir(), Path(r).glob('**/*'))
    pg = filter(lambda x: is_executable(x) and isInBin(x) and not_ants(x) , pg)
    return pg

def get_executables_ants(root_path):
    r=root_path
    pg = filter(lambda x: not x.is_dir(), Path(r).glob('**/*'))
    pg = filter(lambda x: is_executable(x) and isInBin(x) and not not_ants(x) , pg)
    return pg

def get_global_variables():
    home_dir = Path.home()
    config_dir = home_dir.joinpath('.niral-dti')
    global_variable_file = config_dir.joinpath('global_variables.yml')
    return yaml.safe_load(open(global_variable_file,'r'))

def get_default_dpg_executables():
    gvals = get_global_variables()
    root_path = gvals['dtiplayground-tools']['path']
    pg = get_executables_dpg(root_path)
    ## mapping
    res = {}
    for p in pg:
        res[p.name] = str(p)
    return res

def get_default_ants_executables():
    gvals = get_global_variables()
    root_path = gvals['dtiplayground-tools']['path']
    pg = get_executables_ants(root_path)
    ## mapping
    res = {}
    for p in pg:
        res[p.name] = str(p)
    return res

def not_implemented():
    raise Exception("Not Implemented yet")

### classes

class AppState(object): ### software status
  def __init__(self):
    self.state={}

  def updateState(self,state):
    self.state=state 

  def getState(self):
    return self.state 

class FileLogger(object):
    def __init__(self,filename,mode='w'):
        self.setLogfile(filename,mode)

    def setLogfile(self,filename,mode='w'):
        self.filename=filename
        self.file=open(filename,mode)

    def write(self,message):
        self.file.write(message)
        self.file.flush()


class MultiLogger(object):
    def __init__(self,timestamp=True,verbosity=True):
        self.terminal=sys.stdout
        self.log_to_file=False
        self.timestamp=timestamp
        self.verbosity=verbosity 
        self.fileloggers=[]
        self.filename = None
        self.file = None

    def setVerbosity(self,v=True):
        self.verbosity=v 

    def setLogfile(self,filename,mode='a'):
        self.file=open(filename,mode)
        self.filename = filename
        self.log_to_file=True

    def setFilePointer(self, fp):
        if (self.file): self.file.close()
        self.file = fp
        self.log_to_file=True

    def resetLogfile(self):
        if (self.file): self.file.close()
        Path(self.filename).unlink()
        self.setLogfile(self.filename)

    def addLogfile(self,filename,mode='w'):
        self.fileloggers.append(FileLogger(filename,mode))
    
    def setTimestamp(self,timestamp=True):
        self.timestamp=timestamp 
        
    def write(self,message,text_color=Color.END,terminal_only=False):
        datestr=get_timestamp()
        messages=[]
        if message is not None:
          messages=message.split('\n')
        for m in messages:
          if self.timestamp:
              m="[{}]\t{}".format(datestr,m)
          else:
              m="{}".format(m)
          if self.verbosity:
              self.terminal.write(text_color+m + Color.END+"\n")
          if self.log_to_file and (not terminal_only):
              self.file.write(m+"\n")
              self.flush()
          for fl in self.fileloggers:
              fl.write(m+"\n")


    def flush(self):
        self.file.flush()
        pass


logger=MultiLogger()
_debug=True