#
#   common/fibers.py
#
#   Fiber bundle processing for fiber profiles. Python replacement of the parts of the NIRAL C++ tools
#   fiberprocess (DTIProcessToolkit), FiberPostProcess and dtitractstat (DTIFiberTractStatistics)
#   that are used to extract fiber profiles, with their known bugs fixed:
#     - scalar values stay attached to their fibers when fibers are removed (dtitractstat misaligned them)
#     - arc length starts at the signed distance to the plane (dtitractstat used a cosine)
#     - the closest point used for the plane normal is the true closest point (dtitractstat truncated to int)
#     - a fiber point lying exactly on the plane counts as a crossing (dtitractstat crashed with 'median')
#     - NaN fibers are fibers with NaN scalar values (FiberPostProcess checked tensor eigenvalues)
#     - removing fibers keeps all point data (FiberPostProcess dropped the sampled scalar)
#     - interpolation is clamped to the image on both sides (fiberprocess read outside the image buffer)
#
#   Fiber files store world coordinates in RAS, images are handled in LPS (ITK convention).
#

import math
from pathlib import Path

import numpy as np
import SimpleITK as sitk
import vtk
from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk

import dtiplayground.dmri.common as common

logger = common.logger.write


class FiberBundle:
    """Fibers stored as one point array (N x 3, RAS) with per fiber offsets and per point data arrays."""

    def __init__(self, points, offsets, point_data=None):
        self.points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        self.offsets = np.asarray(offsets, dtype=np.int64)  # fiber i = points[offsets[i]:offsets[i+1]]
        self.point_data = {} if point_data is None else dict(point_data)

    @property
    def number_of_fibers(self):
        return len(self.offsets) - 1

    @property
    def number_of_points(self):
        return len(self.points)

    def fiber_slice(self, i):
        return slice(self.offsets[i], self.offsets[i + 1])

    def fiber_ids(self):
        """Fiber index of every point."""
        return np.repeat(np.arange(self.number_of_fibers), np.diff(self.offsets))

    def select(self, keep):
        """New bundle with the fibers where keep is True; every point data array is filtered with the points."""
        keep = np.asarray(keep, dtype=bool)
        point_keep = np.repeat(keep, np.diff(self.offsets))
        lengths = np.diff(self.offsets)[keep]
        offsets = np.concatenate([[0], np.cumsum(lengths)])
        point_data = {name: values[point_keep] for name, values in self.point_data.items()}
        return FiberBundle(self.points[point_keep], offsets, point_data)


### I/O

def read_fibers(filename):
    filename = str(filename)
    if filename.endswith('.vtp'):
        reader = vtk.vtkXMLPolyDataReader()
    elif filename.endswith('.vtk'):
        reader = vtk.vtkPolyDataReader()
        reader.ReadAllScalarsOn()
        reader.ReadAllVectorsOn()
        reader.ReadAllTensorsOn()
        reader.ReadAllFieldsOn()
    else:
        raise Exception("Unsupported fiber file format (only .vtk and .vtp) : {}".format(filename))
    if not Path(filename).exists():
        raise Exception("Fiber file not found : {}".format(filename))
    reader.SetFileName(filename)
    reader.Update()
    poly = reader.GetOutput()
    lines = poly.GetLines()
    if poly.GetPoints() is None or lines is None or lines.GetNumberOfCells() == 0:
        raise Exception("No fibers in fiber file : {}".format(filename))

    connectivity = vtk_to_numpy(lines.GetConnectivityArray()).astype(np.int64)
    offsets = vtk_to_numpy(lines.GetOffsetsArray()).astype(np.int64)
    points = vtk_to_numpy(poly.GetPoints().GetData()).astype(np.float64)[connectivity]

    point_data = {}
    pd = poly.GetPointData()
    for i in range(pd.GetNumberOfArrays()):
        array = pd.GetArray(i)
        if array is None or array.GetName() is None:
            continue
        point_data[array.GetName()] = vtk_to_numpy(array)[connectivity]
    return FiberBundle(points, offsets, point_data)


