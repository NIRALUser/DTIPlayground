#!/bin/bash

export ROOT_DIR=/Human/UCIrvine/InterGenTrauma/DTIAtlasAnalysis/DTIAtlas_March26_2021_Rochester_Pitt
export CONFIG=$ROOT_DIR/common/config.json
export HBUILD=$ROOT_DIR/common/h-build.json
export GREEDY=$ROOT_DIR/common/GreedyAtlasParameters.xml

source /BAND/USERS/skp78-dti/dtiplayground-env/bin/activate
python ./test.py --config $CONFIG --hbuild $HBUILD --greedy-params $GREEDY "$@"

