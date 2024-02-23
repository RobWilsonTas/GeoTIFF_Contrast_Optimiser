This script runs in QGIS and takes an input geotiff and several parameters for contrast enhancement of the tif

It effectively functions as a hue-agnostic dynamic unsharp mask filter, but with extra features

It could otherwise be thought of as a way of stretching pixel values, but in a spatially variable way

___________________________________

Be aware before using this script that there are two main places where you need to set the variables (see "User options for the sharpening section")

The script first splits the original tif into tiles

Then for each tile it will determine various attributes of the raster such as local minimum, maximum, range and midrange values, as well as shadow likelihood

With these attributes the algorithm estimates how far it can stretch the values of the pixels to enhance contrast without clipping the values

Then it applies the stretch to the tiles, before putting them all back together

___________________________________

The user parameters like radiusMetres and toneShiftFactor are worth playing around with on a smaller subset of your image to see what the result will look like

This works best for satellite/aerial images that don't have a significant tint, but are fairly low-contrast on a more micro scale

_____________________________________

Any issues let me know
