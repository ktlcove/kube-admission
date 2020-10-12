import fastentrypoints

from setuptools import setup, find_packages

version = '0.0.2'

requirements = [
    'starlette',
    'uvicorn',
    'uvloop',
    'async-timeout',
    'ruamel.yaml',
    'jsonpatch',
]

setup(name='kube-admission',
      version=version,
      description="provide by sysadmin",
      long_description="",
      long_description_content_type='text/markdown',
      classifiers=[
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
      ],
      url='https://gitlab.admin.bishijie.com/sysadmin/kube-admission',
      author='koutianlong',
      author_email='koutianlong@bishijie.com',
      packages=find_packages(exclude=('test', 'doc',)),
      include_package_data=True,
      zip_safe=False,
      install_requires=requirements,
      )
