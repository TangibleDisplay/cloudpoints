from setuptools import setup
from Cython.Build import cythonize
from subprocess import check_output


# remove the leading v from the tag
# replace the first '-' with a '.' (so commit id is part of version),
# maybe a bad idea?
# remove the final \n (to avoid it being replaced with a dash

VERSION = check_output(
    ['git', 'describe', '--tags']
).decode('utf-8')[1:].replace('-', '.', 1).strip()


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
