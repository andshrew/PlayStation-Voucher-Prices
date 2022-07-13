#!/bin/bash

# Install the projects Python dependencies
pip3 --disable-pip-version-check install -r requirements.txt

# Copy the example data files into the projects root if they do not already exist
files=("config.json" "data.json")
for f in ${files[@]}; do
    if [ ! -f $f ]; then
        cp "example/${f}" . && echo "Copied 'example/${f}' into ${PWD}"
    fi
done