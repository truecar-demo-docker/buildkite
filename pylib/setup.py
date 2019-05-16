from distutils.core import setup
with open('requirements.txt') as f:
    requirements = f.read().splitlines()
setup(name='buildkite',
      version='1.0',
      install_requires=requirements,
      )
