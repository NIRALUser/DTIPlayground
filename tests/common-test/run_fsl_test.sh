#!/bin/bash -v

export TMP=/BAND/USERS/skp78-dti/testdata-dtiprep/eddy_test
export COMMAND=eddy_openmp
INPUTFILE=$1
BVALSFILE="${INPUTFILE%%.*}".bvals
BVECSFILE="${INPUTFILE%%.*}".bvecs
ACQPFILE=$TMP/acqp.txt
MASKFILENAME=$TMP/mask.nii.gz
INDEXFILENAME=$TMP/b0index.txt

python3 fsl_test.py $COMMAND --args $INPUTFILE $MASKFILENAME $ACQPFILE $INDEXFILENAME $BVALSFILE $BVECSFILE ./out.nii.gz