### MANUAL_Exclude

##### Introduction
MANUAL_Exclude.py will help to exclude weird, false gradients manually from the diffusion images

##### Protocol Parameters

- gradientsToExclude is an object-array, it will exclude all the gradients which are in the list from the image. It's default value is an empty list

The listed indices are the **original** ones: the volumes of the input of the pipeline, in the order they are stored
there. They are not the positions in the image this module receives, which differ as soon as an earlier module
excluded a volume (e.g. SLICE_Check before it). The mapping of each listed index to its position in the current image
is written to the log, with a warning when the two differ and when a listed volume is not in the image any more.


##### Examples


##### Author(s)

