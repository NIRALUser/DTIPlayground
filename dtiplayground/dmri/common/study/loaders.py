from pathlib import Path 
import yaml
import json
import re

def load_bids(dirpaths:list):
  studies=[]
  hiddenRegex = re.compile(r'^\..*')
  notHidden = lambda x : hiddenRegex.search(x) is None

  for dr in dirpaths:
    d=Path(dr)
    study={ 'study_id': str(d), 
            'root_dir': str(d),
            'subjects':[]
          }

    subdirs = [ x for x in d.iterdir() if x.is_dir() and notHidden(x.name)]
    for sd in subdirs:
      subject = { 'subject_id': str(sd.relative_to(d)),
                  'sessions':[]
      }
      sesdirs = [ x for x in sd.iterdir() if x.is_dir() and notHidden(x.name)]
      for ssd in sesdirs:
        session = { 
                    'session_id': str(ssd.relative_to(sd)),
                    'modalities': []
        }
        mdirs = [ x for x in ssd.iterdir() if x.is_dir() and notHidden(x.name)]
        for md in mdirs:
          files = [ x for x in md.iterdir() if not x.is_dir() and notHidden(x.name)]
          image_files = list(filter(lambda x: ('.nrrd' in str(x.name)) or ('.nii' in str(x.name)), files))
          meta_files = list(map(lambda x: x.parent.joinpath(x.name.split('.')[0]+'.json'), image_files))
          file_infos = list(zip(image_files,meta_files))
          modality = {
            'modality_type' : str(md.relative_to(ssd)),
            'runs': []
          }
          for fi in file_infos:
            fn,mfn = fi
            if not fn.exists(): continue
            modalityfiles = list(filter(lambda x: mfn.stem in str(x) , files))
            run={
              'run_id': str(fn.relative_to(md)).split('.')[0],
              'files': list(map(lambda x: str(x.name),modalityfiles)),
              'attributes': None
            }
            if mfn.exists():
              run['meta_file']= str(mfn.relative_to(md))
            modality['runs'].append(run)
          session['modalities'].append(modality)
        subject['sessions'].append(session)
      study['subjects'].append(subject)
    studies.append(study)
  return studies 
