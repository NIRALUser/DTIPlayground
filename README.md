# DTIPrep V2

DTIPrep is a tool to quality control the diffusion tensor images.

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

### Requirements

- Python3.6 or greater version

### Chenage Log


##### 2021-04-09
- New protocol format (YAML)
- New protocol template (YAML)

##### 2021-04-01
- Deveopement initiated
