import sys


    
class BiLogger(object):
    def __init__(self):
        self.terminal=sys.stdout
        self.log_to_file=False
        
    def setLogfile(self,filename):
        self.file=open(filename,'w')
        self.log_to_file=True
        
    def write(self,message,terminal_only=False):
        self.terminal.write(message + "\n")
        if self.log_to_file and (not terminal_only):
            self.file.write(message+"\n")
            self.flush()

    def flush(self):
        self.file.flush()
        pass


logger=BiLogger()