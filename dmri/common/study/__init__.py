
import yaml
from pathlib import Path
from dmri.common.study import loaders 

class Study(object):
  def __init__(self, studies: list, **kwargs):
    self.studies=[] ## study object that contains studies, subjects, sessions, modaliditys and files for each modality

  def load(self, studyfilepath):
    if not Path(studyfilepath).exists(): raise Exception("There is no such file : {}".format(studyfilepath))
    with open(studyfilepath,'r') as f:
      studies=yaml.safe_load(f)
      assert(self.study_validate(studies), "Study file format has something wrong")
      assert(self.check_files(studies), "Some files don't exist")
      self.studies=studies 

  def study_validate(self, study: list):
    is_valid = True
    for s in study:
      for sub in s['subjects']:
        for ses in sub['sessions']:
          for modality in ses:
            print(modality)
    return is_valid


  def from_dir(self, dirpath, storage_format):
    pass

  def generate_dir(self, out_dirpath, storage_format): ### copy files and generate study structure into storage format
    pass

  def check_files(self, study: list):
    for s in study:
      for sub in s['subjects']:
        for ses in sub['sessions']:
          for modality in ses:
            for fn in modality['files']:
              if not Path(fn).exists():
                modality['files_checked']=False
              else:
                modality['files_checked']=True 
    return study