"""
    Setup file for file-tree.
    Use setup.cfg to configure your project.

    This file was generated with PyScaffold 4.0a3.
    PyScaffold helps you to put up the scaffold of your new Python project.
    Learn more under: https://pyscaffold.org/
"""

from setuptools import setup
import os
import sys

# find_packages doesn't seem to handle stub files
# so we'll enumarate manually
src_path = os.path.join("src")


def list_packages(src_path=src_path):
    for root, _, _ in os.walk(os.path.join(src_path, "file_tree")):
        if '__pycache__' not in root:
            yield ".".join(os.path.relpath(root, src_path).split(os.path.sep))


if __name__ == '__main__':
    setup(name='akkd-file-tree',

          author='Michael Barros',

          author_email='michaelcbarros@gmail.com',

          url='https://github.com/93Akkord/file-tree',

          download_url='https://github.com/93Akkord/file-tree/archive/refs/tags/v0.0.5.tar.gz',
          
          packages=list(list_packages()))
