# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from setuptools import setup, find_packages

version = '0.8'

# get documentation from the README
try:
    here = os.path.dirname(os.path.abspath(__file__))
    description = file(os.path.join(here, 'README.md')).read()
except (OSError, IOError):
    description = ''

# dependencies
deps = ['datazilla>=1.2',
        'gaiatest==0.12',
        'mozlog==1.3',
        'progressbar==2.3',
        'numpy==1.7.1']

setup(name='b2gperf',
      version=version,
      description="App startup tests for B2G",
      long_description=description,
      classifiers=[],  # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='mozilla',
      author='Mozilla Automation and Testing Team',
      author_email='tools@lists.mozilla.org',
      url='https://github.com/davehunt/b2gperf',
      license='MPL',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      package_data={'b2gperf': ['launchapp.js', 'scrollapp.js']},
      include_package_data=True,
      zip_safe=False,
      entry_points="""
      [console_scripts]
      b2gperf = b2gperf.b2gperf:cli
      """,
      install_requires=deps,
      )
