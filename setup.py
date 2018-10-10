from setuptools import setup
from Cython.Build import cythonize
from subprocess import check_output
from os.path import exists


# remove the leading v from the tag
# replace the first '-' with a '.' (so commit id is part of version),
# maybe a bad idea?
# remove the final \n (to avoid it being replaced with a dash

if exists('version.txt'):
    with open('version.txt') as fd:
        VERSION = fd.read().strip()[1:].replace('-', '.', 1).split('-')[0]

else:
    try:
        VERSION = check_output(
            ['git', 'describe', '--tags'],
            shell=True
        ).decode('utf-8')[1:].replace('-', '.', 1).strip()
    except Exception:
        VERSION = 'dev'


setup(
    name='cloudpoints',
    author='Gabriel Pettier, Tangible Display',
    url='',
    license='all rights reserved',
    version=VERSION,
    description=(
        'visualise LIDAR data'
    ),
    ext_modules=cythonize(
        [
            'cloudpoints/view.pyx',
            'cloudpoints/object_renderer.pyx'
        ]
    ),
    platforms='any',
    include_package_data=True,
    packages=['cloudpoints'],
    install_requires=[
        'liblas',
    ],
    entry_points='''
        [console_scripts]
        cloudpoints=cloudpoints.view:main
    '''
)