def write_fibers(bundle, filename, binary=True):
    """Write fibers as polylines; 'tensors' (9 components) is written as the tensor attribute, other arrays as point data."""
    filename = str(filename)
    poly = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(bundle.points, dtype=np.float32), deep=True))
    poly.SetPoints(points)

    cells = vtk.vtkCellArray()
    cells.SetData(numpy_to_vtk(np.ascontiguousarray(bundle.offsets, dtype=np.int64), deep=True, array_type=vtk.VTK_ID_TYPE),
                  numpy_to_vtk(np.arange(bundle.number_of_points, dtype=np.int64), deep=True, array_type=vtk.VTK_ID_TYPE))
    poly.SetLines(cells)

    for name, values in bundle.point_data.items():
        values = np.asarray(values)
        if values.dtype == np.float64:
            values = values.astype(np.float32)
        array = numpy_to_vtk(np.ascontiguousarray(values), deep=True)
        array.SetName(name)
        if name == 'tensors' and values.ndim == 2 and values.shape[1] == 9:
            poly.GetPointData().SetTensors(array)
        else:
            poly.GetPointData().AddArray(array)

    if filename.endswith('.vtp'):
        writer = vtk.vtkXMLPolyDataWriter()
        if binary:
            writer.SetDataModeToBinary()
    elif filename.endswith('.vtk'):
        writer = vtk.vtkPolyDataWriter()
        if hasattr(writer, 'SetFileVersion'):
            writer.SetFileVersion(42)  ## readable by the older VTK in the NIRAL C++ tools
        if binary:
            writer.SetFileTypeToBinary()
    else:
        raise Exception("Unsupported fiber file format (only .vtk and .vtp) : {}".format(filename))
    writer.SetFileName(filename)
    writer.SetInputData(poly)
    if writer.Write() != 1:
        raise Exception("Couldn't write fiber file : {}".format(filename))


### Images

class Image:
    """Image in ITK physical space (LPS) with voxel array indexed [x, y, z(, component)]."""

    def __init__(self, filename):
        self.filename = str(filename)
        image = sitk.ReadImage(self.filename)
        n_components = image.GetNumberOfComponentsPerPixel()
        image = sitk.Cast(image, sitk.sitkVectorFloat64 if n_components > 1 else sitk.sitkFloat64)
        array = sitk.GetArrayFromImage(image)  # z, y, x(, c)
        self.array = np.ascontiguousarray(np.moveaxis(array, [0, 1, 2], [2, 1, 0]))
        self.size = np.array(image.GetSize(), dtype=np.int64)
        self.origin = np.array(image.GetOrigin(), dtype=np.float64)
        index_to_physical = np.array(image.GetDirection(), dtype=np.float64).reshape(3, 3) @ np.diag(image.GetSpacing())
        self.physical_to_index = np.linalg.inv(index_to_physical)

    def continuous_index(self, lps_points):
        return (lps_points - self.origin) @ self.physical_to_index.T

    def interpolate(self, lps_points):
        """Trilinear interpolation, points outside the image take the value at the image edge."""
        ci = self.continuous_index(lps_points)
        ci = np.clip(ci, 0, self.size - 1)
        base = np.minimum(np.floor(ci).astype(np.int64), self.size - 1)
        frac = ci - base
        upper = np.minimum(base + 1, self.size - 1)
        a = self.array

        def lerp(v0, v1, t):
            if v0.ndim > 1:
                t = t[:, None]
            return np.where(t > 0, v0 + (v1 - v0) * t, v0)  ## a neighbour with weight 0 is not used (keeps NaN local)

        bx, by, bz = base.T
        ux, uy, uz = upper.T
        fx, fy, fz = frac.T
        c00 = lerp(a[bx, by, bz], a[ux, by, bz], fx)
        c10 = lerp(a[bx, uy, bz], a[ux, uy, bz], fx)
        c01 = lerp(a[bx, by, uz], a[ux, by, uz], fx)
        c11 = lerp(a[bx, uy, uz], a[ux, uy, uz], fx)
        return lerp(lerp(c00, c10, fy), lerp(c01, c11, fy), fz)

    def nearest(self, lps_points, outside_value=0.0):
        ci = self.continuous_index(lps_points)
        index = np.floor(ci + 0.5).astype(np.int64)
        inside = np.all((index >= 0) & (index < self.size), axis=1)
        values = np.full(len(lps_points), outside_value, dtype=np.float64)
        ix, iy, iz = index[inside].T
        values[inside] = self.array[ix, iy, iz]
        return values, inside


