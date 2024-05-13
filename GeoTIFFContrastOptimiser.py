import numpy, psutil, os, glob, time, signal
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsRasterLayer
from datetime import datetime
from pathlib import Path
startTime = time.time()


"""
##########################################################
User options for the tiling section
"""

#Initial variable assignment
inImage                 = 'C:/TempYourImage.tif' #E.g 'C:/Temp/BigImage.tif'
approxPixelsPerTile     = 12000 #E.g 12000, this will vary based on your ram

#Options for compressing the images, ZSTD gives the best speed but LZW allows you to view the thumbnail in windows explorer
compressOptions =       'COMPRESS=ZSTD|NUM_THREADS=ALL_CPUS|PREDICTOR=1|ZSTD_LEVEL=1|BIGTIFF=IF_SAFER|TILED=YES'
finalCompressOptions =  'COMPRESS=LZW|PREDICTOR=2|NUM_THREADS=ALL_CPUS|BIGTIFF=IF_SAFER|TILED=YES'
gdalOptions =           '--config GDAL_NUM_THREADS ALL_CPUS -overwrite'


"""
#############################################################
User options for the sharpening section (common values for speedUp and radius: 6SUP & 10RM & 4SBWM for 10cm,   6SUP & 15RM & 10SBWM for 25cm,    2SUP & 80RM & 50SBWM for 10m)
"""


speedUpFactor               = 6 #Between 1 and 1000, recommended is perhaps 6 to start off with  
#This reduces the raster resolution for determining minimum and maximum values
#If the speed up factor is too high, it will overlook smaller bright/dark sections and clip their values
#If the speed up factor is too low, it can be too granular/zealous in preventing pixel value clipping, 
#Plus it can make processing times very long (keep an eye on the console output for this)
#Though as long as it isn't below 5 it likely won't be a real issue on performance

radiusMetres                = 30 #At least 3 times greater than the original pixel size, also must be an integer
#This parameter has a strong effect on the output
#A smaller radius creates more extreme, spatially variable contrast enhancement
#A larger radius is a more gentle, broader brush

toneShiftFactor             = 0.85 #Between 0.1 and 1, recommended is 0.85
#If broader darker areas are getting brightened too much (or vice versa for bright areas), 
#or low contrast areas are having their contrast bumped up too high then you can decrease this value
#Alternatively if you want to really brighten up dark areas you can increase this to 0.95 or even 1

maxPixelChangeFactor        = 0.25 #Between 0.1 and 1, recommended is 0.25
#If harsh edges are appearing where some areas are pushed too far towards black or white,
#then you can decrease this value

clippingPreventionFactor    = 0.05 #Between 0 and 0.9, recommended is 0.05
#If the full stretch of pixels is getting stretched too far into complete blackness/whiteness,
#despite a low speed up factor, then you can increase this value a little

shadowBoostWidthMetres      = 12.0 #Must be larger than approximately 3 times the pixel size times the speed up factor
#This sets a very approximate minimum width of the shadowed areas to be boosted

shadowBoostFactor           = 0.2 #Between 0 and 1, recommended is 0.4


#Keep in mind this script only adjusts brightnesses. A tinted image will affect results.
#If you have an image with a significant coloured tint then it is best to first render out a new version
#that has the 3 bands individually stretched such that the tint is as removed as it can be


"""
#######################################################################
#######################################################################
"""

#Set up the layer name for the raster calculations
inImageName = inImage.split("/")
inImageName = inImageName[-1]
inImageName = inImageName[:len(inImageName)-4]
outImageName = inImageName

#Making a folder for processing
rootProcessDirectory = str(Path(inImage).parent.absolute()).replace('\\','/') + '/'
processDirectoryInstance = rootProcessDirectory + inImageName + 'Process' + '/'

#Creating all the subfolder variables
processDirectory                = processDirectoryInstance + '1Main/'
otherDirectory                  = processDirectoryInstance + '2Other/'
processBoundsDirectory          = processDirectoryInstance + '3TileBounds/'
processTileDirectory            = processDirectoryInstance + '4Tiles/'
outImageDir                     = processDirectoryInstance + '5OutTiles/'
finalImageDir                   = processDirectoryInstance + '6Final/'
inImageTileDir = processTileDirectory

#Creating all the subfolders
if not os.path.exists(processDirectoryInstance):                os.mkdir(processDirectoryInstance) 
if not os.path.exists(processDirectory):                        os.mkdir(processDirectory)
if not os.path.exists(otherDirectory):                          os.mkdir(otherDirectory)
if not os.path.exists(otherDirectory + 'ConfirmationFiles/'):   os.mkdir(otherDirectory + 'ConfirmationFiles/')
if not os.path.exists(processBoundsDirectory):                  os.mkdir(processBoundsDirectory)
if not os.path.exists(processTileDirectory):                    os.mkdir(processTileDirectory)
if not os.path.exists(outImageDir):                             os.mkdir(outImageDir)
if not os.path.exists(finalImageDir):                           os.mkdir(finalImageDir)


#Make a debug text file
debugText = open(otherDirectory + inImageName + "Debug.txt","w+")
debugText.write(datetime.now().strftime("%Y%m%d %H%M%S") + ": Ok let's go\n")
debugText.close()

"""
####################################################################################
Gather information about the initial image
"""

#Get the pixel size and coordinate system of the raster
ras = QgsRasterLayer(inImage)
pixelSizeX = ras.rasterUnitsPerPixelX()
pixelSizeY = ras.rasterUnitsPerPixelY()
pixelSizeAve = (pixelSizeX + pixelSizeY) / 2
coordinateSystem = ras.crs().authid()
rasExtent = ras.extent()

#Now set up some internal variables
pixelSizeBig = pixelSizeAve * speedUpFactor
radiusSize = radiusMetres/pixelSizeBig

