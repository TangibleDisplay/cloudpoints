from setuptools import setup

setup(
    name='cloudpoints',
    author='Gabriel Pettier, Tangible Display',
    url='',
    license='all rights reserved',
    version='1.0',
    description=(
        'visualise LIDAR data'
    ),
    py_modules=['cloudoints'],
    install_requires=[
    ],
    entry_points='''
        [console_scripts]
        cloudpoints=cloudpoints.view:main
    '''
)
