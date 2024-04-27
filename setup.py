from setuptools import setup
import os

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
          
          packages=list(list_packages()))
