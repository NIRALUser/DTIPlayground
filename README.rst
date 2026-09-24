DTI Playground
==============

DTI Playground is python based NIRAL pipeline software for diffusion MRI: preprocessing and quality
control of diffusion weighted images, fiber profile extraction and analysis, and atlas building. It
ships a web UI (DTIPlaygroundLab) and these command line tools:

DMRIPrep (``dmriprep``)
~~~~~~~~~~~~~~~~~~~~~~~

Preprocessing and quality control of DWIs, as a pipeline of modules: artifact checks, susceptibility
and eddy current correction, denoising and Gibbs ringing removal, brain masking, tensor and
multi-shell estimation, registration to an atlas, and reports. Single scans, or a whole cohort with
the BIDS-App interface or a datasheet.

DMRIFiberProfile (``dmrifiberprofile``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Along-tract profiles of diffusion properties (FA, MD, AD, RD, free water, NODDI, ...), and the tools
that gather, impute and QC them against normative statistics.

DMRIAtlasBuilder (``dmriatlas``)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Builds a DTI atlas from multiple diffusion tensor images, with affine and diffeomorphic
registrations.

``dmriplayground`` holds the shared configuration and installs the external tools
(``install-tools``); ``dmriplaygroundlab`` starts the web UI for all of them.

The change log is in
`CHANGELOG.md <https://github.com/NIRALUser/DTIPlayground/blob/master/CHANGELOG.md>`_.