def ras_to_lps(points):
    return points * np.array([-1.0, -1.0, 1.0])


### Tensor images

_SPACE_TO_LPS = {  # sign flips from the NRRD space to LPS
    'left-posterior-superior': [1, 1, 1], 'LPS': [1, 1, 1],
    'right-anterior-superior': [-1, -1, 1], 'RAS': [-1, -1, 1],
    'left-anterior-superior': [1, -1, 1], 'LAS': [1, -1, 1],
}


class TensorImage(Image):
    """Diffusion tensor NRRD image (kinds 3D-symmetric-matrix, 3D-masked-symmetric-matrix or 3D-matrix).
    array[x, y, z, 6] holds (xx, xy, xz, yy, yz, zz). Tensor values are used as stored (no measurement frame rotation),
    which doesn't change FA, MD, AD or RD."""

    def __init__(self, filename):
        import nrrd
        self.filename = str(filename)
        data, header = nrrd.read(self.filename)
        kinds = [k.lower() for k in header.get('kinds', [])]
        tensor_axis = [i for i, k in enumerate(kinds) if 'matrix' in k]
        if len(tensor_axis) != 1 or data.ndim != 4:
            raise Exception("Not a diffusion tensor NRRD image (expected a 3D-symmetric-matrix / 3D-matrix axis) : {}".format(self.filename))
        kind = kinds[tensor_axis[0]]
        data = np.moveaxis(data, tensor_axis[0], 3).astype(np.float64)
        if kind == '3d-masked-symmetric-matrix':
            data = data[..., 1:7] * (data[..., :1] > 0.5)
        elif kind == '3d-symmetric-matrix':
            data = data[..., :6]
        elif kind == '3d-matrix':
            data = data[..., [0, 1, 2, 4, 5, 8]]
        else:
            raise Exception("Unsupported tensor kind {} : {}".format(kind, self.filename))
        self.array = np.ascontiguousarray(data)
        self.size = np.array(self.array.shape[:3], dtype=np.int64)

        space = header.get('space', 'left-posterior-superior')
        if space not in _SPACE_TO_LPS:
            raise Exception("Unsupported NRRD space {} : {}".format(space, self.filename))
        flip = np.array(_SPACE_TO_LPS[space], dtype=np.float64)
        directions = np.array([d for d in header['space directions'] if d is not None and not np.all(np.isnan(np.asarray(d, dtype=float)))], dtype=np.float64)
        index_to_physical = (directions * flip).T  # columns = physical step per index axis (LPS)
        self.origin = np.asarray(header.get('space origin', np.zeros(3)), dtype=np.float64) * flip
        self.physical_to_index = np.linalg.inv(index_to_physical)
        self._log_array = None
        self._log_valid = None

    def log_tensors(self):
        """Matrix logarithm of every voxel tensor (6 components) and a mask of positive definite tensors."""
        if self._log_array is None:
            tensors = self.array.reshape(-1, 6)
            valid = np.all(np.isfinite(tensors), axis=1)
            log6 = np.zeros_like(tensors)
            eigenvalues, eigenvectors = np.linalg.eigh(tensors_to_matrices(np.where(valid[:, None], tensors, 0.0)))
            valid &= eigenvalues[:, 0] > 0
            log_eigenvalues = np.log(np.where(eigenvalues > 0, eigenvalues, 1.0))
            log6[valid] = matrices_to_tensors((eigenvectors[valid] * log_eigenvalues[valid][:, None, :]) @ np.swapaxes(eigenvectors[valid], 1, 2))
            self._log_array = log6.reshape(self.array.shape)
            self._log_valid = valid.reshape(self.array.shape[:3]).astype(np.float64)
        return self._log_array, self._log_valid


