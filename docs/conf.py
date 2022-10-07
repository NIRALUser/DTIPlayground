# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information
import os
import sys
from datetime import datetime
from sphinx import __version__ as sphinxversion
import sphinx_rtd_theme
from pathlib import Path

sys.path.append(Path(__file__).parent.joinpath('ext').__str__())
from github_link import make_linkcode_resolve

project = 'DTIPlayground'
copyright = '2022, Neuro Image Research and Analysis Laboratory, University of North Carolina @ Chapel Hill'
author = 'Neuro Image Research and Analysis Laboratory'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.coverage',
    'sphinx.ext.mathjax',
    'sphinx.ext.linkcode',
    'sphinx_rtd_theme'
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = 'alabaster'
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

linkcode_resolve = make_linkcode_resolve('dtiplayground',
                                         u'https://github.com/niralUser/'
                                         'dtiplayground/blob/{revision}/'
                                         '{package}/{path}#L{lineno}')
def setup(app):
    pass
    app.add_css_file('overrides.css')