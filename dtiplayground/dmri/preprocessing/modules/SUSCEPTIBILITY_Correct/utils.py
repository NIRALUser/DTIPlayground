
import dtiplayground.dmri.preprocessing as prep

import yaml,os
from pathlib import Path 

logger=prep.logger.write

### utilities

def find_fsl(lookup_dirs=[]):
    fsldir=os.environ.get('FSLDIR')
    candidates=[]
    if fsldir is not None:
        fsldir=Path(fsldir)
        candidates.append(fsldir)
    else:
        candidates=[]
        for d in lookup_dirs:
            candidates+=list(Path(d).glob("**/etc/fslversion"))
        
        if len(candidates)==0 : 
            logger("FSL6 NOT found",prep.Color.WARNING)
            return None,None 
        candidates=list(map(lambda x: x.parent.parent, candidates))

    fsl_version=None
    for d in candidates:
        fsldir=d
        versionfile=fsldir.joinpath('etc/fslversion')
        if versionfile.exists():
            with open(versionfile,'r') as f:
                fsl_version=f.readlines()[0]
            bigversion=int(fsl_version.split('.')[0])
            if bigversion>=6:
                return str(fsldir), fsl_version

    return str(fsldir),fsl_version