def tensors_to_matrices(t):
    """(N, 6) xx, xy, xz, yy, yz, zz -> (N, 3, 3)"""
    return np.stack([t[:, [0, 1, 2]], t[:, [1, 3, 4]], t[:, [2, 4, 5]]], axis=1)


def matrices_to_tensors(m):
    return np.stack([m[:, 0, 0], m[:, 0, 1], m[:, 0, 2], m[:, 1, 1], m[:, 1, 2], m[:, 2, 2]], axis=1)


def sample_tensors(bundle, tensor_image, displacement_field=None, interpolation='logEuclidean'):
    """Diffusion tensor (6 components) at every fiber point, sampled at x + u(x) like sample_scalar.
    interpolation:
      'linear'       : trilinear interpolation of the tensor components (as fiberprocess -T)
      'logEuclidean' : trilinear interpolation of the matrix logarithms, then matrix exponential (no swelling effect);
                       voxels without a positive definite tensor (e.g. background) are left out and the weights of
                       the other neighbours are renormalized; points without any valid neighbour get NaN"""
    image = tensor_image if isinstance(tensor_image, TensorImage) else TensorImage(tensor_image)
    lookup = _lookup_points(bundle, displacement_field)
    method = interpolation.lower().replace('-', '').replace('_', '')
    if method == 'linear':
        return image.interpolate(lookup)
    if method != 'logeuclidean':
        raise Exception("Unknown tensor interpolation : {} (logEuclidean or linear)".format(interpolation))

    log_array, valid = image.log_tensors()
    ## weighted average of the valid neighbours = interpolate(valid * log) / interpolate(valid)
    weights = Image.__new__(Image)
    weights.size, weights.origin, weights.physical_to_index = image.size, image.origin, image.physical_to_index
    weights.array = valid
    weight = weights.interpolate(lookup)
    weights.array = log_array  # log_array is already 0 where the tensor is not valid
    log_sum = weights.interpolate(lookup)
    tensors = np.full((len(lookup), 6), np.nan)
    ok = weight > 1e-12
    mean_log = tensors_to_matrices(log_sum[ok] / weight[ok][:, None])
    eigenvalues, eigenvectors = np.linalg.eigh(mean_log)
    tensors[ok] = matrices_to_tensors((eigenvectors * np.exp(eigenvalues)[:, None, :]) @ np.swapaxes(eigenvectors, 1, 2))
    return tensors


def tensor_scalars(tensors):
    """FA, MD, AD (largest eigenvalue) and RD (mean of the two smaller eigenvalues) of (N, 6) tensors."""
    tensors = np.asarray(tensors, dtype=np.float64)
    finite = np.all(np.isfinite(tensors), axis=1)
    eigenvalues = np.full((len(tensors), 3), np.nan)
    eigenvalues[finite] = np.linalg.eigvalsh(tensors_to_matrices(tensors[finite]))  # ascending
    md = eigenvalues.mean(axis=1)
    with np.errstate(invalid='ignore', divide='ignore'):
        fa = np.sqrt(1.5) * np.sqrt(np.sum((eigenvalues - md[:, None]) ** 2, axis=1)) / np.sqrt(np.sum(eigenvalues ** 2, axis=1))
    return {'FA': fa, 'MD': md, 'AD': eigenvalues[:, 2], 'RD': (eigenvalues[:, 0] + eigenvalues[:, 1]) / 2.0}


### fiberprocess: sampling scalar images along fibers

