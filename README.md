# DTI Playground 

DTI Playground are python based NIRAL pipeline software including DMRIPrep (dmriprep), DTIAtlasBuilder (dmriatlasbuilder), DTIFiberAnalyzer (dmrifiberanalyzer), AutoTract

#### Installation (Mac/Linux/Windows-WSL)

We recommend users to make a virtual environment first using python >= 3.8.6

```
$ python -m venv $HOME/dtiplayground-env
$ source $HOME/dtiplayground-env/bin/activate
(dtiplayground_env) $ pip install dtiplayground
$ dmriprep -v
```

For Windows users, install WSL and linux distribution (tested with ubuntu 20.04, Centos7).
**FSL should be installed and environment variable 'FSL' needs to be set to the corresponding directory before initialization.**

**install-tools** - Install DTIPlayground Tools (docker & docker-compose required if custom build is needed)

**Note** : Build tested only on CentOS7 for now. However, it would work on most of linux systems. You don't need to install this tools everytime you upgrade dtiplayground.
```
$ dmriprep install-tools [-o <output directory>] [--clean-install] [--no-remove] [--nofsl] [--install-only] [--build]
```
Default output directory is `$HOME/.niral-dti/dtiplayground-tools` if output directory option is omitted
- If `--clean-install` option is present, it removes existing software packages and temporary files first.
- If `--no-remove` option is present, it doesn't remove temporary build files after installation
- If `--nofsl` option is present, it will not install FSL.
- If `--install-only` option is present, it will not update software path file of the configuration of the current version.
- If `--build` option is present, it will build DTIPlaygroundTools with docker (docker required)

Once installed, `$HOME/.niral-dti/global_variables.yml` will have information of the tools including root path of the packages, and automatically changes software paths for the current version of dmriprep unless `--install-only` option is present.

**NOTE** Once FSL is installed, some of tools in FSL has hard coded path in the script, which means that once FSL directory is moved or copied to different directory, some of functions will not work (e.g. eddy_quad). You need to re-install FSL in that case. But changing directory of FSL doesn't affect the functions of DTIPlayground so far. 


## DMRIPrep (dmriprep)

dmriprep is a tool that performs quality control over diffusion weighted images. Quality control is very essential preprocess in DTI research, in which the bad gradients with artifacts are to be excluded or corrected by using various computational methods. The software and library provides a module based package with which users can make his own QC pipeline as well as new pipeline modules.


#### GUI Mode (Mac/Linux):

When a user run dmriprep-ui first time, it automatically initialize.
```
$ dmriprep-ui
```

#### CLI Mode (Mac/Linux/Windows-WSL):

For windows users, install WSL2 and linux packages with python >=3.8.6. 

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

You can manually specify the tool directory (which is generated by `install-tools` command) by `--tools-dir` option.
```
    $ dmriprep init --tools-dir <path/to/tool_dir>
```

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
if `-o` option is omitted, the output protocol will be printed on terminal.`-d` option specifies the list of modules for the QC, with which command will generate the default pipeline and protocols of the sequence. Same module can be used redundantly. If `-d` option is not specified, the default pipeline will be generated from the file `protocol_template.yml` . You can change the default pipeline in `protocol_template.yml` file

4. **run** - Run pipeline 
To run with default protocol generated from `protocol_template.yml`:

```
    $ dmriprep [base options] run -i IMAGE_FILES -o OUTPUT_DIR -d [ MODULE1 MODULE2 ... ]
```
`-d` option (default protocol) works as described in **make-protocols** command. But you need to specify `"-d"` for the default pipeline from the template.  If `-o` option is omitted, default directory will be set to `Image filename_QC`. IMAGE_FILES may be a list of files to process. In case of susceptibility correction, IMAGE_FILES needs to have counterparts for the polarities. `dmriprep` automatically process qc for all the input images before the susceptibility correction stage.

To run with existing protocol file:
```
    $ dmriprep run -i IMAGE_FILES -p PROTOCOL_FILE -o output/directory/
```

`-p` option cannot be used with `-d` option.

**[NOTE]** when using 2 image files for SUSCEPTIBILITY_Correct and other multi input modules, order of files can be important. For the SUSCEPTIBILITY_Correct, AP(FH), RL, SI phased file comes first. (e.g. `$ dmriprep -i AP_img.nrrd PA_img.nrrd ...`)

### Development of a new module 

#### Adding a module

Once initialized, users can add their custom module from scratch or existing system/user modules by following command
```
$ dmriprep add-module <module-name> [--base-module <base-module-name>] [--edit]
```
Following command will generate initial skeletal files of module
```
$ dmriprep add-module HELLO_World 
```
Then you can test if the module can be loaded properly with
```
$ dmriprep update
```
You can use your module right in protocol file.

if `-b` , `--base-module` is specified, new model will copy existing code and data from the base module.
e.g.
```
$ dmriprep add-module MYFIRST_Module -b SLICE_Check
```
MYFIRST_Module will have same codes and data (module definition yaml file) from SLICE_Check module with new classname and filenames.

#### Developer

Once module is developed and tested in the user module directory, one can just move that directory in `dtiplayground/dmri/preprocessing/modules` and commit. Make sure the custom module is not existing both in system module directory and user module directory.

#### Removing user module
User module can be removed by
```
$ dmriprep remove-module <module-name>
```
e.g.
```
$ dmriprep remove-module MYFIRST_Module
```

**NOTE** System module cannot be removed by this command. Only user module can be removed.

#### Modules in other directory
You can just copy module directory to `$HOME/.niral-dti/modules/dmriprep` and check with `$ dmriprep update` command. Same applies for removal of user modules.

