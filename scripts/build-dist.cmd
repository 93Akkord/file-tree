@echo off

cls

set parent_dir=%~dp0..

cd %parent_dir%

python setup.py sdist