def sample_scalar(bundle, scalar_image, displacement_field=None):
    """Scalar value at every fiber point. With a displacement field (LPS, mm, defined on the fiber/atlas space),
    the image is sampled at x + u(x); the fiber geometry itself is not changed (fiberprocess --no_warp)."""
    image = scalar_image if isinstance(scalar_image, Image) else Image(scalar_image)
    return image.interpolate(_lookup_points(bundle, displacement_field))


def _lookup_points(bundle, displacement_field=None):
    """LPS positions where images are sampled: fiber points moved by the displacement field (if any)."""
    lookup = ras_to_lps(bundle.points)
    if displacement_field is not None:
        field = displacement_field if isinstance(displacement_field, Image) else Image(displacement_field)
        if field.array.ndim != 4 or field.array.shape[3] != 3:
            raise Exception("Displacement field must be a 3D vector image : {}".format(field.filename))
        ci = field.continuous_index(lookup)
        inside = np.all((np.floor(ci + 0.5) >= 0) & (ci <= field.size - 0.5), axis=1)
        if not np.all(inside):
            logger("{} fiber points are outside of the displacement field {}, their original position is used"
                   .format(int(np.sum(~inside)), field.filename), common.Color.WARNING)
        lookup = lookup.copy()
        lookup[inside] += field.interpolate(lookup[inside])
    return lookup


def voxelize(bundle, reference_image, output_file, label=1):
    """Label map (unsigned short) on the voxel grid of the reference image: voxels containing a fiber point get the label
    (fiberprocess --voxelize). Only the geometry of the reference image is used, so DWI, DTI or scalar images work."""
    reader = sitk.ImageFileReader()
    reader.SetFileName(str(reference_image))
    reader.ReadImageInformation()
    if reader.GetDimension() < 3:
        raise Exception("Reference image must be 3D : {}".format(reference_image))
    size = np.array(reader.GetSize()[:3], dtype=np.int64)
    spacing = reader.GetSpacing()[:3]
    origin = reader.GetOrigin()[:3]
    direction = np.array(reader.GetDirection(), dtype=np.float64).reshape(reader.GetDimension(), reader.GetDimension())[:3, :3]
    physical_to_index = np.linalg.inv(direction @ np.diag(spacing))

    ci = (ras_to_lps(bundle.points) - np.array(origin)) @ physical_to_index.T
    index = np.rint(ci).astype(np.int64)  ## round half to even, as fiberprocess
    inside = np.all((index >= 0) & (index < size), axis=1)
    if not np.all(inside):
        logger("{} fiber points are outside of the image {} and are ignored".format(int(np.sum(~inside)), reference_image), common.Color.WARNING)
    labels = np.zeros(size[::-1], dtype=np.uint16)  # z, y, x
    ix, iy, iz = index[inside].T
    labels[iz, iy, ix] = label

    image = sitk.GetImageFromArray(labels)
    image.SetSpacing(spacing)
    image.SetOrigin(origin)
    image.SetDirection(direction.flatten().tolist())
    sitk.WriteImage(image, str(output_file), True)
    return labels


### FiberPostProcess: masking and NaN fibers

def fiber_mask_average(bundle, mask_image):
    """Average mask value (nearest voxel) along each fiber; points outside the mask image count as 0."""
    image = mask_image if isinstance(mask_image, Image) else Image(mask_image)
    values, inside = image.nearest(ras_to_lps(bundle.points), outside_value=0.0)
    if not np.all(inside):
        logger("{} fiber points are outside of the mask image {}".format(int(np.sum(~inside)), image.filename), common.Color.WARNING)
    lengths = np.diff(bundle.offsets)
    sums = np.bincount(bundle.fiber_ids(), weights=values, minlength=bundle.number_of_fibers)
    return np.where(lengths > 0, sums / np.maximum(lengths, 1), np.nan)


def fibers_without_nan(bundle, values):
    """True for fibers without NaN values."""
    nan_points = np.isnan(np.asarray(values, dtype=np.float64))
    nan_count = np.bincount(bundle.fiber_ids(), weights=nan_points, minlength=bundle.number_of_fibers)
    return nan_count == 0


