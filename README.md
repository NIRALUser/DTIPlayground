# DTI Playground 

DTI Playground are python based NIRAL pipeline software including DMRIPrep (dmriprep), DTIAtlasBuilder (dmriatlasbuilder), DTIFiberAnalyzer (dmrifiberanalyzer)

### DMRIPrep Usage (dmriprep)

dmriprep is a tool that performs quality control over diffusion weighted images. Quality control is very essential preprocess in DTI research, in which the bad gradients with artifacts are to be excluded or corrected by using various computational methods. The software and library provides a module based package with which users can make his own QC pipeline as well as new pipeline modules.

#### CLI Mode :

1. **init** - Initialize configuration (default: `$HOME/.niral-dti/dmriprep-<version>`)

**init** command generates the configuration directory and files with following command. One just needs to execute this command only once unless a different configuration is needed. If you want to reset the initial configuration directory, you can run init again.
```
    $ dmriprep init 
```
If you want to set different directory other than default one :
```
    $ dmriprep --config-dir my/config/dir init 
```
Once run, `config.yml` and `environment.yml` will be in the directory. 

2. **update** - Update if `config.yml` has been changed (e.g. in case of adding user module directory).
Changing `config.yml` file should be followed by updating `environment.yml` with running update command :
```
    $ dmriprep [--config-dir my/config/dir] update
```
This will update module-specific informations such as binary locations or package location used by the corresponding module. It simply updates `environment.yml`

3. **make-protocols** - Generating a default protocol file

The first thing to do QC is to generate default protocol file that has pipeline information.
```
    $ dmriprep [base options] make-protocols -i IMAGE_FILENAME [-o OUTPUT_FILENAME_] [-d MODULE1 MODULE2 ... ]
```
if `"-o"` option is omitted, the output protocol will be printed on terminal.`"-d"` option specifies the list of modules for the QC, with which command will generate the default pipeline and protocols of the sequence. Same module can be used redundantly. If `"-d"` option is not specified, the default pipeline will be generated from the file `protocol_template.yml` . You can change the default pipeline in `protocol_template.yml` file

4. **run** - Running pipeline 
To run with default protocol generated from `protocol_template.yml`:

```
    $ dmriprep [base options] run -i IMAGE_FILES -o OUTPUT_DIR -d [ MODULE1 MODULE2 ... ]
```
`"-d"` option (default protocol) works as described in **make-protocols** command. But you need to specify `"-d"` for the default pipeline from the template.  If `"-o"` option is omitted, default directory will be set to `Image filename_QC`. IMAGE_FILES may be a list of files to process. In case of susceptibility correction, IMAGE_FILES needs to have counterparts for the polarities. `dmriprep` automatically process qc for all the input images before the susceptibility correction stage.

To run with existing protocol file:
```
    $ dmriprep run -i IMAGE_FILES -p PROTOCOL_FILE -o output/directory/
```

`"-p"` option cannot be used with `"-d"` option.

#### In SLURM cluster with singularity

`dmriprep_slurm` is a wrapper script for dmriprep under singularity container. Usage is same. Users can change slurm resource parameter in the script.
```
    $ dmriprep_slurm <<same options as dmriprep>>
```

### Supported Images

- NRRD 
- NIFTI

### DTIAtlasBuilder Usage (dtiab)

DTIAtlasBuilder is a software to make an atlas from multiple diffusion weighted images. It performs affine/diffeomorphic registrations and finally generates the atlas for all the reference image. 

### DTIFiberAnalyzer Usage (dtifa)

DTIFiberAnalyzer performs statistical computation over the extracted fibers. This enables researchers to get the information of the fiber images easily and fast.

### Developement 

#### Author

- SK Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill

#### References

- [Quality Control of Diffusion Weighted Images - Zhexing Liu, et al](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/)

#### Acknowlegements

DTI Toolkits are funded by National Institute of Health (NIH)

#### LICENSE

MIT

#### Requirements

##### Application required

[GENERAL]
- Python >= 3.8.6
- Singularity (only for dmriprep_singularity)

[DMRIPrep]
- Python Libraries
    - SimpleITK==2.1.1
    - pynrrd==0.4.2
    - dipy==1.4.0 (INTERLACE_Check, BASELINE_Average)
    - pyyaml==5.3.1
    - nibabel==3.2.1
    - tensorflow==2.7.0 (For antspynet)
    - antspynet==0.1.2 (For BRAIN_Mask module)
