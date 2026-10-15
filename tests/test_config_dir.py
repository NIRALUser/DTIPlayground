#   Tests of the shared configuration directory (~/.niral-dti) when jobs run at the same time:
#       python -m unittest discover -s tests

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from dtiplayground.dmri import common
import dtiplayground.dmri.preprocessing.modules
from dtiplayground.dmri.preprocessing.app import DMRIPrepApp


class TestGlobalVariables(unittest.TestCase):

    def test_empty_or_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            fn = Path(tmp) / 'global_variables.yml'
            for text in ('', 'fsl:\n', 'fsl: {path: /fsl}\n'):
                fn.write_text(text)
                gvals = common.load_global_variables(fn)
                self.assertIsNone(gvals['dtiplayground-tools']['path'])
                self.assertEqual(gvals['fsl']['path'], '/fsl' if 'path' in text else None)
            self.assertIsNone(common.load_global_variables(Path(tmp) / 'missing.yml')['fsl']['path'])

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            fn = Path(tmp) / 'global_variables.yml'
            common.dump_yaml({'fsl': {'path': '/fsl'}}, fn)
            self.assertEqual(yaml.safe_load(fn.read_text()), {'fsl': {'path': '/fsl'}})
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ['global_variables.yml'])


class TestInitializeDuringAnotherJob(unittest.TestCase):
    """A job that initializes the configuration of a new version while another job rewrites
    global_variables.yml read an empty file (TypeError: 'NoneType' object is not subscriptable)."""

    def test_empty_global_variables_without_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fsl = tmp / 'fsl'
            (fsl / 'etc').mkdir(parents=True)
            (fsl / 'etc' / 'fslversion').write_text('6.0.7\n')
            dpt = tmp / 'dtiplayground-tools'
            dpt.mkdir()
            (dpt / 'info.yml').write_text('name: dtiplayground-tools\n')
            config = tmp / 'niral-dti'
            config.mkdir()
            (config / 'global_variables.yml').write_text('')
            env = {'FSLDIR': str(fsl), 'DTIPLAYGROUNDTOOLS': str(dpt), 'HOME': str(tmp)}
            cwd = os.getcwd()
            try:
                with mock.patch.dict(os.environ, env), mock.patch('sys.stdin', io.StringIO('')):
                    app = DMRIPrepApp(str(config))
                    app.initialize({})
            finally:
                os.chdir(cwd)
            gvals = yaml.safe_load((config / 'global_variables.yml').read_text())
            self.assertEqual(gvals['fsl']['path'], str(fsl))
            self.assertEqual(gvals['dtiplayground-tools']['path'], str(dpt))
            self.assertTrue(Path(app.app['application_dir']).joinpath('init.yml').exists())


if __name__ == '__main__':
    unittest.main()
