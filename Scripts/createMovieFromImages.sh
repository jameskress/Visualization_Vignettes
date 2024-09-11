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

cd movie
x=1
for i in ../*.png; do
	counter=$(printf %03d $x)
	ln -s "$i" img"$counter".png
	x=$(($x+1))
done


echo "    -Generating movie file"
rm -rf out.mov
ffmpeg -framerate 10 -i  img%03d.png -c:v libx264 -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -crf 30 -pix_fmt yuv420p -preset slow -vtag avc1 out.mp4
echo "Scirpt complete!"

#END ALL
