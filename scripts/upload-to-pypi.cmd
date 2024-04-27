@echo off

cls

set parent_dir=%~dp0..

cd %parent_dir%

for /f "delims=" %%x in ('dir /B /OD dist') do set latest=%%x

echo Uploading to PyPI...

rem twine upload dist/*
rem twine upload dist/%latest% --verbose
twine upload dist/* --verbose

rem echo The latest file is: %latest%
