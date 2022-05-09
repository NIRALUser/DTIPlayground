#!/bin/bash

### User provided environment
export DEST_DIR=/NIRAL/tools/bin_linux64  ### Change this accordingly


### Automatic generation
export V="$(cat version.yml | grep dmriprep)"
export DMRIPREP_VER=(${V//:/})
export VERSION=${DMRIPREP_VER[1]}
echo "Installing ${VERSION}"
export SOURCE_DIR=$PWD
export DEST_NAME="dtiplayground-${VERSION}"
export SCRIPT_NAME="dmriprep-${VERSION}"
export SCRIPT_FILE="${DEST_DIR}/${SCRIPT_NAME}"
export DEFAULT_SCRIPTNAME="dmriprep"
export DEFAULT_SCRIPTFILE="${DEST_DIR}/${DEFAULT_SCRIPTNAME}"

echo "Copying files from ${SOURCE_DIR} to ${DEST_DIR}/${DEST_NAME}"
cp -r $SOURCE_DIR $DEST_DIR/$DEST_NAME
if [ $? != 0 ] 
then
  echo "Failed to copy, exiting."
  exit
fi
echo "Generating script file"
echo "#!/bin/bash" > $SCRIPT_FILE
echo "export VERSION=${VERSION}" >> $SCRIPT_FILE
echo "export BASEDIR=${DEST_DIR}" >> $SCRIPT_FILE
echo "export DPDIR=${DEST_DIR}/${DEST_NAME}" >> $SCRIPT_FILE
echo "export DPENV=${DEST_DIR}/dtiplayground-env" >> $SCRIPT_FILE
echo 'source $DPENV/bin/activate' >> $SCRIPT_FILE
echo 'python3 $DPDIR/dmriprep.py "$@"' >> $SCRIPT_FILE
if [ $? != 0 ] 
then
  echo "Failed to generate script file, exiting."
  exit
fi
chmod +x $SCRIPT_FILE
echo "Copying to ${DEFAULT_SCRIPTFILE}"
cp $SCRIPT_FILE $DEFAULT_SCRIPTFILE
if [ $? != 0 ] 
then
  echo "Failed to chmod script file, exiting."
  exit
fi