#   HD-BET brain extraction (https://github.com/MIC-DKFZ/HD-BET, Apache-2.0), run through its hd-bet command so that its
#   dependencies (nnunetv2, SimpleITK) can live in a separate Python environment.
#
#   Isensee F, Schell M, Pflueger I, et al. Automated brain extraction of multisequence MRI using artificial neural
#   networks. Human Brain Mapping 40(17) (2019), 4952-4964. https://doi.org/10.1002/hbm.24750
#
#   The model weights are downloaded by hd-bet on first use (~/hd-bet_params).

import os
import shutil
import subprocess
import sys
from pathlib import Path

WEIGHTS_URL = 'https://zenodo.org/records/14445620/files/release_v1.5.0.zip'  # hd-bet 2.x (HD_BET/paths.py)


def find_hdbet(path=None):
    """Path of the hd-bet command: *path* (the executable or the bin directory / prefix of its Python environment),
    next to the running Python, or on the PATH; None if not found."""
    candidates = []
    if path:
        p = Path(str(path)).expanduser()
        candidates += [p, p.joinpath('hd-bet'), p.joinpath('bin', 'hd-bet')]
    candidates.append(Path(sys.executable).parent.joinpath('hd-bet'))
    found = shutil.which('hd-bet')
    if found:
        candidates.append(Path(found))
    for c in candidates:
        if c.is_file() and os.access(str(c), os.X_OK):
            return str(c)
    return None


def _interpreter(executable):
    """Python interpreter of the hd-bet console script (from its #! line), None if unknown."""
    try:
        with open(executable, 'rb') as f:
            line = f.readline().decode(errors='ignore').strip()
    except OSError:
        return None
    if not line.startswith('#!'):
        return None
    python = line[2:].strip().split()[0]
    return python if Path(python).is_file() else None


def cuda_available(executable):
    """Whether the torch of the hd-bet environment sees a CUDA device."""
    python = _interpreter(executable)
    if python:
        result = subprocess.run([python, '-c', 'import torch; print(torch.cuda.is_available())'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().endswith('True')
    return shutil.which('nvidia-smi') is not None and \
        subprocess.run(['nvidia-smi', '-L'], capture_output=True).returncode == 0


def run_hdbet(executable, image_path, mask_path, device='auto', tta=True, work_dir=None):
    """Brain mask of the 3D NIfTI *image_path* with hd-bet, written to *mask_path*. Returns (command, device)."""
    if device == 'auto':
        device = 'cuda' if cuda_available(executable) else 'cpu'
    work = Path(work_dir) if work_dir else Path(mask_path).parent.joinpath('hdbet')
    work.mkdir(parents=True, exist_ok=True)
    output = work.joinpath('brain.nii.gz')
    command = [str(executable), '-i', str(image_path), '-o', str(output), '-device', device,
               '--save_bet_mask', '--no_bet_image']
    if not tta:
        command.append('--disable_tta')
    result = subprocess.run(command, capture_output=True, text=True, cwd=str(work))
    produced = work.joinpath('brain_bet.nii.gz')
    if result.returncode != 0 or not produced.exists():
        hint = ''
        if 'zenodo.org' in result.stderr:
            hint = ('\nhd-bet could not download its model weights from Zenodo; retry later, or download {} and unzip '
                    'it into ~/hd-bet_params/release_2.0.0'.format(WEIGHTS_URL))
        raise RuntimeError('hd-bet failed ({}):\n{}{}{}'.format(' '.join(command), result.stdout, result.stderr, hint))
    shutil.move(str(produced), str(mask_path))
    shutil.rmtree(str(work), ignore_errors=True)
    return command, device
