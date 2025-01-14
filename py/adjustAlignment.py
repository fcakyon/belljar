import cv2
import numpy as np
import argparse
import os
import pickle
import csv

parser = argparse.ArgumentParser(
    description='Allow adjustment of region alignments')
parser.add_argument(
    '-i', '--input', help='input files, pkl atlas files and dapi images in same folder', default='')
parser.add_argument('-s', '--structures', help='structures file',
                    default='../csv/structure_tree_safe_2017.csv')
args = parser.parse_args()

# Get all files in the input directory
args.input = args.input.strip()
files = os.listdir(args.input)
annotationsPkl = [f for f in files if f.endswith('.pkl')]
dapiImages = [f for f in files if f.endswith('.png')]

# Prep regions for saving
regions = {}
nameToRegion = {}
with open(args.structures.strip()) as structureFile:
    structureReader = csv.reader(structureFile, delimiter=",")

    header = next(structureReader)  # skip header
    root = next(structureReader)  # skip atlas root region
    # manually set root, due to weird values
    regions[997] = {"acronym": "undefined", "name": "undefined",
                    "parent": "N/A", "points": [], 'color': [0, 0, 0]}
    regions[0] = {"acronym": "LIW", "name": "Lost in Warp",
                  "parent": "N/A", "points": [], 'color': [0, 0, 0]}
    nameToRegion["undefined"] = 997
    nameToRegion["Lost in Warp"] = 0
    # function to create unique color tuples
    usedColors = []

    def getColor():
        color = np.random.randint(0, 255, (3)).tolist()
        while color in usedColors:
            color = np.random.randint(0, 255, (3)).tolist()
        usedColors.append(color)
        return color
    # store all other atlas regions and their linkages
    for row in structureReader:
        regions[int(row[0])] = {"acronym": row[3], "name": row[2], "parent": int(
            row[8]), "points": [], "color": getColor()}
        nameToRegion[row[2]] = int(row[0])

