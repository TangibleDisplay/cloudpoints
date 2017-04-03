from setuptools import setup
from Cython.Build import cythonize
from subprocess import check_output


VERSION = check_output(['git', 'describe', '--tags'])[1:].replace('-', '.')


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
