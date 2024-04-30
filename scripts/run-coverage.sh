#!/bin/bash

original_dir=$(pwd)

parent_dir=$(dirname "$0")/..

cd "$parent_dir"

if [[ "$OSTYPE" == "cygwin" ]]; then
    export PYTHONPATH=$(cygpath -w $(realpath ./src))
else
    export PYTHONPATH=$(realpath ./src)
fi

coverage run -m file_tree.__init__

coverage report -m

coverage html

if [[ "$OSTYPE" == "cygwin" ]]; then
    cygstart "$parent_dir/htmlcov/index.html"
else
    open "$parent_dir/htmlcov/index.html"
fi

cd "$original_dir"
