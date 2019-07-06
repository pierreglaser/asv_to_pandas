from distutils.core import setup

setup(name='asv_to_pandas',
      version='0.1',
      description='asv-to-pandas benchmark results converter',
      author='Pierre Glaser',
      author_email='pierreglaser@msn.com',
      packages=['asv_to_pandas'],
      install_requires=['asv', 'pandas', 'gitpython']
      )