### dtitractstat: plane, arc length and profile

def find_plane(bundle, method='cog'):
    """Plane origin (center of gravity or median point of the bundle) and normal (fiber direction near the origin)."""
    method = method.lower()
    fibers = [bundle.points[bundle.fiber_slice(i)] for i in range(bundle.number_of_fibers)]
    fibers = [f for f in fibers if len(f) > 0]
    if len(fibers) == 0:
        raise Exception("Can't compute the plane of an empty fiber bundle")
    if method == 'cog':
        origin = bundle.points.mean(axis=0)
    elif method == 'median':
        median_points = np.array([f[min(int(math.ceil(len(f) / 2.0)), len(f) - 1)] for f in fibers])
        mean_point = median_points.mean(axis=0)
        origin = median_points[np.argmin(np.linalg.norm(median_points - mean_point, axis=1))].copy()
    else:
        raise Exception("Unknown plane of origin : {} (cog or median)".format(method))

    ## closest point to the origin, ignoring the first and last 30% of each fiber (fiber ends of curved bundles)
    best = None
    for f in fibers:
        n = len(f)
        idx = np.arange(n)
        window = (idx + 1 > math.floor(n * 0.3)) & (idx + 1 < math.floor(n * 0.7))
        if not np.any(window):
            continue
        dist = np.linalg.norm(f[window] - origin, axis=1)
        j = int(np.argmin(dist))
        if best is None or dist[j] < best[0]:
            best = (dist[j], f, int(idx[window][j]))
    if best is None:
        raise Exception("Fibers are too short to compute the plane normal")
    _, f, j = best
    normal = f[min(j + 3, len(f) - 1)] - f[max(j - 3, 0)]
    norm = np.linalg.norm(normal)
    if norm == 0:
        raise Exception("Couldn't compute the plane normal")
    return origin, normal / norm


def arc_lengths(bundle, origin, normal):
    """Signed arc length of every fiber point, measured along the fiber from the plane. Points on the side the normal
    points to are positive. Fibers whose end points are on the same side of the plane get NaN (not used)."""
    arcs = np.full(bundle.number_of_points, np.nan)
    signed_distance = (bundle.points - origin) @ normal
    ignored = 0
    for i in range(bundle.number_of_fibers):
        sl = bundle.fiber_slice(i)
        p = bundle.points[sl]
        s = signed_distance[sl]
        if len(p) < 2:
            ignored += 1
            continue
        positive = s >= 0  ## a point on the plane counts as crossing
        if positive[0] == positive[-1]:
            ignored += 1
            continue
        k = int(np.argmax(positive[1:] != positive[:-1])) + 1  ## first point after the first crossing
        direction = 1.0 if positive[-1] else -1.0  ## arc length increases towards the positive side
        segment = np.linalg.norm(np.diff(p, axis=0), axis=1)
        a = np.empty(len(p))
        a[k:] =s[k] + direction * np.concatenate([[0.0], np.cumsum(segment[k:])])
        a[:k] = s[k - 1] - direction * np.concatenate([np.cumsum(segment[:k - 1][::-1])[::-1], [0.0]])
        arcs[sl] = a
    if ignored > 0:
        logger("{} of {} fibers don't cross the plane and are not used".format(ignored, bundle.number_of_fibers), common.Color.WARNING)
    if ignored == bundle.number_of_fibers:
        raise Exception("No fiber crosses the plane")
    return arcs


def profile_grid(arcs, step):
    """Sample positions: multiples of step (0 = plane) covering the arc length range."""
    if step <= 0:
        raise Exception("Step size must be positive : {}".format(step))
    valid = arcs[~np.isnan(arcs)]
    first = int(math.ceil(valid.min() / step - 1e-9))
    last = int(math.floor(valid.max() / step + 1e-9))
    return np.arange(first, last + 1) * step


