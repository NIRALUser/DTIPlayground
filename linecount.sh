#!/bin/bash

flist=$(find ./dtiprep -regex '.*\.[py][ym]l*' -print);cat $flist | wc -l