#Make sure the radius numbers slide nicely into the grass tools
if ras.crs().toProj4()[6:13] == 'longlat':
    shadowDiameter = int(numpy.ceil((shadowBoostWidthMetres*1.4/(pixelSizeBig*111139))) // 2 * 2 + 1)
    diameterSize = int(numpy.ceil((radiusSize*2)/111139) // 2 * 2 + 1)
else:
    shadowDiameter = int(numpy.ceil((shadowBoostWidthMetres*1.4/pixelSizeBig)) // 2 * 2 + 1)
    diameterSize = int(numpy.ceil((radiusSize*2)) // 2 * 2 + 1)
diameterSizeThird = int(numpy.ceil(diameterSize/3) // 2 * 2 + 1)

#If the radius size is less than a pixel then there's a problem
if ((radiusMetres/3) <= pixelSizeAve):
    print("You must increase your radius size")
    getToItOldBoy

if ((radiusMetres/3) <= pixelSizeBig):
    print("You must decrease your speed up factor or increase your radius")
    getToItOldBoy

if (shadowDiameter < 5):
    print("You must increase your shadow boost width or decrease your speed up factor")
    getToItOldBoy

if (speedUpFactor < 1 or toneShiftFactor <= 0 or maxPixelChangeFactor <= 0 or clippingPreventionFactor < 0 or clippingPreventionFactor >= 1):
    print("The parameters are invalid, please review")
    getToItOldBoy
    
if (speedUpFactor == 1 or toneShiftFactor > 1 or maxPixelChangeFactor > 1 or clippingPreventionFactor >= 0.3 or radiusMetres < (3 * pixelSizeBig)):
    print("The current parameters aren't recommended... but good luck")



"""
####################################################################################
First check to make sure there isn't a significant tint, then prep for tiling
"""


#Let's see if tiling needs to be done 
#You won't need to do tiling if the tif is less than about 10000x10000 or if the tiling has been done previously
promptReply = QMessageBox.question(iface.mainWindow(), 'Does the raster need splitting up?', "Do you need to perform tiling?\n\nIf you don't, make sure that all the tifs are in " + processTileDirectory + " before you click no\n\nIf you do, tiling will be performed on " + inImage + " when you click yes", QMessageBox.Yes, QMessageBox.No)
if promptReply == QMessageBox.Yes:
    
    
    
    #Get some stats about the raster
    processing.run("gdal:warpreproject", {'INPUT':inImage,'SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve * 250,'OPTIONS':finalCompressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':'','OUTPUT':processDirectory + 'LowResCopy.tif'})
    processing.run("native:rasterlayerstatistics", {'INPUT':processDirectory + 'LowResCopy.tif','BAND':1,'OUTPUT_HTML_FILE':processDirectory + inImageName + 'RedStats.html'})
    processing.run("native:rasterlayerstatistics", {'INPUT':processDirectory + 'LowResCopy.tif','BAND':2,'OUTPUT_HTML_FILE':processDirectory + inImageName + 'GreenStats.html'})
    processing.run("native:rasterlayerstatistics", {'INPUT':processDirectory + 'LowResCopy.tif','BAND':3,'OUTPUT_HTML_FILE':processDirectory + inImageName + 'BlueStats.html'})

    #Make a function for getting values from the statistics file
    def getStats (statsFile):
        HtmlFile = open(statsFile, 'r', encoding='utf-8')
        fullHtml = HtmlFile.read()
        minValList = fullHtml.split("Minimum value: ")
        minValList = minValList[1].split("<")
        minVal = int(minValList[0])
        meanList = fullHtml.split("Mean value: ")
        meanList = meanList[1].split("<")
        mean = int(float(meanList[0]))
        HtmlFile.close()
        return mean, minVal

    #Grab the rgb stats
    redMean = getStats(processDirectory + inImageName + 'RedStats.html')[0]
    redMin = getStats(processDirectory + inImageName + 'RedStats.html')[1]
    greenMean = getStats(processDirectory + inImageName + 'GreenStats.html')[0]
    greenMin = getStats(processDirectory + inImageName + 'GreenStats.html')[1]
    blueMean = getStats(processDirectory + inImageName + 'BlueStats.html')[0]
    blueMin = getStats(processDirectory + inImageName + 'BlueStats.html')[1]

    #Check to see if anything is a bit sus
    if abs(redMean - greenMean) + abs(redMean - blueMean) + abs(blueMean - greenMean) > 20 or abs(redMin - greenMin) + abs(redMin - blueMin) + abs(blueMin - greenMin) > 30:
        promptReply = QMessageBox.question(iface.mainWindow(), 'Check the RGB values',"Your image may have a significant tint.\nRGB mean is " + str(redMean) + ', ' + str(greenMean) + ', ' + str(blueMean) + '.\nRGB min is ' + str(redMin) + ', ' + str(greenMin) + ', ' + str(blueMin) + '.\nDo you wish to continue?', QMessageBox.Yes, QMessageBox.No)
        if promptReply == QMessageBox.No:
            alrightLetsNotContinueThen
    
    
    print("Ok let's do some tiling")

    #Clear out the folders
    files = glob.glob(processDirectory + '*')
    for f in files:
        os.remove(f)
        
    boundsFiles = glob.glob(processBoundsDirectory + '*')
    for f in boundsFiles:
        os.remove(f)   
        
    tileFiles = glob.glob(processTileDirectory + '*')
    for f in tileFiles:
        try:
            os.remove(f) 
        except:
            print("...")

    """
    ###############################################################################################
    Creating a grid which can be used to slice up the original image into tiles
    """

    #Get the extent of the image where there is alpha
    processing.run("gdal:translate", {'INPUT':inImage,'TARGET_CRS':None,'NODATA':None,'COPY_SUBDATASETS':False,'OPTIONS':compressOptions,'EXTRA':'-b 4 -scale_1 128 255 -1000 1255','DATA_TYPE':0,'OUTPUT':processDirectory + inImageName + 'AlphaClean.tif'})
    processing.run("gdal:polygonize", {'INPUT':processDirectory + inImageName + 'AlphaClean.tif','BAND':1,'FIELD':'DN','EIGHT_CONNECTEDNESS':False,'EXTRA':'','OUTPUT':processDirectory + inImageName + 'Extent.gpkg'})
    processing.run("native:fixgeometries", {'INPUT':processDirectory + inImageName + 'Extent.gpkg','OUTPUT':processDirectory + inImageName + 'ExtentFix.gpkg'})
    processing.run("native:extractbyexpression", {'INPUT':processDirectory + inImageName + 'ExtentFix.gpkg','EXPRESSION':' \"DN\" > 245','OUTPUT':processDirectory + inImageName + 'ExtentFixFilt.gpkg'})

    #Determine the extent and coordinate system of the extent
    fullExtentForCutline = processDirectory + inImageName + 'ExtentFixFilt.gpkg'
    extentVector = QgsVectorLayer(processDirectory + inImageName + 'ExtentFixFilt.gpkg')
    extentRectangle = extentVector.extent()
    extentCrs = extentVector.sourceCrs()
    #Then close the layer object so that QGIS doesn't unnecessarily hold on to it
    QgsProject.instance().addMapLayer(extentVector, False)
    QgsProject.instance().removeMapLayer(extentVector.id())

    #Create a grid for dividing the image up into tiles
    processing.run("native:creategrid", {'TYPE':2,'EXTENT':extentRectangle,'HSPACING':pixelSizeX * approxPixelsPerTile,'VSPACING':pixelSizeY * approxPixelsPerTile,'HOVERLAY':0,'VOVERLAY':0,'CRS':extentCrs,'OUTPUT':processDirectory + inImageName + 'ExtentFixFiltGrid.gpkg'})
    
    #Buffer it out so that we have space for clipping 
    processing.run("native:buffer", {'INPUT':processDirectory + inImageName + 'ExtentFixFiltGrid.gpkg','DISTANCE':pixelSizeAve * 100,'SEGMENTS':5,'END_CAP_STYLE':0,'JOIN_STYLE':1,'MITER_LIMIT':2,'DISSOLVE':False,'OUTPUT':processDirectory + inImageName + 'ExtentFixFiltGridBuffer.gpkg'})
    processing.run("native:buffer", {'INPUT':processDirectory + inImageName + 'ExtentFixFilt.gpkg','DISTANCE':pixelSizeAve * 100,'SEGMENTS':5,'END_CAP_STYLE':0,'JOIN_STYLE':1,'MITER_LIMIT':2,'DISSOLVE':False,'OUTPUT':processDirectory + inImageName + 'ExtentFixFiltBuffer.gpkg'})


    #Determine the extent and coordinate system of the buffered extent
    bufferedExtentVector = QgsVectorLayer(processDirectory + inImageName + 'ExtentFixFiltBuffer.gpkg')
    bufferedExtentRectangle = bufferedExtentVector.extent()
    bufferedExtentCrs = bufferedExtentVector.sourceCrs()
    #Then close the layer object so that QGIS doesn't unnecessarily hold on to it
    QgsProject.instance().addMapLayer(bufferedExtentVector, False)
    QgsProject.instance().removeMapLayer(bufferedExtentVector.id())
    
    
    #Use minis in a grid so that excess areas aren't rendered
    processing.run("native:creategrid", {'TYPE':2,'EXTENT':bufferedExtentRectangle,'HSPACING':pixelSizeX * 100,'VSPACING':pixelSizeY * 100,'HOVERLAY':0,'VOVERLAY':0,'CRS':bufferedExtentCrs,'OUTPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinis.gpkg'})

    processing.run("native:joinattributesbylocation", {'INPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinis.gpkg','JOIN':processDirectory + inImageName + 'ExtentFixFiltGridBuffer.gpkg',
    'PREDICATE':[0],'JOIN_FIELDS':[],'METHOD':0,'DISCARD_NONMATCHING':False,'PREFIX':'tile','OUTPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinisSelected.gpkg'})
    
    processing.run("native:dissolve", {'INPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinisSelected.gpkg','FIELD':['tileid'],'OUTPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinisSelectedDissolve.gpkg'})


    processing.run("native:extractbylocation", {'INPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinisSelectedDissolve.gpkg','PREDICATE':[0,4,5],'INTERSECT':processDirectory + inImageName + 'ExtentFixFilt.gpkg','OUTPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinisSelectedDissolveGrabbed.gpkg'})

    #Split it out so there is a different extent to work from for each instance of the raster clipping
    processing.run("native:splitvectorlayer", {'INPUT':processDirectory + inImageName + 'ExtentFixFiltGridMinisSelectedDissolveGrabbed.gpkg','FIELD':'tileid','FILE_TYPE':0,'OUTPUT':processBoundsDirectory})
    
    

    
    """
    #################################################################################################
    Running the tile clipping as separate tasks so that you can get more done at once
    """

    #Get all of the sections of the grid
    boundsFiles = glob.glob(processBoundsDirectory + '/*.gpkg')
    boundsFiles = [i.replace("\\", "/") for i in boundsFiles]
    countOfTiles1 = 0
    countOfTiles2 = 0
    countOfTiles3 = 0
    countOfTiles4 = 0

    #Split the list of grid sections into quarters, ready for multiprocessing
    boundsNo1 = boundsFiles[0::4]
    boundsNo2 = boundsFiles[1::4]
    boundsNo3 = boundsFiles[2::4]
    boundsNo4 = boundsFiles[3::4]
 
    #Define the multiprocessing tasks
    def one(task):
        try:
            for indivBound1 in boundsNo1:
                boundName1 = indivBound1.split('/')[-1]
                boundName1 = boundName1.split('.')[0]
                processing.run("gdal:cliprasterbymasklayer", {'INPUT':inImage,'MASK':indivBound1,'SOURCE_CRS':None,'TARGET_CRS':None,'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':False,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':True,'OPTIONS':finalCompressOptions,'DATA_TYPE':0,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory  + boundName1 + 'Tile.tif'})
            print("Done pt.1")
        except BaseException as e:
            print(e)
    def two(task):
        try:
            for indivBound2 in boundsNo2:
                boundName2 = indivBound2.split('/')[-1]
                boundName2 = boundName2.split('.')[0]
                processing.run("gdal:cliprasterbymasklayer", {'INPUT':inImage,'MASK':indivBound2,'SOURCE_CRS':None,'TARGET_CRS':None,'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':False,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':True,'OPTIONS':finalCompressOptions,'DATA_TYPE':0,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory  + boundName2 + 'Tile.tif'})
            print("Done pt.2")
        except BaseException as e:
            print(e)
    def three(task):
        try:
            for indivBound3 in boundsNo3:
                boundName3 = indivBound3.split('/')[-1]
                boundName3 = boundName3.split('.')[0]
                processing.run("gdal:cliprasterbymasklayer", {'INPUT':inImage,'MASK':indivBound3,'SOURCE_CRS':None,'TARGET_CRS':None,'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':False,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':True,'OPTIONS':finalCompressOptions,'DATA_TYPE':0,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory  + boundName3 + 'Tile.tif'})
            print("Done pt.3")
        except BaseException as e:
            print(e)
    def four(task):
        try:
            for indivBound4 in boundsNo4:
                boundName4 = indivBound4.split('/')[-1]
                boundName4 = boundName4.split('.')[0]
                processing.run("gdal:cliprasterbymasklayer", {'INPUT':inImage,'MASK':indivBound4,'SOURCE_CRS':None,'TARGET_CRS':None,'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':False,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':True,'OPTIONS':finalCompressOptions,'DATA_TYPE':0,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory  + boundName4 + 'Tile.tif'})
            print("Done pt.4")
        except BaseException as e:
            print(e)

    #Assign the functions to a Qgs task
    task1 = QgsTask.fromFunction('Main Tile Task', one)
    task2 = QgsTask.fromFunction('Second Task', two)
    task3 = QgsTask.fromFunction('Third Task', three)
    task4 = QgsTask.fromFunction('Fourth Task', four)

    #Combine and run the tasks
    QgsApplication.taskManager().addTask(task1)
    QgsApplication.taskManager().addTask(task2)
    QgsApplication.taskManager().addTask(task3)
    QgsApplication.taskManager().addTask(task4)

    print("The tasks are now running in the background, you can check task manager for CPU usage")

    """
    #################################################################################################
    Wait for all these tasks to finish before proceeding with the sharpening section
    """

    #Wait for the tiling to finish...
    try:
        task1.waitForFinished(timeout = 20000000)
    except BaseException as e:
        print(e)
    try:
        task2.waitForFinished(timeout = 20000000)
    except BaseException as e:
        print(e)
    try:
        task3.waitForFinished(timeout = 20000000)
    except BaseException as e:
        print(e)
    try:
        task4.waitForFinished(timeout = 20000000)
    except BaseException as e:
        print(e)


else:
    print("Alright let's get straight into sharpening what is already in " + processTileDirectory)



"""
#############################################################################################
#############################################################################################
Set up for the batch processing
"""

#A suffix for the file output
settingsSuffix = str(speedUpFactor) + '_' + str(radiusMetres) + '_' + str(toneShiftFactor) + '_' + str(maxPixelChangeFactor) + '_' + str(clippingPreventionFactor)

#y=(640/(1+(1-0.00625)^{x}))-320
#Following the above formula style to cap the shifting of pixel values as the shift approaches 255
#A max pixel change factor of 0.25 will cap the pixel shift at about 20
maxPixelChangeFactor = maxPixelChangeFactor * maxPixelChangeFactor
capDenominator = maxPixelChangeFactor * 640
capMinusFactor = 0.00625 / (maxPixelChangeFactor**0.9)
capSubtraction = maxPixelChangeFactor * 320

#List the input images
inImageTileFiles = glob.glob(inImageTileDir + '*.tif')

#Make sure the parent process folder exists
processTileDirectoryWOutNumber = inImageTileDir + 'Processing/' 
if not os.path.exists(processTileDirectoryWOutNumber): os.mkdir(processTileDirectoryWOutNumber)


"""
####################################################################
Starting up the for-loop...
"""

#Let's process each of the images one by one
runNumber = 0
for inImageTile in inImageTileFiles:
    try:
        
        runNumber = runNumber + 1
        inImageTile = inImageTile.replace('\\','/')
        #Set up the layer name for the raster calculations
        inImageTileName = inImageTile.split("/")[-1]
        inImageTileName = inImageTileName.split(".")[0]
        

        #Make sure that the processing folder exists
        processTileDirectory = processTileDirectoryWOutNumber + inImageTileName + '/'
        try:
            os.mkdir(processTileDirectory)
        except:
            boundsFiles = glob.glob(processTileDirectory + '*')
            for f in boundsFiles:
                os.remove(f)

        #Clear out the folder
        files = glob.glob(processTileDirectory + '*')
        try:
            for f in files:
                os.remove(f)
        except BaseException as e:
            print("Bro we couldn't clear the files " + inImageTileName)
            print(e)

        """
        ###########################################################################
        Setting it up for the bigger processing
        """

        print("Initial processing")

        #Combine the bands to determine a total brightness
        processing.run("gdal:rastercalculator", {'INPUT_A': inImageTile ,'BAND_A':1,'INPUT_B':inImageTile,'BAND_B':2,'INPUT_C':inImageTile,'BAND_C':3,'INPUT_D':inImageTile,'BAND_D':4,'FORMULA':'(D>128)*(((A.astype(numpy.float64))+(B.astype(numpy.float64))+(C.astype(numpy.float64)))/3)+((D<129)*(-1))','RTYPE':1,'NO_DATA':-1,'OPTIONS':compressOptions,'EXTRA':'','OUTPUT':processTileDirectory + 'CombinedBands.tif'})
        
        #Reduce res for quicker processing
        processing.run("gdal:translate", {'INPUT':inImageTile,'TARGET_CRS':None,'NODATA':None,'COPY_SUBDATASETS':False,'OPTIONS':compressOptions,'EXTRA':'-r cubic -tr ' + str(pixelSizeBig) + ' ' + str(pixelSizeBig) + ' -b 1','DATA_TYPE':0,'OUTPUT':processTileDirectory + 'ReducedResRed.tif'})
        processing.run("gdal:translate", {'INPUT':inImageTile,'TARGET_CRS':None,'NODATA':None,'COPY_SUBDATASETS':False,'OPTIONS':compressOptions,'EXTRA':'-r cubic -tr ' + str(pixelSizeBig) + ' ' + str(pixelSizeBig) + ' -b 2','DATA_TYPE':0,'OUTPUT':processTileDirectory + 'ReducedResGreen.tif'})
        processing.run("gdal:translate", {'INPUT':inImageTile,'TARGET_CRS':None,'NODATA':None,'COPY_SUBDATASETS':False,'OPTIONS':compressOptions,'EXTRA':'-r cubic -tr ' + str(pixelSizeBig) + ' ' + str(pixelSizeBig) + ' -b 3','DATA_TYPE':0,'OUTPUT':processTileDirectory + 'ReducedResBlue.tif'})

        #Calculate the minimum and maximum among all bands
        processing.run("grass7:r.series", {'input':[processTileDirectory + 'ReducedResBlue.tif',processTileDirectory + 'ReducedResGreen.tif',processTileDirectory + 'ReducedResRed.tif'],'-n':True,'method':[4],'quantile':'','weights':'','output':processTileDirectory + 'TrueMinimum.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        processing.run("grass7:r.series", {'input':[processTileDirectory + 'ReducedResBlue.tif',processTileDirectory + 'ReducedResGreen.tif',processTileDirectory + 'ReducedResRed.tif'],'-n':True,'method':[6],'quantile':'','weights':'','output':processTileDirectory + 'TrueMaximum.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})

        #Reduce the resolution for the combined bands, bilinear and the scale parameters are used to prevent values from being 0, which causes glitches in grass tools
        processing.run("gdal:translate", {'INPUT':processTileDirectory + 'CombinedBands.tif','TARGET_CRS':None,'NODATA':None,'COPY_SUBDATASETS':False,'OPTIONS':compressOptions,'EXTRA':'-r bilinear -tr ' + str(pixelSizeBig) + ' ' + str(pixelSizeBig) + ' -b 1 -scale 0 255 1 255','DATA_TYPE':0,'OUTPUT':processTileDirectory + 'ReducedResCombined.tif'})


        """
        ##########################################################################
        Find the shadowed areas for later correction
        """
        
        #Shadow area A
        #Grab pixels that are very dark
        processing.run("qgis:rastercalculator", {'EXPRESSION':'8/(1+1.15^(\"ReducedResCombined@1\"-30))','LAYERS':[processTileDirectory + 'ReducedResCombined.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'ShadowChanceA.tif'})
        #Determine where the bigger areas are
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ShadowChanceA.tif','selection':processTileDirectory + 'ShadowChanceA.tif','method':15,'size':shadowDiameter - 2,'gauss':None,'quantile':'0.10','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'ShadowChanceASmooth.tif','nprocs':8,'GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        #Confirming the bigger shadow parts
        processing.run("qgis:rastercalculator", {'EXPRESSION':'(\"ShadowChanceA@1\"^0.2)  *  (\"ShadowChanceASmooth@1\" ^ 0.7)','LAYERS':[processTileDirectory + 'ShadowChanceASmooth.tif',processTileDirectory + 'ShadowChanceA.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'ShadowChanceAMultiply.tif'})
        #Give approval for the shadow area B to spread 
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ShadowChanceAMultiply.tif','selection':processTileDirectory + 'ShadowChanceAMultiply.tif','method':0,'size':shadowDiameter,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'ShadowChanceAMultiplyApproval.tif','nprocs':8,'GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})

        #Shadow area B
        #Grab pixels that are fairly dark
        processing.run("qgis:rastercalculator", {'EXPRESSION':'8/(1+1.15^(\"ReducedResCombined@1\"-52))','LAYERS':[processTileDirectory + 'ReducedResCombined.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'ShadowChanceB.tif'})
        #Determine where the bigger areas are
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ShadowChanceB.tif','selection':processTileDirectory + 'ShadowChanceB.tif','method':15,'size':shadowDiameter,'gauss':None,'quantile':'0.28','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'ShadowChanceBSmooth.tif','nprocs':8,'GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        #Confirming the bigger shadow parts as approved by shadow area A
        processing.run("qgis:rastercalculator",{'EXPRESSION':'(\"ShadowChanceB@1\"^0.2)  *  (\"ShadowChanceBSmooth@1\" ^ 0.6) * ((\"ShadowChanceAMultiplyApproval@1\" ^ 0.5) + 0.1)','LAYERS':[processTileDirectory + 'ShadowChanceBSmooth.tif',processTileDirectory + 'ShadowChanceB.tif',processTileDirectory + 'ShadowChanceAMultiplyApproval.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'ShadowChanceBMultiply.tif'})
        #Give approval for the shadow area C to spread 
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ShadowChanceBMultiply.tif','selection':processTileDirectory + 'ShadowChanceBMultiply.tif','method':15,'size':shadowDiameter + 2,'gauss':None,'quantile':'0.92','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'ShadowChanceBMultiplyApproval.tif','nprocs':8,'GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        
        #Shadow area C
        #Grab pixels that are somewhat dark
        processing.run("qgis:rastercalculator", {'EXPRESSION':'8/(1+1.15^(\"ReducedResCombined@1\"-85))','LAYERS':[processTileDirectory + 'ReducedResCombined.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'ShadowChanceC.tif'})
        #Determine where the bigger areas are
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ShadowChanceC.tif','selection':processTileDirectory + 'ShadowChanceC.tif','method':15,'size':shadowDiameter,'gauss':None,'quantile':'0.4','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'ShadowChanceCSmooth.tif','nprocs':8,'GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        #Confirming the bigger shadow parts as approved by shadow area B
        processing.run("qgis:rastercalculator",{'EXPRESSION':'(\"ShadowChanceC@1\"^0.2)  *  (\"ShadowChanceCSmooth@1\" ^ 0.6) * ((\"ShadowChanceBMultiplyApproval@1\" ^ 0.6)) * ' + str(shadowBoostFactor),'LAYERS':[processTileDirectory + 'ShadowChanceCSmooth.tif',processTileDirectory + 'ShadowChanceC.tif',processTileDirectory + 'ShadowChanceBMultiplyApproval.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'ShadowChanceCMultiply.tif'})
        #Bring out to full res
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'ShadowChanceCMultiply.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'ShadowBoostFinal.tif'})
        
        
        """
        ##########################################################################
        Determining the difference to apply based on the larger radius
        """

        print("Speed up factor engaged")
        print("(Increase the speed up factor if this part takes too long)")


        #Calculate the minimum and maximum of the combined bands within the radius
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ReducedResCombined.tif','selection':processTileDirectory + 'ReducedResCombined.tif','method':4,'size':diameterSize,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MaximumCombined.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ReducedResCombined.tif','selection':processTileDirectory + 'ReducedResCombined.tif','method':3,'size':diameterSize,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MinimumCombined.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})


        #Smooth off those hard edges
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'MaximumCombined.tif','selection':processTileDirectory + 'MinimumCombined.tif','method':0,'size':diameterSize,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MaximumSmooth.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'MinimumCombined.tif','selection':processTileDirectory + 'MinimumCombined.tif','method':0,'size':diameterSize,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MinimumSmooth.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})


        #Scale the amount that the midtone is allowed to be moved
        processing.run("qgis:rastercalculator", {'EXPRESSION':' \"MinimumSmooth@1\" ^ ' + str(toneShiftFactor),'LAYERS':[processTileDirectory + 'MinimumSmooth.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'MinimumSmoothScaled.tif'})
        processing.run("qgis:rastercalculator", {'EXPRESSION':' (((abs(\"MaximumSmooth@1\"-255))^ '+ str(toneShiftFactor)+ ')*-1)+255 ' ,'LAYERS':[processTileDirectory + 'MaximumSmooth.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'MaximumSmoothScaled.tif'})


        #Use the min and max to calculate range and midrange
        processing.run("qgis:rastercalculator", {'EXPRESSION':'\"MaximumSmoothScaled@1\" - \"MinimumSmoothScaled@1\"','LAYERS':[processTileDirectory + 'MaximumSmoothScaled.tif',processTileDirectory + 'MinimumSmoothScaled.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'Range.tif'})
        processing.run("qgis:rastercalculator", {'EXPRESSION':'(\"MaximumSmoothScaled@1\" + \"MinimumSmoothScaled@1\")/2','LAYERS':[processTileDirectory + 'MaximumSmoothScaled.tif',processTileDirectory + 'MinimumSmoothScaled.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'Midrange.tif'})


        #Bring the res back out to full
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'Range.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve,'OPTIONS':compressOptions,'DATA_TYPE':0,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'RangeResamp.tif'})
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'Midrange.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve,'OPTIONS':compressOptions,'DATA_TYPE':0,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'MidrangeResamp.tif'})



        #Look for potential clipping
        processing.run("qgis:rastercalculator", {'EXPRESSION':'(\"TrueMaximum@1\" - \"Midrange@1\")*((255/(\"Range@1\"+1)))-128','LAYERS':[processTileDirectory + 'TrueMaximum.tif',processTileDirectory + 'Midrange.tif',processTileDirectory + 'Range.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'WhiteClip.tif','OPTIONS': compressOptions})
        processing.run("qgis:rastercalculator", {'EXPRESSION':'-(\"TrueMinimum@1\" - \"Midrange@1\")*((255/(\"Range@1\"+1)))-128','LAYERS':[processTileDirectory + 'TrueMinimum.tif',processTileDirectory + 'Midrange.tif',processTileDirectory + 'Range.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':processTileDirectory + 'BlackClip.tif','OPTIONS': compressOptions})
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'WhiteClip.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'WhiteClipByte.tif'})
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'BlackClip.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'BlackClipByte.tif'})
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'WhiteClipByte.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':7,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig * 4,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'WhiteClipByteExpand.tif'})
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'BlackClipByte.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':7,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig * 4,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'BlackClipByteExpand.tif'})
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'WhiteClipByteExpand.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'WhiteClipByteExpandSmooth.tif'})
        processing.run("gdal:warpreproject", {'INPUT':processTileDirectory + 'BlackClipByteExpand.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':processTileDirectory + 'BlackClipByteExpandSmooth.tif'})
        

        #Use the determined formula to figure out what difference needs to be applied to the pixels to stretch them to 0-255
        #0.85 is a factor to increase the effect of the larger radius
        processing.run("qgis:rastercalculator", {'EXPRESSION':'((\"CombinedBands@1\" - \"MidrangeResamp@1\")*((255/(\"RangeResamp@1\"+1)))+128 - \"CombinedBands@1\") / 0.80','LAYERS':[processTileDirectory + 'CombinedBands.tif',processTileDirectory + 'MidrangeResamp.tif',processTileDirectory + 'RangeResamp.tif'],'CELLSIZE':0,'EXTENT':rasExtent,'CRS':None,'OUTPUT':processTileDirectory + 'DifferenceToApply.tif','OPTIONS': compressOptions})
        
        
        """
        ###########################################################################
        Determining the difference to apply based on the smaller radius
        """

        #Calculate the minimum and maximum of the combined bands within the radius
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ReducedResCombined.tif','selection':processTileDirectory + 'ReducedResCombined.tif','method':4,'size':diameterSizeThird,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MaximumCombinedThird.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'ReducedResCombined.tif','selection':processTileDirectory + 'ReducedResCombined.tif','method':3,'size':diameterSizeThird,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MinimumCombinedThird.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})

        #Smooth off those hard edges
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'MaximumCombinedThird.tif','selection':processTileDirectory + 'MaximumCombinedThird.tif','method':0,'size':diameterSizeThird,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MaximumSmoothThird.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})
        processing.run("grass7:r.neighbors", {'input':processTileDirectory + 'MinimumCombinedThird.tif','selection':processTileDirectory + 'MinimumCombinedThird.tif','method':0,'size':diameterSizeThird,'gauss':None,'quantile':'','-c':True,'-a':False,'weight':'','output':processTileDirectory + 'MinimumSmoothThird.tif','GRASS_REGION_PARAMETER':None,'GRASS_REGION_CELLSIZE_PARAMETER':0,'GRASS_RASTER_FORMAT_OPT':'','GRASS_RASTER_FORMAT_META':''})

        """
        ###########################################################################
        Start up the non-grass task
        """
        
        def processEachList(task, taskProcessTileDirectory, taskInImageTileName, taskInImageTile, taskRasExtent):
                
            print("Applying the differences for" + taskInImageTile)
            print("Process dir" + taskProcessTileDirectory)
            
            
            #Scale the amount that the midtone is allowed to be moved
            processing.run("qgis:rastercalculator", {'EXPRESSION':' \"MinimumSmoothThird@1\" ^ ' + str(toneShiftFactor),'LAYERS':[taskProcessTileDirectory + 'MinimumSmoothThird.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'MinimumSmoothScaledThird.tif'})
            processing.run("qgis:rastercalculator", {'EXPRESSION':' (((abs(\"MaximumSmoothThird@1\"-255))^ '+ str(toneShiftFactor)+ ')*-1)+255 ' ,'LAYERS':[taskProcessTileDirectory + 'MaximumSmoothThird.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'MaximumSmoothScaledThird.tif'})

            #Use the min and max to calculate range and midrange
            processing.run("qgis:rastercalculator", {'EXPRESSION':'\"MaximumSmoothScaledThird@1\" - \"MinimumSmoothScaledThird@1\"','LAYERS':[taskProcessTileDirectory + 'MaximumSmoothScaledThird.tif',taskProcessTileDirectory + 'MinimumSmoothScaledThird.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'RangeThird.tif'})
            processing.run("qgis:rastercalculator", {'EXPRESSION':'(\"MaximumSmoothScaledThird@1\" + \"MinimumSmoothScaledThird@1\")/2','LAYERS':[taskProcessTileDirectory + 'MaximumSmoothScaledThird.tif',taskProcessTileDirectory + 'MinimumSmoothScaledThird.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'MidrangeThird.tif'})

            print("Speed up factor disengaging")

            #Bring the res back out to full
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'RangeThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve,'OPTIONS':compressOptions,'DATA_TYPE':0,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'RangeResampThird.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'MidrangeThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve,'OPTIONS':compressOptions,'DATA_TYPE':0,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'MidrangeResampThird.tif'})


            #Look for potential clipping
            processing.run("qgis:rastercalculator", {'EXPRESSION':'(\"TrueMaximum@1\" - \"MidrangeThird@1\")*((255/(\"RangeThird@1\"+1)))-128','LAYERS':[taskProcessTileDirectory + 'TrueMaximum.tif',taskProcessTileDirectory + 'MidrangeThird.tif',taskProcessTileDirectory + 'RangeThird.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'WhiteClipThird.tif','OPTIONS':compressOptions})
            processing.run("qgis:rastercalculator", {'EXPRESSION':'-(\"TrueMinimum@1\" - \"MidrangeThird@1\")*((255/(\"RangeThird@1\"+1)))-128','LAYERS':[taskProcessTileDirectory + 'TrueMinimum.tif',taskProcessTileDirectory + 'MidrangeThird.tif',taskProcessTileDirectory + 'RangeThird.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'BlackClipThird.tif','OPTIONS':compressOptions})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'WhiteClipThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'WhiteClipByteThird.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'BlackClipThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'BlackClipByteThird.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'WhiteClipByteThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':7,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig * 2,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'WhiteClipByteExpandThird.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'BlackClipByteThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':7,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig * 2,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'BlackClipByteExpandThird.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'WhiteClipByteExpandThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'WhiteClipByteExpandSmoothThird.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'BlackClipByteExpandThird.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeBig,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'BlackClipByteExpandSmoothThird.tif'})
            

            #Use the determined formula to figure out what difference needs to be applied to the pixels to stretch them to 0-255
            #0.85 is a factor to decrease the effect of the smaller radius
            processing.run("qgis:rastercalculator", {'EXPRESSION':'((\"CombinedBands@1\" - \"MidrangeResampThird@1\")*((255/(\"RangeResampThird@1\"+1)))+128 - \"CombinedBands@1\") * 0.80 ','LAYERS':[taskProcessTileDirectory + 'CombinedBands.tif',taskProcessTileDirectory + 'MidrangeResampThird.tif',taskProcessTileDirectory + 'RangeResampThird.tif'],'CELLSIZE':0,'EXTENT':taskRasExtent,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'DifferenceToApplyThird.tif','OPTIONS': compressOptions})

            
            """
            ###########################################################################
            Bring together the pixel shift amounts for each of the radii and apply them to the original bands
            """
            
            #z=(x+y)*((1)/(abs(x-y)+abs(x+y))) abs(x+y)
            #The above formula is a three dimensional function that combines values such that there is a penalty for disagreeance 
            processing.run("qgis:rastercalculator", {'EXPRESSION':'0.5*(\"DifferenceToApply@1\"+\"DifferenceToApplyThird@1\")*((1)/(abs(\"DifferenceToApply@1\"-\"DifferenceToApplyThird@1\")+abs(\"DifferenceToApply@1\"+\"DifferenceToApplyThird@1\"))) * abs(\"DifferenceToApply@1\"+\"DifferenceToApplyThird@1\")','LAYERS':[taskInImageTile,taskProcessTileDirectory + 'DifferenceToApply.tif',taskProcessTileDirectory + 'DifferenceToApplyThird.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'CombinedDifference.tif','OPTIONS': compressOptions})

            #Scale the differencing amounts back as per the formula to cap extreme values
            processing.run("qgis:rastercalculator", {'EXPRESSION':'(' + str(capDenominator) + '/ ( 1 + (1 - ' + str(capMinusFactor) + ' ) ^ ( \"CombinedDifference@1\" ) ) ) - ' + str(capSubtraction),'LAYERS':[taskInImageTile,taskProcessTileDirectory + 'CombinedDifference.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'ScaledBackDifference.tif','OPTIONS': compressOptions})

            

            #Calculate how much to pull back the pixels from clipping
            processing.run("qgis:rastercalculator", {'EXPRESSION':' ( 1.004 ^(( (\"WhiteClipByteExpandSmooth@1\" ^ 0.5) + (\"WhiteClipByteExpandSmoothThird@1\" ^ 0.5) ) * 1)) - 1','LAYERS':[taskProcessTileDirectory + 'WhiteClipByteExpandSmoothThird.tif',taskProcessTileDirectory + 'WhiteClipByteExpandSmooth.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'WhiteClipFactor.tif','OPTIONS':compressOptions})
            processing.run("qgis:rastercalculator", {'EXPRESSION':' ( 1.004 ^(( (\"BlackClipByteExpandSmooth@1\" ^ 0.5) + (\"BlackClipByteExpandSmoothThird@1\" ^ 0.5) ) * 1)) - 1','LAYERS':[taskProcessTileDirectory + 'BlackClipByteExpandSmoothThird.tif',taskProcessTileDirectory + 'BlackClipByteExpandSmooth.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'BlackClipFactor.tif','OPTIONS':compressOptions})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'WhiteClipFactor.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve,'OPTIONS':compressOptions,'DATA_TYPE':6,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'WhiteClipFactorResamp.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'BlackClipFactor.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':3,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve,'OPTIONS':compressOptions,'DATA_TYPE':6,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'BlackClipFactorResamp.tif'})

            
            #Apply the difference to the bands, potentially with clipping prevention
            processing.run("qgis:rastercalculator", {'EXPRESSION':'((\"' + taskInImageTileName + '@1\" + \"ScaledBackDifference@1\")*(1- \"WhiteClipFactorResamp@1\" - \"BlackClipFactorResamp@1\"))+ (255 * ( \"BlackClipFactorResamp@1\" )) + (\"ShadowBoostFinal@1\")','LAYERS':[taskInImageTile,taskProcessTileDirectory + 'ScaledBackDifference.tif',taskProcessTileDirectory + 'WhiteClipFactorResamp.tif',taskProcessTileDirectory + 'BlackClipFactorResamp.tif',taskProcessTileDirectory + 'ShadowBoostFinal.tif'],'CELLSIZE':0,'EXTENT':taskRasExtent,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'Band1Diffed.tif','OPTIONS': compressOptions})
            processing.run("qgis:rastercalculator", {'EXPRESSION':'((\"' + taskInImageTileName + '@2\" + \"ScaledBackDifference@1\")*(1- \"WhiteClipFactorResamp@1\" - \"BlackClipFactorResamp@1\"))+ (255 * ( \"BlackClipFactorResamp@1\" )) + (\"ShadowBoostFinal@1\")','LAYERS':[taskInImageTile,taskProcessTileDirectory + 'ScaledBackDifference.tif',taskProcessTileDirectory + 'WhiteClipFactorResamp.tif',taskProcessTileDirectory + 'BlackClipFactorResamp.tif',taskProcessTileDirectory + 'ShadowBoostFinal.tif'],'CELLSIZE':0,'EXTENT':taskRasExtent,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'Band2Diffed.tif','OPTIONS': compressOptions})
            processing.run("qgis:rastercalculator", {'EXPRESSION':'((\"' + taskInImageTileName + '@3\" + \"ScaledBackDifference@1\")*(1- \"WhiteClipFactorResamp@1\" - \"BlackClipFactorResamp@1\"))+ (255 * ( \"BlackClipFactorResamp@1\" )) + (\"ShadowBoostFinal@1\")','LAYERS':[taskInImageTile,taskProcessTileDirectory + 'ScaledBackDifference.tif',taskProcessTileDirectory + 'WhiteClipFactorResamp.tif',taskProcessTileDirectory + 'BlackClipFactorResamp.tif',taskProcessTileDirectory + 'ShadowBoostFinal.tif'],'CELLSIZE':0,'EXTENT':taskRasExtent,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'Band3Diffed.tif','OPTIONS': compressOptions})

            
            """
            ###########################################################################
            The tiles need a fading alpha band so they sit together nicely
            """

            
            #Get the full extent of the tile
            processing.run("native:polygonfromlayerextent", {'INPUT':taskInImageTile,'ROUND_TO':0,'OUTPUT':taskProcessTileDirectory + 'FullExtent.gpkg'})
            
            #Bring this in so that any border issues are taken away
            processing.run("native:buffer", {'INPUT':taskProcessTileDirectory + 'FullExtent.gpkg','DISTANCE':pixelSizeAve * (-2),'SEGMENTS':5,'END_CAP_STYLE':0,'JOIN_STYLE':0,'MITER_LIMIT':2,'DISSOLVE':False,'OUTPUT':taskProcessTileDirectory + 'FullExtentIn.gpkg'})
           
            #Then convert to lines so that
            processing.run("native:polygonstolines", {'INPUT':taskProcessTileDirectory + 'FullExtentIn.gpkg','OUTPUT':taskProcessTileDirectory + 'FullExtentInLines.gpkg'})
            
            #A raster is buffered off the lines so that has its values at 255 across most of the raster, but fades down to 0 at the edges
            processing.run("gdal:rasterize", {'INPUT':taskProcessTileDirectory + 'FullExtentInLines.gpkg','FIELD':'','BURN':1,'UNITS':1,'WIDTH':pixelSizeX,'HEIGHT':pixelSizeY,'EXTENT':taskRasExtent,'NODATA':None,'OPTIONS':compressOptions,'DATA_TYPE':0,'INIT':None,'INVERT':False,'EXTRA':'','OUTPUT':taskProcessTileDirectory + 'FullExtentLinesRasterize.tif'})
            processing.run("gdal:proximity", {'INPUT':taskProcessTileDirectory + 'FullExtentLinesRasterize.tif','BAND':1,'VALUES':'1','UNITS':1,'MAX_DISTANCE':64,'REPLACE':None,'NODATA':64,'OPTIONS':compressOptions,'EXTRA':'','DATA_TYPE':0,'OUTPUT':taskProcessTileDirectory + 'FullExtentLinesRasterizeDistance.tif'})
            processing.run("qgis:rastercalculator", {'EXPRESSION':'\"FullExtentLinesRasterizeDistance@1\" * 4','LAYERS':[taskProcessTileDirectory + 'FullExtentLinesRasterizeDistance.tif'],'CELLSIZE':0,'EXTENT':None,'CRS':None,'OUTPUT':taskProcessTileDirectory + 'AlphaBand.tif','OPTIONS': compressOptions})
            
            fullExtentVector = QgsVectorLayer(taskProcessTileDirectory + 'FullExtent.gpkg')
            QgsProject.instance().addMapLayer(fullExtentVector, False)
            QgsProject.instance().removeMapLayer(fullExtentVector.id())
            fullExtentInVector = QgsVectorLayer(taskProcessTileDirectory + 'FullExtentIn.gpkg')
            QgsProject.instance().addMapLayer(fullExtentInVector, False)
            QgsProject.instance().removeMapLayer(fullExtentInVector.id())

            """
            ###########################################################################
            Bring all the bands together
            """
            
            print("Final value clipping and exporting...")

            #Clip values to within 0 and 255
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'Band1Diffed.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':taskRasExtent,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'Band1DiffedByte.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'Band2Diffed.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':taskRasExtent,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'Band2DiffedByte.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'Band3Diffed.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':taskRasExtent,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'Band3DiffedByte.tif'})
            processing.run("gdal:warpreproject", {'INPUT':taskProcessTileDirectory + 'AlphaBand.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':None,'OPTIONS':compressOptions,'DATA_TYPE':1,'TARGET_EXTENT':taskRasExtent,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':gdalOptions,'OUTPUT':taskProcessTileDirectory + 'AlphaBandByte.tif'})

            #Bring the bands together
            processing.run("gdal:buildvirtualraster", {'INPUT':[taskProcessTileDirectory + 'Band1DiffedByte.tif',taskProcessTileDirectory + 'Band2DiffedByte.tif',taskProcessTileDirectory + 'Band3DiffedByte.tif',taskProcessTileDirectory + 'AlphaBandByte.tif'],'RESOLUTION':2,'SEPARATE':True,'PROJ_DIFFERENCE':True,'ADD_ALPHA':False,'ASSIGN_CRS':None,'RESAMPLING':0,'SRC_NODATA':'','EXTRA':'','OUTPUT':taskProcessTileDirectory + 'Band123A.vrt'})

            #Determine where must be clipped to, given the bigger pixels won't line up with the smaller pixels
            processing.run("native:polygonfromlayerextent", {'INPUT':taskProcessTileDirectory + 'ReducedResRed.tif','ROUND_TO':0,'OUTPUT':taskProcessTileDirectory + 'ReducedResExtent.gpkg'})
            processing.run("native:buffer", {'INPUT':taskProcessTileDirectory + 'ReducedResExtent.gpkg','DISTANCE':(pixelSizeBig + (pixelSizeAve * 0.8)) * -1,'SEGMENTS':5,'END_CAP_STYLE':0,'JOIN_STYLE':0,'MITER_LIMIT':2,'DISSOLVE':False,'OUTPUT':taskProcessTileDirectory + 'ReducedResExtentIn.gpkg'})
         
            
            #Clip to vrt to export a final tif
            processing.run("gdal:cliprasterbymasklayer", {'INPUT':taskProcessTileDirectory + 'Band123A.vrt','MASK':taskProcessTileDirectory + 'FullExtentIn.gpkg','SOURCE_CRS':None,'TARGET_CRS':None,'NODATA':None,
            'ALPHA_BAND':False,'CROP_TO_CUTLINE':True,'KEEP_RESOLUTION':False,'SET_RESOLUTION':False,'X_RESOLUTION':None,'Y_RESOLUTION':None,'MULTITHREADING':True,'OPTIONS':finalCompressOptions,'DATA_TYPE':1,
            'EXTRA':'-co \"PHOTOMETRIC=RGB\" -srcalpha -dstalpha ' + gdalOptions,'OUTPUT':outImageDir + taskInImageTileName + 'ClippedFinalTile' + settingsSuffix + '.tif'})
            print("Final tile export done")
            
            """
            ###########################################################################
            Debug writing and temp file clean up
            """
            
            #Make sure that there aren't too many processes piling up
            debugText = open(otherDirectory + inImageName + "Debug.txt","a+")
            debugText.write(datetime.now().strftime("%Y%m%d %H%M%S") + ": Ok " + taskInImageTileName + ' is done. Currently there are ' + str(QgsApplication.taskManager().countActiveTasks()) + ' tasks running. Free memory is ' + str(round(psutil.virtual_memory().free / 1000000000,1)) + 'gb. \n')
            debugText.close()
            
            #Clean up the files so we don't run out of hard drive space
            time.sleep(0.1)
            processFiles = glob.glob(taskProcessTileDirectory + '*')
            for f in processFiles:
                try:
                    os.remove(f)
                except BaseException as e:
                    e = e
                    
            confirmationText = open(otherDirectory + 'ConfirmationFiles/' + taskInImageTileName + "Confirmation.txt","w+")
            confirmationText.write(inImageTileName + ' confirmed complete')
            confirmationText.close()    
        
        """
        #######################################################################
        Running all of the above through a task, before starting up the next tile in parallel
        """

        print("About to run the task for " + inImageTileName)
        #Assign the functions to a Qgs task and run
        beyondGrassTask = QgsTask.fromFunction(inImageTile + 'FirstOne', processEachList, processTileDirectory, inImageTileName, inImageTile, rasExtent)
        
        #Make sure that it is not until the final run through of the loop that next part of the process runs
        QgsApplication.taskManager().addTask(beyondGrassTask)

    except BaseException as e:
        print("Bro it failed " + inImageTileName)
        print(e)
        debugText = open(otherDirectory + inImageName + "Debug.txt","a+")
        debugText.write(datetime.now().strftime("%Y%m%d %H%M%S") + ": So " + inImageTileName + ' failed to process. Error message is ' + str(e) + '. Currently there are ' + str(QgsApplication.taskManager().countActiveTasks()) + ' tasks running. Free memory is ' + str(round(psutil.virtual_memory().free / 1000000000,1)) + 'gb. \n')
        debugText.close()

    
"""
#######################################################################
Once all tiles are processed, they can be brought together
"""

#This makes sure that the cmd process doesn't take off before the tiles are ready    
print("Ok lets make sure the tasks (" + str(QgsApplication.taskManager().countActiveTasks()) + ") have finished before doing the final merge")

numberOfTilesDone = 0
while numberOfTilesDone < len(inImageTileFiles):
    confirmationFiles = glob.glob(otherDirectory + 'ConfirmationFiles/' + '*.txt')
    numberOfTilesDone = len(confirmationFiles)
    debugText = open(otherDirectory + inImageName + "Debug.txt","a+")
    debugText.write(str(numberOfTilesDone) + ' tiles done. ' + str(len(inImageTileFiles)) + ' total tiles. The time is ' + datetime.now().strftime("%Y%m%d %H%M%S"))
    debugText.close()
    
    time.sleep(5)
    
    


print("Ok so there are still " + str(QgsApplication.taskManager().countActiveTasks()) + " tasks running before the merge")


#Prepare to make a final mosaic where the alpha bands are respected, this is a string being prepped for cmd
mosaicInString = ''
outImageDir = outImageDir.replace("/", "\\")

#Make the final image directory
finalImageDir = finalImageDir.replace("/", "\\")
if not os.path.exists(finalImageDir):os.mkdir(finalImageDir)

#Prepare variables for the final merging in GDAL
fullExtentForCutline = processDirectory + inImageName + 'ExtentFixFilt.gpkg'
fullExtentForCutline = fullExtentForCutline.replace("/", "\\")
finalOutputImageName = outImageName + datetime.now().strftime("%Y%m%d%H%M") 
finalOutputImage = finalImageDir + finalOutputImageName + '.tif'

#Run gdal through cmd using syntax that it likes (the gdal exe is in cd C:\Program Files\QGIS 3.16\bin)
gdalOptionsFinal = '-co COMPRESS=LZW -co PREDICTOR=2 -co NUM_THREADS=ALL_CPUS -co BIGTIFF=IF_SAFER -co TILED=YES -multi --config GDAL_NUM_THREADS ALL_CPUS -wo NUM_THREADS=ALL_CPUS -overwrite'
cmd = 'gdalwarp -of GTiff ' + gdalOptionsFinal + ' -crop_to_cutline -cutline "' + fullExtentForCutline + '" "' + outImageDir + '**.tif" "' + finalOutputImage + '" & timeout 3'
print("Watch the cmd window")
os.system(cmd)


"""
##########################################################################
Histograms can be used to inform on how much value clipping is going on
"""

#This is run and left as a separate process as it's an optional extra amount of information to the final tif
def finalWork(task, taskFinalOutputImage):
    try:
        #Histogram calculations by reducing resolution then analysing each band
        processing.run("gdal:warpreproject", {'INPUT':taskFinalOutputImage,'SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':-1,'TARGET_RESOLUTION':pixelSizeAve * 100,'OPTIONS':compressOptions,'DATA_TYPE':2,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':'','OUTPUT':processDirectory + 'ReducedResForHisto.tif'})

        processing.run("qgis:rasterlayerhistogram", {'INPUT':processDirectory + 'ReducedResForHisto.tif','BAND':1,'BINS':256,'OUTPUT':finalImageDir + finalOutputImageName + 'FinalHistoRed.html'})
        processing.run("qgis:rasterlayerhistogram", {'INPUT':processDirectory + 'ReducedResForHisto.tif','BAND':2,'BINS':256,'OUTPUT':finalImageDir + finalOutputImageName + 'FinalHistoGreen.html'})
        processing.run("qgis:rasterlayerhistogram", {'INPUT':processDirectory + 'ReducedResForHisto.tif','BAND':3,'BINS':256,'OUTPUT':finalImageDir + finalOutputImageName + 'FinalHistoBlue.html'})
        
        #Creating a small thumbnail so that you know the extent from windows explorer
        processing.run("gdal:warpreproject", {'INPUT':processDirectory + 'ReducedResForHisto.tif','SOURCE_CRS':None,'TARGET_CRS':None,'RESAMPLING':0,'NODATA':None,'TARGET_RESOLUTION':pixelSizeAve * 100,'OPTIONS':finalCompressOptions,'DATA_TYPE':1,'TARGET_EXTENT':None,'TARGET_EXTENT_CRS':None,'MULTITHREADING':True,'EXTRA':'','OUTPUT':finalImageDir + finalOutputImageName + 'Thumbnail.tif'})
        
        #Building pyramid layers so that you can browse easily
        processing.run("gdal:overviews", {'INPUT':taskFinalOutputImage,'CLEAN':False,'LEVELS':'','RESAMPLING':0,'FORMAT':1,'EXTRA':'--config COMPRESS_OVERVIEW JPEG'})
    except BaseException as e:
        print (e)

finalTask = QgsTask.fromFunction('FinalWork', finalWork, finalOutputImage)
QgsApplication.taskManager().addTask(finalTask)

"""
#########################################################################
"""

endTime = time.time()
totalTime = endTime - startTime
print("Done, this took " + str(int(totalTime)) + " seconds")
print("The final tasks (making a thumbnail, histogram and pyramids) will continue for a bit...")


"""
#######################################################################
"""


