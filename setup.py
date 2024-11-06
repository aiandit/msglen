#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import re
from setuptools import setup, find_packages


def read_version():
    with open(os.path.join('msglen', '__init__.py')) as f:
        m = re.search(r'''__version__\s*=\s*['"]([^'"]*)['"]''', f.read())
        if m:
            return m.group(1)
        raise ValueError("couldn't find version")

setup(
    name='msglen',
    version=read_version(),
    description='Simple Binary Stream Messages)',
    long_description=readme + '\n\n' + history,
    maintainer='Johannes Willkomm',
    maintainer_email='jwillkomm@ai-and-it.de',
    url='https://github.com/aiandit/msglen',
    project_urls={
        'AI&IT Home': 'https://ai-and-it.de',
        'Project': 'https://github.com/aiandit/msglen',
    },
    packages=find_packages('.'),
    include_package_data=True,
#    package_data={'msglen': ['xsl/xml2json.xsl']},
    install_requires='-r requirements.txt',
    entry_points={
        'console_scripts': [
            # master entry point, includes the following as subcommands
            'msglen=msglen.__main__:run',
        ]
    },
    license="BSD",
    zip_safe=False,
    keywords='msglen',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Topic :: Streaming :: Streaming Msg',
    ],
)