## DMRIAutoTract (dmriautotract) - *UNDER DEVELOPMENT*

`dmriautotract` is a tool that performs automatic tractography from the diffusion weighted image. 


#### GUI Mode (Mac/Linux):

Currently GUI for dmritract is not available

#### CLI Mode (Mac/Linux/Windows-WSL):

The usage is same as DMRIPrep. Only difference is that DMRITract uses different set of modules.

To run with existing protocol file:
```
    $ dmritautoract run -i IMAGE_FILES -p PROTOCOL_FILE -o output/directory/
```

`-p` option cannot be used with `-d` option.

## DMRIFiberProfile (dmrifiberprofile) - *UNDER DEVELOPMENT*

`dmrifiberprofile` performs statistical computation over the extracted fibers. This enables researchers to get the information of the fiber images easily and fast.

#### GUI Mode (Mac/Linux):

Currently GUI for dmrifiberprofile is not available

#### CLI Mode (Mac/Linux/Windows-WSL):

The usage is same as DMRIPrep. Only difference is that DMRIFiberProfile uses different set of modules.

To run with existing protocol file:
```
    $ dmrifiberprofile run -i IMAGE_FILES -p PROTOCOL_FILE -o output/directory/
```

`-p` option cannot be used with `-d` option.

## DMRIAtlas (dmriatlas) - *UNDER DEVELOPMENT*

DMRIAtlas is a software to make an atlas from multiple diffusion weighted images. It performs affine/diffeomorphic registrations and finally generates the atlas for all the reference image. 




### Supported Images

- NRRD 
- NIFTI


### Developement 

#### Authors

- Sang Kyoon Park -  Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S.
- Johanna Dubos - Neuro Image Research and Analysis Laboratory , University of North Carolina @ Chapel Hill, U.S. / CPE Lyon, France

#### References

- [Quality Control of Diffusion Weighted Images - Zhexing Liu, et al](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3864968/)

#### Acknowlegements

This software has been supported by the following NIH grants: R01HDO55741, U54HDO79124, R01EB021391,
P50HD103573.

#### LICENSE

MIT

#### Requirements

##### Application dependencies

[GENERAL]
- Python >= 3.8.6 and development packages (e.g. python-dev or python-devel)

[POST INSTALLATION (OPTION)] : below tools can be installed using `$ dmriprep install-tools` command
- FSL >= 6.0 
- DTIPlaygroundTools 

[DTIPlayground]
- Python Libraries
    - simpleitk>=2.1.1
    - pynrrd==0.4.2
    - dipy==1.4.0 
    - pyyaml==5.3.1
    - nibabel==3.2.1
    - tensorflow==2.8.0 (For antspynet)
    - antspyx==0.3.2 (This should be installed due to compiling error in more recent versions)
    - antspynet==0.1.8 (For BRAIN_Mask module)
    - pandas==1.4.3
    - reportlab==3.6.6
    - pypdf2==1.26.0
    - markdown==3.3.6
    - xhtml2pdf==0.2.7

[DMRIPrepUI]
- Python Libraries
    - PyQt5==5.9.2


### Todos

- Server mode - Flask 
- Multi node computing with Kubernetes

### Change Log

##### 2022-09-22
- dmriprep - Measurement frame bug fixed (inversion of measurement frame applied)
- dmriprep - BRAIN_Tractography_v2 : partial tractography with reference dti. Registration added

##### 2022-09-13
- dmriprep - v0.4.3b8
- dmriprep - Bug fixed : Affine matrix transposition bug fixed
- dmriprep - Memory usage: redundancy and inefficient memory management has been improved
- dmriprep - Dependency removal: fury is removed from dependency
- dmriprep - DTIPlayground tools installation without compile

##### 2022-08-19
- dmriprep - v0.4.1 Release
- dmriautotract - Initialized
- dmrifiberprofile - Initialized
- dmriatlas - name changed

##### 2022-08-16
- dmriprep - dwi module moved to common namespace (dtiplayground.dmri.common.dwi)

##### 2022-08-12
- dmriprep - add BRAIN_Tractography, DTI_Register and SINGLETRACT_Process in UI

##### 2022-08-11 (0.3.8b4)
- dmriprep - Bug fixed : Conversion between NRRD and NIFTI now includes space direction conversion as well as measurement frame
- dmriprep - Bug fixed : B value rounding issue resolved

##### 2022-08-10 (0.3.8b3)
- dmriprep - **New Module** BRAIN_Tractography module for generating a tractogram of the whole brain using DIPY

##### 2022-07-22
- dmriprep - Remove option to use ANTsPyNet in BRAIN_Mask module

##### 2022-07-08
- dmriprep - update QC_Report, pdf and csv outputs directly in output directory

##### 2022-07-06
- dmriprep - **New Module** DTI_Register module added for DTI registration (for tractography), it uses DTIReg with ANTS
- dmriprep - software path related enhancement, each module can access to software path information more intuitively using self.softwares variable
- dmriprep - yaml.dump replaced by yaml.safe_dump for potential exception handling

##### 2022-06-19
- dmriprep - module commands added. add-module, remove-module
- dmriprep - FSL installation
- dmriprep - global variables in .niral-dti directory storing global information such as FSL/DTIPlaygroundTools paths

##### 2022-06-17
- dmriprep - installation of dtiplayground tools
- dmriprep - software path generation modified for the tools

##### 2022-06-07
- dmriprep - Change EDDYMOTION_Correction parameters

##### 2022-06-03
- dmriprep - Bug fix in UI (Exclude gradients module with manual selection)

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
