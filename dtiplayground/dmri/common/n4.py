#
#   common/n4.py
#
#   N4 bias field correction (Tustison et al., IEEE TMI 2010) of a 3D image with SimpleITK, for the image a brain
#   mask is computed from (an average baseline, a T2w): a smooth intensity inhomogeneity (coil sensitivity) makes the
#   brain darker on one side, which intensity based mask methods (bet, median Otsu) and, to a lesser degree, the
#   networks cut into.
#

import numpy as np


def spacing_of(affine):
    """Voxel sizes (mm) of a NIfTI affine."""
    return tuple(float(s) for s in np.sqrt((np.asarray(affine, dtype=float)[:3, :3] ** 2).sum(axis=0)))


def n4_correct(volume, spacing=(1.0, 1.0, 1.0), shrink_factor=4, iterations=(50, 50, 50, 50), mask=None):
    """N4 bias field correction of a 3D array (x, y, z), voxel sizes *spacing* in mm. The field is estimated on the
    image shrunk by *shrink_factor* (faster; it is smooth) within *mask* (default: an Otsu threshold of the image, so
    that the background noise doesn't take part), then applied to the whole image at full resolution. Returns
    (corrected image, bias field), both of the shape of *volume*; the corrected image is *volume* / field."""
    import SimpleITK as sitk
    data = np.nan_to_num(np.asarray(volume, dtype=np.float32))
    data = np.clip(data, 0, None)
    if not data.any():
        return data, np.ones_like(data)
    image = sitk.GetImageFromArray(np.ascontiguousarray(data.transpose(2, 1, 0)))  # SimpleITK arrays are z, y, x
    image.SetSpacing(tuple(spacing))
    if mask is None:
        mask_image = sitk.OtsuThreshold(image, 0, 1, 200)
    else:
        mask_image = sitk.GetImageFromArray(np.ascontiguousarray((np.asarray(mask) > 0).astype(np.uint8).transpose(2, 1, 0)))
        mask_image.CopyInformation(image)
    shrink = max(1, int(shrink_factor))
    small = sitk.Shrink(image, [shrink] * 3) if shrink > 1 else image
    small_mask = sitk.Shrink(mask_image, [shrink] * 3) if shrink > 1 else mask_image
    n4 = sitk.N4BiasFieldCorrectionImageFilter()
    n4.SetMaximumNumberOfIterations([int(i) for i in iterations])
    n4.Execute(small, small_mask)
    log_field = n4.GetLogBiasFieldAsImage(image)
    field = np.exp(sitk.GetArrayFromImage(log_field).transpose(2, 1, 0)).astype(np.float32)
    return data / field, field