- External Packages
    - FSL >= 6.0 (Required for the eddy tools which perform eddymotion/suceptibility correction. SUSCEPTIBILITY_Correct, EDDYMOTION_Correct)

[DMRIPrepUI]
- Python Libraries
    - PyQt5==5.9.2

[DTIAtlasbuilder]
- Python Libraries
    - pyyaml==5.3.1
- Binaries
    - DTI-Reg
    - dtiprocess
    - dtiaverage
    - unu
    - ImageMath
    - ResampleDTIlogEuclidean
    - GreedyAtlas
    - BRAINSFit
    - ITKTransformTools

[DTIFiberAnalyzer]
- Python Libraries
    - pyyaml==5.3.1


### Todos

- Server mode - Flask 
- GUI client (Single page web app) - Vuejs, React, ...
- Native GUI client (qt)
- Multi threading

### Change Log

##### 2022-01-26
- dmriprep - Minor bug fix (conversion related)
- dmriprep - Intermediary files can be exported during computation (in module level)

##### 2021-12-10
- dmriprep **New Module** MANUAL_Exclude module added. It is a simple utility module that can exclude gradient volumes from an image with gradient indices from user input via protocols file.

##### 2021-12-08
- dmriprep - **New Module** DTI_Estimate module added with limited capability (only dtiestim is enabled)
- dmriprep - new option --no-output-image, if it's on, there will be no QCed outputfile (only use when there should be no output file. e.g. utilities such as BRAIN_Mask, DTI_Estimate)
- dmriprep - Intermediary files can be saved in output directory with user-specified postfix. e.g. (Module).addOutputFile(sourcefile, postfix). These stored files will be copied into project directory with filename changed with postfix.

##### 2021-11-10
- dmriprep - Singularity setup in slurm cluster
- dmriprep - removed system logging
- dmriprep - Nifti affine matrix orientation problem fixed.

##### 2021-09-02
- dmriprep - Only modules listed in the protocols will be loaded.
- dmriprep - BRAIN_Mask module added (use antspynet, fsl bet), only single file modalities (t2,fa) are available.
- dmriprep - Image orientation between Nrrd and Nifti issue are mostly cleared, however 4d Nifti in Slicer doesn't work properly. Need to look into the issue

##### 2021-08-24
- dmriprep - AntsPyNet library added for brain masking
- dmriprep - BRAIN_Mask module development initiated 

##### 2021-08-12
- dmriprep : change directory name for the merged output to 'combined' from 'consolidated'
- dmriprep : configuration directory will be provided to the protocol and submodules for reading configurations.
- dmriprep : threading issue is addressed. --num-threads will cap the maximum number of threads to be used in the process

##### 2021-07-15

- dmriprep : --num-threads option is added for users to control the resource allocation. 
- dmriprep : FSL wrapping 
- dmriprep : Eddymotion/susceptibility correction implemented with 2 modules (SUSCEPTIBILITY_Correct, EDDYMOTION_Correct)
- dmriprep : Multi image input is implemented for susceptibility correction (if susceptibility correction module is not in the protocol, the input images will be QCed independently)

##### 2021-06-8
- dmriprep : Multi input enabled both for multi processing and multi-input modules (such as susceptibility correction).

##### 2021-05-20
- dtiatlasbuilder : Threading bug fixed.
- dtiatlasbuilder : 1st refactoring is finished. 

##### 2021-05-14
- dtiatlasbuilder : ported to python3, refactoring

##### 2021-04-21
- dmriprep : Baseline average implemented (DirectAverage, BaselineOptimized)
- dmriprep : Optionalized pipeline implemented 
- dmriprep : dmriprep cli implemented
- dmriprep : initial configuration directory management (default $HOME/.niral-dti/dmriprep)
- dmriprep : Minor bug fixed

##### 2021-04-18
- dmriprep : Slicewise check implemented
- dmriprep : Interlace check implemented
- dmriprep : Continuation from stopped point has been implemented , but if image itself is deformed it won't work. It only has ability to track exclusion of gradients yet.
- dmriprep : Colored output is enabled with the logger. (dmriprep.Color.WARNING, dmriprep.Color.OK ... thingks like that look in __init__.py of dmriprep module)

##### 2021-04-15
- dmriprep : Sequential Pipelining implemented

##### 2021-04-09
- dmriprep : New protocol format (YAML)
- dmriprep : New protocol template (YAML)

##### 2021-04-01
- dmriprep : Deveopement initiated
