#!/bin/bash

parent_dir=$(dirname "$0")/..

cd "$parent_dir"

latest=$(ls -t dist | head -n 1)

echo "Uploading to PyPI..."

twine upload dist/* --verbose
