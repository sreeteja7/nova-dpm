# Copyright 2016 IBM Corp.
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import oslosphinx
import sys

sys.path.insert(0, os.path.abspath('../..'))
sys.path.insert(0, os.path.abspath('../'))
sys.path.insert(0, os.path.abspath('./'))
# -- General configuration ----------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom ones.
extensions = [
    'ext.support_matrix',
    'sphinx.ext.autodoc',
    #'sphinx.ext.intersphinx',
    'sphinxcontrib.seqdiag',
    'oslosphinx',
    'oslo_config.sphinxconfiggen',
    'reno.sphinxext',
]

config_generator_config_file = '../../etc/nova/nova-dpm-config-generator.conf'
sample_config_basename = '_static/nova_dpm'

# autodoc generation is a bit aggressive and a nuisance when doing heavy
# text edit cycles.
# execute "export SPHINX_DEBUG=1" in your terminal to disable

# The suffix of source filenames.
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = u'nova-dpm'
copyright = u'2016, OpenStack Foundation'

# Version information
import nova_dpm.version
# The short X.Y version.
version = nova_dpm.version.version_info.version_string()
# The full version, including alpha/beta/rc tags.
release = nova_dpm.version.version_info.release_string()

# If true, '()' will be appended to :func: etc. cross-reference text.
add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
add_module_names = True

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# -- Options for HTML output --------------------------------------------------

# The theme to use for HTML and HTML Help pages.  Major themes that come with
# Sphinx are currently 'default' and 'sphinxdoc'.
# html_theme_path = ["."]
# html_theme = '_theme'

# Bullets of a toctree are not getting rendered when docs are build
# on RTD. The following 2 lines circumvent that.
# For more details see: https://bugs.launchpad.net/oslosphinx/+bug/1664976
# Once the bug is fixed, those 2 lines can be remove again
html_theme_path = [os.path.join(os.path.dirname(oslosphinx.__file__), 'theme')]
html_theme = 'openstack'

html_static_path = ['_static']

# Output file base name for HTML help builder.
htmlhelp_basename = '%sdoc' % project

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass
# [howto/manual]).
latex_documents = [
    ('index',
     '%s.tex' % project,
     u'%s Documentation' % project,
     u'OpenStack Foundation', 'manual'),
]

# Example configuration for intersphinx: refer to the Python standard library.
#intersphinx_mapping = {'http://docs.python.org/': None}