end = False
print(2, flush=True)
print('Running alignment adjustment...', flush=True)
for annoPkl, dapi in zip(annotationsPkl, dapiImages):
    if end:
        break
    # Load the annotations
    with open(os.path.join(args.input, annoPkl), 'rb') as f:
        annoWarp = pickle.load(f)
    # Pad 100 pixels on each side of the image
    pad = 100
    dapi = cv2.imread(os.path.join(args.input, dapi), cv2.IMREAD_COLOR)
    dapi = cv2.copyMakeBorder(dapi, pad, pad, pad, pad,
                              cv2.BORDER_CONSTANT, value=(0, 0, 0))
    y, x = annoWarp.shape
    mapImage = dapi.copy()

    # Create a border index for each parent region in regions with an empty list
    borderIndex = {}
    for region in regions:
        if (regions[region]["parent"] not in borderIndex) and (regions[region]["parent"] != 'N/A'):
            borderIndex[regions[region]["parent"]] = []

    blank = np.zeros((y, x, 3), np.uint8)
    for (j, i), area in np.ndenumerate(annoWarp):
        # Draw the colored region on the map image
        if area != 0:
            # Add the point to the parent region's list of points
            try:
                if 'layer' in regions[area]['name'].lower():
                    parent = regions[area]["parent"]
                    area = parent
                blank[j, i] = regions[area]["color"]
                # Add the point to the parent region's list of points
                regions[area]["points"].append((j, i))
            except KeyError:
                pass

    # Create two windows one for the image and one for interactive adjustments
    displayed = np.zeros((y, x, 3), np.uint8)
    cv2.namedWindow('Map', cv2.WINDOW_NORMAL)
    adjustment = np.zeros((500, 500, 3), np.uint8)
    cv2.namedWindow('Adjust', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Adjust', 500, 500)

    # Create a mouse callback to display the region name in the Adjust window
    selectedRegion = None
    brushSize = 5
    drawing = False
    annoBackup = annoWarp.copy()

    def mouseCallback(event, x, y, flags, param):
        '''
        Right click selects the hovered region
        Left click sets the hovered region to the selected region in the annoWarp
        '''
        global selectedRegion, brushSize, drawing, displayed
        if event == cv2.EVENT_MOUSEMOVE:
            # Get the region name at the mouse position
            try:
                if not drawing:
                    region = annoWarp[y, x]
                    if 'layer' in regions[region]['name'].lower():
                        parent = regions[region]["parent"]
                        region = parent

                    regionName = regions[region]["name"]
                    acronym = regions[region]["acronym"]
                    # Display the region name in the Adjust window
                    newAdjustment = adjustment.copy()
                    cv2.putText(newAdjustment, regionName, (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 1)
                    cv2.putText(newAdjustment, acronym, (10, 75),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 1)
                    if selectedRegion != None:
                        # Write the selected region's name and acronym in the Adjust window
                        cv2.putText(newAdjustment, regions[selectedRegion]["name"], (
                            10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 1)
                        cv2.putText(newAdjustment, regions[selectedRegion]["acronym"], (
                            10, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 1)
                    cv2.imshow('Adjust', newAdjustment)
                else:
                    annoWarp[y-brushSize:y+brushSize, x -
                             brushSize:x+brushSize] = selectedRegion
                    # Draw the change in the map image, use brushSize
                    blank[y-brushSize:y+brushSize, x-brushSize:x +
                          brushSize] = regions[selectedRegion]["color"]
                    cv2.addWeighted(blank, 0.3, dapi, 0.5, 0, displayed)
                    cv2.imshow('Map', displayed)
            except:
                # If the mouse is outside the image, display nothing in the Adjust window
                cv2.imshow('Adjust', adjustment)
        elif event == cv2.EVENT_RBUTTONDOWN:
            try:
                region = annoWarp[y, x]
                if 'layer' in regions[region]['name'].lower():
                    parent = regions[region]["parent"]
                    region = parent
                # Set the selected region to the hovered region parent region if not N/A
                selectedRegion = region
                # Draw the selected region in the Adjust window
                newAdjustment = adjustment.copy()
            except IndexError:
                # If the mouse is outside the image, display nothing in the Adjust window
                cv2.imshow('Adjust', adjustment)
        elif event == cv2.EVENT_LBUTTONDOWN:
            try:
                # Untill the mouse is released, draw the selected region in the Adjust window
                if selectedRegion != None:
                    drawing = True
                    annoWarp[y-brushSize:y+brushSize, x -
                             brushSize:x+brushSize] = selectedRegion
                    # Draw the change in the map image, use brushSize
                    blank[y-brushSize:y+brushSize, x-brushSize:x +
                          brushSize] = regions[selectedRegion]["color"]
                    cv2.addWeighted(blank, 0.3, dapi, 0.5, 0, displayed)
                    cv2.imshow('Map', displayed)
            except:
                # If the mouse is outside the image, display nothing in the Adjust window
                cv2.imshow('Adjust', adjustment)
        elif event == cv2.EVENT_LBUTTONUP:
            # Stop drawing the selected region when the mouse is released
            drawing = False

    # Add callback
    cv2.setMouseCallback('Map', mouseCallback)
    cv2.addWeighted(blank, 0.3, dapi, 0.5, 0, displayed)
    cv2.imshow('Map', displayed)

    # Await q key to quit'
    while True:
        key = cv2.waitKey(0)
        if key == ord('q'):
            # Save the annoWarp back to the pkl
            with open(os.path.join(args.input, annoPkl), 'wb') as f:
                pickle.dump(annoWarp, f)
            break
        elif key == ord('z'):
            cv2.namedWindow('Undoing...', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('Undoing...', 300, 10)
            annoWarp = annoBackup.copy()
            blank = np.zeros((y, x, 3), np.uint8)
            for (j, i), area in np.ndenumerate(annoWarp):
                # Draw the colored region on the map image
                if area != 0:
                    # Add the point to the parent region's list of points
                    try:
                        parent = regions[area]["parent"]
                        blank[j, i] = regions[parent]["color"]
                        # Add the point to the parent region's list of points
                        regions[parent]["points"].append((j, i))
                    except KeyError:
                        pass
            cv2.destroyWindow('Undoing...')
            cv2.addWeighted(blank, 0.3, dapi, 0.5, 0, displayed)
            cv2.imshow('Map', displayed)
        elif key == ord('h'):
            # show only the dapi image
            cv2.imshow('Map', dapi)
        elif key == ord('m'):
            # show the map image
            cv2.imshow('Map', displayed)
        # if escape is pressed quit
        elif key == 27:
            end = True
            cv2.destroyAllWindows()
            print('Done!', flush=True)
            break

print('Done!', flush=True)
