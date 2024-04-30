#!/bin/bash

parent_dir=$(dirname "$0")/..

python "$parent_dir"/src/file_tree/_file_tree.py -r "$parent_dir"
