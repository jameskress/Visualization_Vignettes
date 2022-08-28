#!/bin/bash
#
# KAUST Visualization Vignettes
#
# Author: James Kress, <james.kress@kaust.edu.sa>
# Copyright KAUST
#
if [ $0 == "-h" ]; then
	echo "This script will link all '.png' files in :: "
	echo $(pwd) " to :: " $(pwd)"/movie"
fi

echo "Running script..."
echo "    -Creating 'movie' directory"
mkdir movie

echo "    -Linking '.png' files"

x=1
for i in *.png; do
	counter=$(printf %03d $x)
	ln "$i" movie/img"$counter".png
	x=$(($x+1))
done

echo "    -Generating movie file"
cd movie
rm -rf out.mov
ffmpeg -framerate 10 -i img%03d.png -vcodec qtrle out.mov
echo "Scirpt complete!"

#END ALL
