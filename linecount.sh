#!/bin/bash

flist=$(find ./ -regex '.*\.[py][ym]l*' -print);cat $flist | wc -l


