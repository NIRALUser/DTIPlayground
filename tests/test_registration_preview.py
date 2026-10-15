#   Tests of the preview images of dmrifiberprofile qc-registration:
#       python -m unittest discover -s tests

import tempfile
import unittest
from pathlib import Path

import numpy as np

from dtiplayground.dmri.fiberprofile.analysis import registration_qc as rq


def brain(shape=(40, 48, 30), z=(5, 24)):
    fa = np.zeros(shape, dtype=np.float32)
    x, y = np.mgrid[:shape[0], :shape[1]]
    disk = (x - shape[0] / 2) ** 2 / 15 ** 2 + (y - shape[1] / 2) ** 2 / 18 ** 2 < 1
    fa[disk, z[0]:z[1] + 1] = 0.4
    return fa


class TestPreviewSlices(unittest.TestCase):

    def test_four_equally_spaced_slices_inside_the_brain(self):
        self.assertEqual(rq.preview_slices(brain(z=(5, 24))), [9, 13, 16, 20])
        self.assertEqual(rq.preview_slices(np.zeros((8, 8, 10))), [2, 4, 5, 7])
        self.assertEqual(rq.preview_slices(brain(z=(10, 11))), [10, 11])  # thin slab: no repeated slice

    def test_preview_image(self):
        atlas = brain()
        subj = atlas * 0.9
        maps = {'FA_diff': subj - atlas, 'FA_ssim': np.ones_like(atlas), 'angular_z': np.zeros_like(atlas),
                'FA_z_blobs': (atlas > 0).astype(np.uint8)}
        with tempfile.TemporaryDirectory() as tmp:
            rq.make_preview('sub-01_ses-1', atlas, subj, maps, tmp)
            import matplotlib.image as mpimg
            img = mpimg.imread(str(Path(tmp) / 'previews' / 'sub-01_ses-1_preview.png'))
            self.assertGreater(img.shape[0], img.shape[1] * 0.5)  # 4 rows of 6 panels, no longer one row


if __name__ == '__main__':
    unittest.main()