def gaussian_profile(arcs, values, grid, bandwidth):
    """Gaussian weighted mean (std = bandwidth) of the values within +-bandwidth of each sample position.
    Returns a dict of arrays: arc_length, number_of_points, mean, std (std is the unweighted deviation from the mean,
    as in dtitractstat). Samples without points are NaN."""
    if bandwidth <= 0:
        raise Exception("Bandwidth must be positive : {}".format(bandwidth))
    arcs = np.asarray(arcs, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    used = ~np.isnan(arcs)
    order = np.argsort(arcs[used], kind='stable')
    a = arcs[used][order]
    v = values[used][order]
    count = np.zeros(len(grid), dtype=np.int64)
    mean = np.full(len(grid), np.nan)
    std = np.full(len(grid), np.nan)
    lo = np.searchsorted(a, grid - bandwidth, side='left')
    hi = np.searchsorted(a, grid + bandwidth, side='right')
    for i, s in enumerate(grid):
        window_a = a[lo[i]:hi[i]]
        window_v = v[lo[i]:hi[i]]
        count[i] = len(window_a)
        if count[i] == 0:
            continue
        w = np.exp(-0.5 * ((s - window_a) / bandwidth) ** 2)
        mean[i] = np.sum(w * window_v) / np.sum(w)
        std[i] = math.sqrt(np.mean((window_v - mean[i]) ** 2)) if count[i] > 1 else 0.0
    return {'arc_length': np.asarray(grid, dtype=np.float64), 'number_of_points': count, 'mean': mean, 'std': std}


def write_fvp(filename, profile, parameter_name, step, bandwidth):
    """Profile in the dtitractstat .fvp format (4 header lines, then CSV)."""
    with open(filename, 'w') as f:
        f.write("Noise Model: Gaussian\tStatistics: Mean\n")
        f.write("Arc Length parametrization (Step size): {:g}\tStandard Deviation for kernel window: {:g}\n".format(step, bandwidth))
        f.write("Parameter chosen for regression: {}\t\tWorld space chosen\n".format(parameter_name))
        f.write("Number of samples along the bundle: {}\n".format(len(profile['arc_length'])))
        f.write("Arc_Length,#_fiber_points,Parameter_Value,Std_Dev,Param+Std_Dev,Param-Std_Dev\n")
        for a, n, m, s in zip(profile['arc_length'], profile['number_of_points'], profile['mean'], profile['std']):
            f.write("{:g},{:d},{:g},{:g},{:g},{:g}\n".format(a, int(n), m, s, m + s, m - s))


def write_parameterized_fibers(bundle, arcs, grid, filename):
    """Fibers resampled on the profile grid: each point is the average position of the fiber points closest to one
    sample position, with arrays FiberLocationIndex (index in the grid) and SamplingDistance2Origin (average arc length)."""
    step = grid[1] - grid[0] if len(grid) > 1 else 1.0
    points, offsets, location, distance = [], [0], [], []
    for i in range(bundle.number_of_fibers):
        sl = bundle.fiber_slice(i)
        a = arcs[sl]
        if np.all(np.isnan(a)):
            continue
        p = bundle.points[sl][~np.isnan(a)]
        a = a[~np.isnan(a)]
        index = np.rint((a - grid[0]) / step).astype(np.int64)
        valid = (index >= 0) & (index < len(grid))
        order = np.argsort(index[valid], kind='stable')
        index, p, a = index[valid][order], p[valid][order], a[valid][order]
        bins, start = np.unique(index, return_index=True)
        n = np.diff(np.concatenate([start, [len(index)]]))
        points.append(np.add.reduceat(p, start, axis=0) / n[:, None])
        distance.append(np.add.reduceat(a, start) / n)
        location.append(bins)
        offsets.append(offsets[-1] + len(bins))
    if len(points) == 0:
        raise Exception("No parameterized fibers to write")
    resampled = FiberBundle(np.concatenate(points), offsets,
                            {'FiberLocationIndex': np.concatenate(location).astype(np.int32),
                             'SamplingDistance2Origin': np.concatenate(distance).astype(np.float32)})
    write_fibers(resampled, filename)
