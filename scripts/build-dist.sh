#!/bin/bash

parent_dir=$(dirname "$0")/..

cd "$parent_dir"

rm -rf "$parent_dir"/dist/*

python setup.py sdist
