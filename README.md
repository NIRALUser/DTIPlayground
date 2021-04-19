# DTI Toolkits 

DTI Toolkits are python based NIRAL pipeline software including DTIPrep (dtiprep), DTIAtlasBuilder (dtiab), DTIFiberTract Analyzer (dtifa)

### Usage

CLI Mode :

```
    $ dtiprep image_file -p protocol.yml
```

GUI Mode :
```
    $ dtiprep image_file -p protocol --gui
```

Server Mode:
```
    $ dtiprep --server --port 4000
```


### Supported Images

- NRRD 
- NIFTI

### References

- [Quality Control of Diffusion Weighted Images - Zhexing Liu, et al](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/)

### Requirements

##### Application required

- Python >= 3.6 
- FSL >= 6.0 (Required for the eddy tools which perform eddymotion/suceptibility correction)

##### Python libraries
- pynrrd==0.4.2
- dipy==1.4.0
- pyyaml==5.3.1

### Change Log

##### 2021-04-18
- DTIPrep : Slicewise check implemented
- DTIPrep : Interlace check implemented
- DTIPrep : Continuation from stopped point has been implemented , but if image itself is deformed it won't work. It only has ability to track exclusion of gradients

##### 2021-04-15
- DTIPrep : Sequential Pipelining implemented

##### 2021-04-09
- DTIPrep : New protocol format (YAML)
- DTIPrep : New protocol template (YAML)

##### 2021-04-01
- DTIPrep : Deveopement initiated
