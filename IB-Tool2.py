#----------------------------------------------------------------------
# Name:        IB-Tool3
# Purpose:     Toolset for the delineation of settlements on the basis
#              building footprints
#
# Author:      Oliver Harig
#
# Created:     10.05.2021
# Cite:        Oliver Harig (2021). Toolset for the delineation of settlements on the basis building footprints, road network and land use data (v1.0) https://doi.org/10.26084/IOERFDZ-SOFT-001    
# Licence:     MIT License
#              Copyright 2025 Oliver Harig
#
#              Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
#              associated documentation files (the "Software"), to deal in the Software without restriction, including
#              without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#              copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the
#              following conditions:
#
#              The above copyright notice, and this permission notice must be included in all copies or substantial portions of the Software.
#
#              THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
#              LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#              IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
#              WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
#              SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#----------------------------------------------------------------------


#  !/usr/bin/python
#  -*- coding:utf-8 -*-

#  ------ MODULE IMPORTS ------

import arcpy
from arcpy.sa import *
import os
import time
import datetime
import traceback
import sys
import networkx as nx
import numpy as np
import scipy as sp
import statistics
import msvcrt
import re
import json
import psutil
from scipy.sparse.csgraph import minimum_spanning_tree
from scipy.spatial import Delaunay
from scipy.stats.mstats import mquantiles
from operator import itemgetter

# ------ GLOBAL SETTINGS ------

# working folder set to current folder of py-file

Workspace = os.getcwd()
os.chdir(Workspace)

# deactivate ESRI logging for disk space saving
arcpy.SetLogHistory(False)

# import values from IB-Tool2_Config.txt

valuelist = []
with open('IB-Tool2_Config.txt', 'r') as txt:
    data = txt.readlines()
    for row in data:
        string = str(row).replace('\n', '')
        pos = string.find(":")
        valuelist.append(string[pos + 1:])

# set level of logging (LogLevels:'Alert', 'Warning', 'Info', 'Debug')
LogLevel = valuelist[10]

# get spatial reference
sr = arcpy.SpatialReference(int(valuelist[11]))

# get workspace for results
workspace_results = valuelist[12]

# set ESRI environment variables
arcpy.env.workspace = Workspace
arcpy.env.outputCoordinateSystem = sr
arcpy.env.referenceScale = "10000"
arcpy.env.outputCoordinateSystem = sr
arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")
os.chdir(Workspace)

# create folder for temporary files
if arcpy.Exists("Tmp.gdb"):
    arcpy.Delete_management("Tmp.gdb")
arcpy.CreateFileGDB_management(Workspace, "Tmp.gdb")
Geodatabase = Workspace + os.path.sep + "Tmp.gdb"
timedic = {}

# ------ INPUT DATA ------

InputHU = Workspace + os.path.sep + "A_HU.shp"
Strassen = Workspace + os.path.sep + "A_RN.shp"
Partition = Workspace + os.path.sep + "A_PART.shp"
Veg_Layer = Workspace + os.path.sep + "A_AUX.shp"


# ------ HELPER FUNCTIONS ------

def tmp(filename):
    """writes file in temporary folder and return filename"""
    return Workspace + os.path.sep + "Tmp" + os.path.sep + filename


def mem(filename):
    """writes file in RAM-memory and return filename"""
    return r'in_memory' + os.path.sep + filename


def gdb(filename):
    """writes file in geodatabase and return filename"""
    return Geodatabase + os.path.sep + filename


def DelName(DelList):
    """deletes files given as list of files"""
    arcpy.env.overwriteOutput = True
    for j in DelList:
        try:
            arcpy.Delete_management(j)
        except Exception:
            if j is not None:
                Log("Warning", " Could not delete {}".format(j))


def DelField(Filename, Fields):
    """deletes field of given file"""
    try:
        for i in Fields:
            arcpy.DeleteField_management(Filename, i)
    except Exception:
        pass


def TimePrint(T1, T3):
    """logging the total time and the time for the section for debugging"""
    T2 = time.time()
    Ta = int(T2 - T3)
    Tg = int(T2 - T1)
    Log("Info", "Time total: " + str(datetime.timedelta(seconds=Tg)) + " - " + "Section: " + str(
        datetime.timedelta(seconds=Ta)))
    return T2


def TimePrint3(T3, text=""):
    """logging the time for the section for debugging"""
    T2 = time.time()
    Ta = (T2 - T3)
    Tdiff = 0

    if "{}_Ts".format(text) in timedic:
        timedic["{}_Tj".format(text)] = Ta
        Tdiff = timedic["{}_Tj".format(text)] - timedic["{}_Ts".format(text)]
    else:
        timedic["{}_Ts".format(text)] = Ta
    printtext = text + ": " + str(round(Ta, 1)) + ", " + str(round(Tdiff, 2))
    Log("Debug", printtext)
    return T2


def CountPrint(filename):
    """print number of features of given file for debugging"""
    result = arcpy.GetCount_management(filename)
    Anz = int(result.getOutput(0))
    printtext = ("No: " + str(Anz))
    return printtext


def Log(Level='Warning', Text=''):
    """writing log massage to log file and printing it to screen on dependency of log level"""

    def LogWrite(Level, printtext):
        jetztzeit = time.strftime("%H:%M:%S")
        logfile = open('logfile_{}.txt'.format(startzeit), 'a')
        if Level == 'Info':
            pt = (Level + "    " + jetztzeit + " - " + printtext)
        elif Level == 'Alert':
            pt = (Level + "   " + jetztzeit + " - " + printtext)
        elif Level == 'Debug':
            pt = (Level + "   " + jetztzeit + " - " + printtext)
        elif Level == 'Warning':
            pt = (Level + " " + jetztzeit + " - " + printtext)
        logfile.write("\n" + pt)
        logfile.close()
        print (pt)
        return pt

    if LogLevel == 'Alert' and (Level == 'Alert' or Level == 'Info'):
        LogWrite(Level, Text)
    elif LogLevel == 'Warning' and (Level == 'Warning' or Level == 'Alert' or Level == 'Info'):
        LogWrite(Level, Text)
    elif LogLevel == 'Debug' and (Level == 'Debug' or Level == 'Info' or Level == 'Warning' or Level == 'Alert'):
        LogWrite(Level, Text)


def Shp_Area(filename, Fieldname='Shape_Area'):
    """adds shape area field to file"""
    if len(arcpy.ListFields(filename, Fieldname)) == 0:
        arcpy.AddField_management(filename, '{}'.format(Fieldname), "DOUBLE")
    arcpy.management.CalculateField(filename, '{}'.format(Fieldname), "!shape.geodesicArea@SQUAREMETERS!", "PYTHON_9.3",
                                    None)


def Shp_Length(filename):
    """adds shape length field to file"""
    if len(arcpy.ListFields(filename, "Shape_Len")) == 0:
        arcpy.AddField_management(filename, "Shape_Len", "DOUBLE")
    arcpy.management.CalculateField(filename, "Shape_Len", "!shape.geodesicLength@METERS!", "PYTHON_9.3", None)


def Rename_Field(filename, OldFieldName, NewFieldName, Type):
    """renames field of file"""
    arcpy.AddField_management(filename, NewFieldName, Type, '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
    arcpy.management.CalculateField(filename, NewFieldName, "!{}!".format(OldFieldName), "PYTHON_9.3", None)
    arcpy.DeleteField_management(filename, OldFieldName)


def Join_Field(FileToJoin, KeyField1, JoiningFile, KeyField2, JoiningField):
    """joins field of one file to another"""

    if len(arcpy.ListFields(FileToJoin, JoiningField)) > 0:
        pass
    else:
        arcpy.AddField_management(FileToJoin, JoiningField, "DOUBLE")

    JoinList = []
    with arcpy.da.SearchCursor(JoiningFile, [KeyField2, JoiningField]) as cursor17:
        for x in cursor17:
            JoinList.append([x[0], x[1]])
    del cursor17
    JoinDict = dict(JoinList)

    with arcpy.da.UpdateCursor(FileToJoin, [KeyField1, JoiningField]) as cursor18:
        for row in cursor18:
            row[1] = JoinDict[row[0]]
            cursor18.updateRow(row)
    del cursor18


def CheckFileType(inputfile, datatype, geometrytype):
    """
    :param inputfile: File to check
    :param datatype (str): ShapeFile, FeatureClass, FeatureLayer
    :param geometrytype (str):  Polygon, Polyline, Point, Multipoint, MultiPatch

   -  checks whether the file has the required data type and geometry type
    """


    desc = arcpy.Describe(inputfile)
    if datatype != desc.dataType:  # ShapeFile FeatureClass FeatureLayer
        raise TypeError("Data type of {} should be {}, but is {}".format(inputfile, datatype, desc.dataType))
    if geometrytype != desc.shapeType:
        raise TypeError("Geometry type of {} should be {}, but is {}".format(inputfile, geometrytype, desc.shapeType))


def Starter(valuelist):
    """
    :param: list of imported parameters
    :return: MinOverlapBlocks, MinOverlapMST, MinArea, MinBdgCount, MinPatchSize, max_hole_size, max_gap_size, partstart, partend, partlist

    - checks whether all needed files are present
    - coverts valuelist to single variables and return them
    """

    logo = '\n\n' + \
           r'          __/\\\\\\\\\\\__/\\\\\\\\\\\\\__________________/\\\\\\\\\\\\\\\______________________________/\\\\\\____' + '\n' + \
           r'          _\/////\\\///__\/\\\/////////\\\_______________\///////\\\/////______________________________\////\\\____' + '\n' + \
           r'          _____\/\\\_____\/\\\_______\/\\\_____________________\/\\\______________________________________\/\\\____' + '\n' + \
           r'          _____\/\\\_____\/\\\\\\\\\\\\\\___/\\\\\\\\\\\_______\/\\\___________/\\\\\________/\\\\\_______\/\\\____' + '\n' + \
           r'          _____\/\\\_____\/\\\/////////\\\_\///////////________\/\\\_________/\\\///\\\____/\\\///\\\_____\/\\\____' + '\n' + \
           r'          _____\/\\\_____\/\\\_______\/\\\_____________________\/\\\________/\\\__\//\\\__/\\\__\//\\\____\/\\\____' + '\n' + \
           r'          _____\/\\\_____\/\\\_______\/\\\_____________________\/\\\_______\//\\\__/\\\__\//\\\__/\\\_____\/\\\____' + '\n' + \
           r'          __/\\\\\\\\\\\_\/\\\\\\\\\\\\\/______________________\/\\\________\///\\\\\/____\///\\\\\/____/\\\\\\\\\_' + '\n' + \
           r'          _\///////////__\/////////////________________________\///___________\/////________\/////_____\/////////__' + '\n' + \
           r'          ' + '\n' + \
           r'          Author: Oliver Harig' + '\n' '          Licence: Copyright 2021 Oliver Harig' + '\n\n'
    print (logo)
    time.sleep(1)

    if os.path.isfile("A_HU.shp") != True:
        raise Exception("Please name you building footprint shape 'A_HU.shp' an copy it in working folder")
    if os.path.isfile("A_RN.shp") != True:
        raise Exception("Please name you road network shape 'A_RN.shp' and copy it in working folder")
    if os.path.isfile("A_PART.shp") != True:
        raise Exception("Please name you Partition shape 'A_PART.shp' and copy it in working folder")
    if os.path.isfile("A_AUX.shp") != True:
        raise Exception("Please name you Partition shape 'A_AUX.shp' and copy it in working folder")
    if os.path.isfile("IB-Tool2_Config.txt") != True:
        raise Exception("Config file 'IB-Tool2_Config.txt' is not in working folder")

    if len(arcpy.ListFields("A_HU.shp", "NAME")) > 0:
        arcpy.DeleteField_management("A_HU.shp", "NAME")

    if len(arcpy.ListFields("A_HU.shp", "Join_Count")) > 0:
        arcpy.DeleteField_management("A_HU.shp", "Join_Count")

    if len(arcpy.ListFields("A_PART.shp", "NAME")) == 0:
        Log("Alert", "No field 'NAME' in A_PART.shp")


    # Check projection of input files

    sr_i = arcpy.SpatialReference(int(valuelist[11]))
    inputlist = ["A_PART.shp", "A_AUX.shp", "A_HU.shp", "A_RN.shp"]

    for f in inputlist:
        sr_f = arcpy.Describe(f).spatialReference
        if sr_i.name != sr_f.name:
            Log("Alert", "Projection of {} is not {}, but {}!".format(f, sr_i.name, sr_f.name))


    # Convert txt entries to list

    MinOverlapBlocks = int(valuelist[0])
    globfpdenshresld = float(valuelist[1])
    MinArea = float(valuelist[2])
    MinBdgCount = int(valuelist[3])
    MinPatchSize = int(valuelist[4])
    MaxHoleSize = int(valuelist[5])
    MaxGapSize = int(valuelist[6])
    partstart = int(valuelist[7])
    partend = int(valuelist[8])
    partlist = valuelist[9]
    PathCommonWorkspace = valuelist[12]
    DelPartLog = valuelist[13]

    if partlist[0] != "#":
        partlist = list(partlist.split(","))

    return MinOverlapBlocks, globfpdenshresld, MinArea, MinBdgCount, MinPatchSize, MaxHoleSize, MaxGapSize, partstart, partend, partlist, PathCommonWorkspace, DelPartLog


def Polyline2(ArrayOfLines):
    """
    :param ArrayOfLines: array of pairs of points of a line and additional value of length ("x1", "y1", "x2", "y2", "Shape_Len")
    :return: polyline (shape)

    - creates polyline shape of point array with length field
    """
    out_poly = "polyline2.shp"
    arcpy.CreateFeatureclass_management(out_path=Workspace, out_name=out_poly, geometry_type="POLYLINE",
                                        spatial_reference=sr)
    arcpy.AddField_management("polyline2.shp", 'x1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
    arcpy.AddField_management("polyline2.shp", 'y1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
    arcpy.AddField_management("polyline2.shp", 'x2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
    arcpy.AddField_management("polyline2.shp", 'y2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
    arcpy.AddField_management("polyline2.shp", 'Shape_Len', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE',
                              'NON_REQUIRED', '#')
    cursor = arcpy.da.InsertCursor("polyline2.shp", ("SHAPE@", "x1", "y1", "x2", "y2", "Shape_Len"))
    for feature in ArrayOfLines:
        x1, y1 = feature[0]
        x2, y2 = feature[1]
        polyline = arcpy.Polyline(arcpy.Array([arcpy.Point(x1, y1), arcpy.Point(x2, y2)]))
        try:
            if feature[2] is not None:
                Shape_Len = feature[2]
                cursor.insertRow((polyline, x1, y1, x2, y2, Shape_Len))
        except:
            cursor.insertRow((polyline, x1, y1, x2, y2, "0"))
    del cursor
    return "polyline2.shp"

# ------ IB-TOOL-DEFINITIONS ------

class IbTool:

    def __init__(self, workspace):
        self.workspace = workspace


    def PolyMainAngle(self, HU_input):
        """
        :param HU_input: set of polygons (shape)
        :return: minimum bounding rectangle polygons

        - creates a minimum bounding rectangle out of polygons orientated to longest edges
        """

        IbTools5 = IbTool(self.workspace)
        arcpy.env.overwriteOutput = True
        HU_vert = IbTools5.HUtoLineXY(HU_input, "POINT_X;POINT_Y")
        HUDirRect, Area = IbTools5.CalcBoundingRect(HU_vert, HU_input, "shape")
        return HUDirRect


    def HUtoLineXY(self, HU_input, Fields):

        """
        :param HU_input:  set of polygons
        :param Fields: Fields of joining features
        :return: set of polylines

        - helper function for PolyMainAngle
        """

        HU_v = tmp("HU_v.shp")
        HU_vert_join = mem("HU_vert_join")
        HU_vert_start = mem("HU_vert_start")

        arcpy.AddField_management(HU_input, "FID_ORIG")
        arcpy.management.CalculateField(HU_input, "FID_ORIG", "!FID!", "PYTHON_9.3", '')
        arcpy.management.SplitLine(HU_input, "in_memory\HU_vert")
        arcpy.management.FeatureVerticesToPoints("in_memory\HU_vert", HU_vert_start, "START")
        arcpy.management.FeatureVerticesToPoints("in_memory\HU_vert", "in_memory\HU_vert_end", "END")
        arcpy.management.AddXY(HU_vert_start)
        arcpy.management.AddXY("in_memory\HU_vert_end")
        arcpy.management.JoinField("in_memory\HU_vert", "FID", HU_vert_start, "ORIG_FID", Fields)
        arcpy.management.JoinField("in_memory\HU_vert", "FID", "in_memory\HU_vert_end", "ORIG_FID", Fields)
        arcpy.SpatialJoin_analysis("in_memory\HU_vert", HU_input, HU_vert_join)
        arcpy.CopyFeatures_management(HU_vert_join, HU_v)
        Shp_Length(HU_v)

        return HU_v


    def CalcBoundingRect(self, HU_v, HU_input, type):
        """
        :param HU_v: input buildings footprints as polyline-features
        or list like ["POINT_X", "POINT_Y", "POINT_X_1", "POINT_Y_1", "Shape_Len"]
        :param HU_input: original building footprints of selection
        :param type: "shape" = HU_v is polyline, "list" HU_v is list
        :return: minimum bounding rectangle of input HU

        - Creates minimum bounding rectangle of input building footprints
        """

        HUDirRect = tmp("HUDirRect.shp")  # Ausgabe
        LenghtList = []
        AngleList = []
        PointList = []

        def MainAngle(list, maxdiff):
            listsort = sorted(list, key=itemgetter(0))
            groups = [[listsort[0]]]
            for x in listsort[1:]:
                if abs(x[0] - groups[-1][-1][0]) < maxdiff:
                    groups[-1].append(x)
                else:
                    groups.append([x])
            sumlist = []
            for e in groups:
                s = 0
                for j in e:
                    s = s + j[1]
                sumlist.append(s)

            longestgroup = groups[np.argmax(sumlist)]
            s = 0
            g1 = longestgroup[0][0]
            lengthsum = []
            for e in longestgroup:
                if g1 == e[0]:
                    s = s + e[1]
                else:
                    lengthsum.append(s)
                    s = e[1]
                g1 = e[0]
            if len(lengthsum) == 0:
                lengthsum.append(s)
            MainAng = longestgroup[np.argmax(lengthsum)][0]

            return MainAng


        def Polyline(ArrayOfLines):
            """
            :param ArrayOfLines: array of points of a line
            :return: polyline (mem)

            - creates polyline in memory out of point array
            """
            out_poly = mem("polyline")
            features = []
            for feature in ArrayOfLines:
                features.append(
                    arcpy.Polyline(
                        arcpy.Array([arcpy.Point(*coords) for coords in feature]), sr))
            arcpy.CopyFeatures_management(features, out_poly)
            return out_poly


        def NearPoint(x0, y0, x1, y1, x2, y2):
            """
            - Calculates the perpendicular point on a straight line (x0,y0,x1,y1)
            """

            p0 = np.array([x0, y0])
            p1 = np.array([x1, y1])
            p2 = np.array([x2, y2])

            d = np.abs(np.cross(p1 - p0, p0 - p2) / np.linalg.norm(p1 - p0))

            dx = x1 - x0
            dy = y1 - y0
            m = np.sqrt(dx * dx + dy * dy)
            dx /= m
            dy /= m

            l = (dx * (x2 - x0)) + (dy * (y2 - y0))
            x = (dx * l) + x0
            y = (dy * l) + y0

            return d, x, y

        def VectorAngle(xy11, xy12, xy21, xy22):
            """
            INPUTS
            xy11, xy12 , xy21, xy22 = Two point pairs of two straight lines with xy coordinates
            OUTPUT
            Ang = Angle of the straight lines to each other in degrees
            """
            # Sort the points by central point
            List = xy11, xy12, xy21, xy22

            if List.count(List[0]) == 2:  # xy11 is central point
                if xy21 != xy11:
                    xy21b = xy21
                    xy21 = xy22
                    xy22 = xy21b

            else:  # xy12 is central point
                xy11b = xy11
                xy11 = xy12
                xy12 = xy11b
                if xy21 != xy11:
                    xy21b = xy21
                    xy21 = xy22
                    xy22 = xy21b

            # Conversion of point pairs into position vectors
            x1, y1 = xy12[0] - xy11[0], xy12[1] - xy11[1]
            x2, y2 = xy22[0] - xy21[0], xy22[1] - xy21[1]

            Vector1 = np.array([x1, y1])
            Vector2 = np.array([x2, y2])
            dot = np.dot(Vector1, Vector2)
            x_modulus = np.sqrt((Vector1 * Vector1).sum())
            y_modulus = np.sqrt((Vector2 * Vector2).sum())
            cos_angle = dot / x_modulus / y_modulus
            angle = np.arccos(cos_angle)  # angle in rad
            Ang = angle * 360 / 2 / np.pi  # angle in degrees

            if xy11[1] == xy22[1]:  # Direction is calculated
                if Vector1[1] <= 0:
                    Ang = 180 - Ang

            return Ang

        if type == "shape":

            with arcpy.da.SearchCursor(HU_v,
                                       ["POINT_X", "POINT_Y", "POINT_X_1", "POINT_Y_1", "Shape_Len"]) as  cursor12:
                for row in cursor12:
                    X11, Y11, X12, Y12, LENGHTH = row
                    Angle = VectorAngle((X11, Y11), (X12, Y12), (X11, Y11), (X11 + 100, Y11))
                    LenghtList.append(LENGHTH)
                    AngleList.append(Angle)
                    PointList.append([X11, Y11])
            del cursor12

        if type == "list":
            for row in HU_v:
                X11, Y11, X12, Y12, LENGHTH = row
                Angle = VectorAngle((X11, Y11), (X12, Y12), (X11, Y11), (X11 + 100, Y11))
                LenghtList.append(LENGHTH)
                AngleList.append(round(Angle, 1))
                PointList.append([X11, Y11])

        # calculates histogram with four bars

        j = 0
        list = []
        for i in AngleList:
            list.append([i, LenghtList[j]])
            j += 1

        if len(PointList) > 4:

            MainAngle = MainAngle(list, 10)

            X, Ymin = min(PointList, key=lambda t: t[1])
            Xmax, Y = max(PointList, key=lambda t: t[0])
            Xmin, Y = min(PointList, key=lambda t: t[0])

            Py1 = Ymin

            if MainAngle > 90:
                Px1 = Xmax + 10000
            else:
                Px1 = Xmin - 10000

            Px2 = Px1 + 10000 * math.cos(math.radians(MainAngle))
            Py2 = Py1 + 10000 * math.sin(math.radians(MainAngle))

            NearList = []
            for p in PointList:
                d, x, y = NearPoint(Px1, Py1, Px2, Py2, p[0], p[1])
                NearList.append([d, p[0], p[1], x, y])

            A_NEAR_DIST, A_FROM_X, A_FROM_Y, A_NEAR_X, A_NEAR_Y = min(NearList, key=itemgetter(0))
            B_NEAR_DIST, B_FROM_X, B_FROM_Y, B_NEAR_X, B_NEAR_Y = max(NearList, key=itemgetter(0))
            C_NEAR_DIST, C_FROM_X, C_FROM_Y, C_NEAR_X, C_NEAR_Y = min(NearList, key=itemgetter(4))
            D_NEAR_DIST, D_FROM_X, D_FROM_Y, D_NEAR_X, D_NEAR_Y = max(NearList, key=itemgetter(4))

            C2_x = C_NEAR_X + ((C_FROM_X - C_NEAR_X) * B_NEAR_DIST / C_NEAR_DIST)
            C2_y = C_NEAR_Y + ((C_FROM_Y - C_NEAR_Y) * B_NEAR_DIST / C_NEAR_DIST)
            D2_x = D_NEAR_X + ((D_FROM_X - D_NEAR_X) * B_NEAR_DIST / D_NEAR_DIST)
            D2_y = D_NEAR_Y + ((D_FROM_Y - D_NEAR_Y) * B_NEAR_DIST / D_NEAR_DIST)
            D1_x = D_NEAR_X + ((D_FROM_X - D_NEAR_X) * A_NEAR_DIST / D_NEAR_DIST)
            D1_y = D_NEAR_Y + ((D_FROM_Y - D_NEAR_Y) * A_NEAR_DIST / D_NEAR_DIST)
            C1_x = C_NEAR_X + ((C_FROM_X - C_NEAR_X) * A_NEAR_DIST / C_NEAR_DIST)
            C1_y = C_NEAR_Y + ((C_FROM_Y - C_NEAR_Y) * A_NEAR_DIST / C_NEAR_DIST)

            ArrayOfLines = [[[C1_x, C1_y], [C2_x, C2_y]], [[C2_x, C2_y], [D2_x, D2_y]],
                            [[D2_x, D2_y], [D1_x, D1_y, ]], [[D1_x, D1_y], [C1_x, C1_y]]]

            PolyArea = math.sqrt(abs(C1_x - C2_x) ** 2 + abs(C1_y - C2_y) ** 2) * math.sqrt(
                abs(D2_x - C2_x) ** 2 + abs(D2_y - C2_y) ** 2)

            PolyLine = Polyline(ArrayOfLines)
            arcpy.management.FeatureToPolygon(PolyLine, HUDirRect, None, "ATTRIBUTES", None)
            DelName([PolyLine])

            if PolyArea == 0:
                Log("ALert", " FID {} or FID {} in MST_Clustering causes division by zero")
                PolyArea = 1000000000000
            return HUDirRect, PolyArea

        else:
            Log("Warning", "CalcBoundingRect - No output generated")

            return HU_input, None


    def Blocker(self, Strassen, HU_Input, Partition):
        """
        :param Strassen: road network as polyline (shape)
        :param HU_Input: building footprints as polygon (shape)
        :param Partition: part of study area for that city block is calculated (shape)
        :return: city block (shape) = Block_FID.shp

        - create city blocks of partition outline and road network
        """

        # locale variables
        Blocks = tmp("blocks.shp")
        SettlBuffer_Outline = mem("SettlBuffer_Outline")
        Strassen_Intersect = mem("Strassen_Intersect")
        Strassen_Outline = mem("Strassen_Outline")

        Log("Debug", "Blocker Start")
        # create city blocks of partition outline and road network
        arcpy.management.FeatureToLine(Partition, SettlBuffer_Outline, None, "ATTRIBUTES")
        arcpy.analysis.Intersect([Strassen, Partition], Strassen_Intersect, "ONLY_FID", None, "INPUT")
        arcpy.management.Merge([SettlBuffer_Outline, Strassen_Intersect], Strassen_Outline)
        arcpy.FeatureToPolygon_management(Strassen_Outline, Blocks, None, "ATTRIBUTES", None)
        Blocks_FL = arcpy.MakeFeatureLayer_management(Blocks)
        # select blocks with buildings
        HU_Input_FL = arcpy.MakeFeatureLayer_management(HU_Input)
        arcpy.management.SelectLayerByLocation(Blocks_FL, "CONTAINS", HU_Input_FL, None, "NEW_SELECTION", "INVERT")
        # delete empty blocks
        arcpy.DeleteFeatures_management(Blocks_FL)
        arcpy.management.AddField(Blocks, "NAME", "Text", None, None, None, None, "NULLABLE", "NON_REQUIRED", None)
        Expression = '"Block_{}".format(!FID!)'
        arcpy.management.CalculateField(Blocks, "NAME", Expression, "PYTHON_9.3", None)
        arcpy.CopyFeatures_management(Blocks, gdb("blocks"))
        arcpy.CopyFeatures_management(gdb("blocks"), Blocks)
        DelName([HU_Input_FL, Blocks_FL, gdb("blocks"), SettlBuffer_Outline, Strassen_Intersect, Strassen_Outline])
        if Blocks is not None:
            Log("Debug", "Blocker End - blocks {}".format(CountPrint(Blocks)))
        return Blocks

    def InputHU_Filter(self, HU_Input, MinAreaAllBdgs=50, PointDensCellSize=50, PointDensNbh=100, PointDensMin=8.2E-05):
        """
        :param HU_Input: input building footprints(shape)
        :param MinAreaAllBdgs: minimum area of all filtered buildings
        :param MaxAreaNegBdgs: maximum area of buildings from filterneg list that will not deleted
        :param PointDensCellSize: cell size parameter in meters of density function
        :param PointDensNbh: search radius parameter in meters of density function
        :param PointDensMin: threshold value to select residential areas
        :return: filtert buildings (shape)

        - select residential buildings (filterpos list) an create density-based selecting polygon
        - delete neagtive buildings (filterneg list), that are within residential selecting polygon
        - delete small buildings
        """

        # locale variables

        HU_Input_Copy = tmp("HU_Input_Copy.shp")  # tmp
        HU_Input_Copy_Diss = tmp("HU_Input_Copy_Diss.shp")  # tmp
        HU_Filter = "HU_Filter.shp"
        BdgResid = mem("BdgResid")
        BdgResidPoints = mem("BdgResidPoints")
        BdgResidRaster = gdb("BdgResidRaster")
        BdgResidPoints2 = mem("BdgResidPoints2")
        BdgResidPoints3 = mem("BdgResidPoints3")
        BdgResid_Buffer = mem("BdgResid_Buffer")
        Bdg_MinAreaAllBdgs = mem("Bdg_MinAreaAllBdgs")
        HU_FL_neg = mem("HU_FL_neg")
        HU_FL_neg_sel = mem("HU_FL_neg_sel")

        Log("Debug", "Input HU Filter Start")

        def ImportFilter(filename, HU_Input):
            """
            Imports list of buildings from IB-Tool2_Filter.txt
            :param filename: file with filter definition
            :param HU_Input: building footprint input data as polygon shape
            :return: selection strings

            - imports from IB-Tool2_Filter.txt filter values an convert them to two lists
            - creates select strings for later filtering
            """

            CheckFileType(HU_Input, "ShapeFile", "Polygon")

            if os.path.isfile("{}".format(filename)) != True:
                raise Exception("{} is not in working folder".format(filename))

            if len(arcpy.ListFields(HU_Input, "fkt")) > 0:
                fieldname = "fkt"
            elif len(arcpy.ListFields(HU_Input, "funktion")) > 0:
                fieldname = "funktion"

            # converts filter.txt entry to lists
            file = open('{}'.format(filename), 'r')
            l = 0
            listpos = []
            listneg = []
            for row in file:
                if row[0] == "#":  # '#' is key value for dividing positive filter and negative filter
                    l = l + 1
                elif l == 1:
                    listpos.append(("'" + str(row[:10]) + "'"))
                elif l == 2:
                    listneg.append(("'" + str(row[:10]) + "'"))
                elif l == 3:
                    break

            # create select strings for filtering
            index = 0
            filterpos, filterneg = '', ''

            for e in listpos:
                index = index + 1
                if index < len(listpos):
                    addstring = '{} LIKE {} Or '.format(fieldname, e)
                else:
                    addstring = '{} LIKE {}'.format(fieldname, e)
                filterpos = str(filterpos) + str(addstring)

            index = 0
            for e in listneg:
                index = index + 1
                if index < len(listneg):
                    addstring = '{} LIKE {} Or '.format(fieldname, e)
                else:
                    addstring = '{} LIKE {}'.format(fieldname, e)
                filterneg = str(filterneg) + str(addstring)

            return filterpos, filterneg, fieldname

        DelName([HU_Filter])
        HU_FL = arcpy.MakeFeatureLayer_management(HU_Input)

        # delete round shapes
        if len(arcpy.ListFields(HU_Input, "SHP_IDX")) == 0:
            arcpy.AddField_management(HU_Input, "SHP_IDX", "DOUBLE")
        Shp_Area(HU_Input)
        Shp_Length(HU_Input)
        arcpy.CalculateField_management(HU_Input, "SHP_IDX",
                                        '!Shape_Len! /(2 * math.sqrt (4 * math.atan (1)* !Shape_Area! ))',
                                        'PYTHON_9.3', '#')
        HU_Input_FL = arcpy.MakeFeatureLayer_management(HU_Input)
        arcpy.management.SelectLayerByAttribute(HU_Input_FL, "NEW_SELECTION", "SHP_IDX < 1.05")
        arcpy.DeleteFeatures_management(HU_Input_FL)

        # import select strings
        filterpos, filterneg, fieldname = ImportFilter("IB-Tool2_Filter.txt", InputHU)
        # select residential buildings (filterpos list)
        Sel = arcpy.management.SelectLayerByAttribute(HU_FL, "NEW_SELECTION", filterpos)
        arcpy.CopyFeatures_management(Sel, BdgResid)
        # create density raster of residential buildings
        arcpy.management.FeatureToPoint(BdgResid, BdgResidPoints, "INSIDE")
        result = arcpy.GetCount_management(BdgResidPoints)
        Anz = int(result.getOutput(0))
        if Anz > 3:  # Exception handling
            out_raster = arcpy.sa.PointDensity(BdgResidPoints, "NONE", PointDensCellSize,
                                               "Circle {} MAP".format(PointDensNbh), "SQUARE_METERS")
            out_raster.save(BdgResidRaster)
            arcpy.conversion.RasterToPoint(BdgResidRaster, BdgResidPoints2, "Value")
            BdgResidPoints2_FL = arcpy.MakeFeatureLayer_management(BdgResidPoints2)
            # create polygon of density raster
            Sel = arcpy.management.SelectLayerByAttribute(BdgResidPoints2_FL, "NEW_SELECTION",
                                                          "grid_code >= {}".format(PointDensMin))
            arcpy.CopyFeatures_management(Sel, BdgResidPoints3)
            BufferDist = math.sqrt(PointDensCellSize ** 2 + PointDensCellSize ** 2) / 2
            arcpy.analysis.Buffer(BdgResidPoints3, BdgResid_Buffer, "{} Meters".format(BufferDist), "FULL", "ROUND",
                                  "ALL", None, "PLANAR")
            BdgResid_Buffer_FL = arcpy.MakeFeatureLayer_management(BdgResid_Buffer)
            # select buildings from negative list that are larger than :param: MaxAreaNegBdgs
            sel = arcpy.management.SelectLayerByAttribute(HU_FL, "NEW_SELECTION", str(
                filterneg))  # And Shape_Area > {}".format(MaxAreaNegBdgs))
            # delete those buildings, that are not within the redidential building buffer
            arcpy.CopyFeatures_management(sel, HU_FL_neg)
            HU_FL_neg_FL = arcpy.MakeFeatureLayer_management(HU_FL_neg)
            sel = arcpy.management.SelectLayerByLocation(HU_FL_neg_FL, "INTERSECT", BdgResid_Buffer_FL, None,
                                                         "NEW_SELECTION", "INVERT")
            arcpy.CopyFeatures_management(sel, HU_FL_neg_sel)
            HU_FL_neg_sel_FL = arcpy.MakeFeatureLayer_management(HU_FL_neg_sel)
            arcpy.management.SelectLayerByLocation(HU_FL, "INTERSECT", HU_FL_neg_sel_FL, None, "NEW_SELECTION",
                                                   "NOT_INVERT")
            arcpy.DeleteFeatures_management(HU_FL)
            # dissolve buildings an building parts to single feature
            arcpy.management.Dissolve(HU_FL, HU_Input_Copy_Diss, None, None, "SINGLE_PART", "DISSOLVE_LINES")
            HU_Input_Copy_Diss_FL = arcpy.MakeFeatureLayer_management(HU_Input_Copy_Diss)
            Shp_Area(HU_Input_Copy_Diss_FL)
            Shp_Area(HU_FL)
            # delete features smaller than :param: MaxAreaAllBdgs
            selectstring = "Shape_Area < {}".format(str(MinAreaAllBdgs))
            Sel = arcpy.management.SelectLayerByAttribute(HU_Input_Copy_Diss_FL, "NEW_SELECTION", selectstring)
            arcpy.CopyFeatures_management(Sel, Bdg_MinAreaAllBdgs)
            Bdg_MinAreaAllBdgs_FL = arcpy.MakeFeatureLayer_management(Bdg_MinAreaAllBdgs)
            arcpy.management.SelectLayerByLocation(HU_FL, "INTERSECT", Bdg_MinAreaAllBdgs_FL, None,
                                                   "NEW_SELECTION", "NOT_INVERT")
            arcpy.DeleteFeatures_management(HU_FL)
            selectstring = "Shape_Area < {}".format(35)
            arcpy.management.SelectLayerByAttribute(HU_FL, "NEW_SELECTION", selectstring)
            arcpy.DeleteFeatures_management(HU_FL)
            arcpy.management.Dissolve(HU_FL, HU_Input_Copy_Diss, None, None, "SINGLE_PART", "DISSOLVE_LINES")

            arcpy.CopyFeatures_management(HU_Input_Copy_Diss, HU_Filter)
            DelName([HU_Input_Copy, HU_Input_Copy_Diss, HU_Input_Copy_Diss_FL, sel, HU_FL_neg_FL, HU_FL_neg_sel_FL])
            if HU_Filter is not None:
                Log("Debug", "Input HU Filter finish - HU_Filter {}".format(CountPrint(HU_Filter)))
            return HU_Filter
        else:
            Log("Warning", "No buildings selected by InputHU_Filter")
            return None

    def FootprintDensity(self, HU_Input, Bloecke, footprintdensitythreshold):
        """
        :param HU_Input:
        :param Bloecke:
        :param footprintdensitythreshold:
        :return: City blocks and related buildings below given footprintdensitythreshold

        - calculates Overlap ratio of sum of building footprints area to area of city block for each block
        - returns buildings and city blocks below footprintdensitythreshold
        """

        # locale variables
        HU_input_SP = mem("HU_input_SP")
        HU_Rectangle = mem("HU_Rectangle")
        HU_Rect_Buff = mem("HU_Rect_Buff")
        HU_Bloeck_Merge = tmp("HU_Bloeck_Merge.shp")
        #  HUInput_red = tmp("HUInput_red.shp")
        HU_Bloeck_Merge_Join = tmp("Bloeck_Merge_Join.shp")
        Blocks_red = tmp("Blocksred_glob.shp")
        HU_Bloeck_Merge_Join_Dissolve = tmp("Bloeck_Merge_Join_Dissolve.shp")

        Log("Debug", "FootprintDensity Start")
        # order buildings to the blocks
        MergeList = arcpy.ListFeatureClasses('Block_*')
        DelName(MergeList)
        arcpy.management.MultipartToSinglepart(HU_Input, HU_input_SP)
        arcpy.analysis.Split(HU_input_SP, Bloecke, "NAME", self.workspace, None)
        MergeList = arcpy.ListFeatureClasses('Block_*')
        arcpy.management.Merge(MergeList, HU_Bloeck_Merge)
        DelName(MergeList)
        arcpy.analysis.SpatialJoin(HU_Bloeck_Merge, Bloecke, HU_Bloeck_Merge_Join, "JOIN_ONE_TO_ONE", "KEEP_ALL", None,
                                   "WITHIN", None, None)
        arcpy.management.Dissolve(HU_Bloeck_Merge_Join, HU_Bloeck_Merge_Join_Dissolve, "NAME", None, "MULTI_PART",
                                  "DISSOLVE_LINES")
        # calculate area values of building footprints and blocks
        arcpy.AddField_management(HU_Bloeck_Merge_Join_Dissolve, "AREA_BLK_M", "DOUBLE")
        arcpy.AddField_management(Bloecke, "SHAPE_AREA", "DOUBLE")
        arcpy.management.CalculateField(HU_Bloeck_Merge_Join_Dissolve, "AREA_BLK_M", "!shape.geodesicArea@SQUAREMETERS!",
                                        "PYTHON_9.3", None)
        arcpy.management.CalculateField(Bloecke, "SHAPE_AREA", "!shape.geodesicArea@SQUAREMETERS!", "PYTHON_9.3", None)
        arcpy.management.JoinField(Bloecke, "NAME", HU_Bloeck_Merge_Join_Dissolve, "NAME", "AREA_BLK_M")
        arcpy.AddField_management(Bloecke, "OVERLAP", "DOUBLE")
        # calculate overlap
        arcpy.management.CalculateField(Bloecke, "OVERLAP", "!AREA_BLK_M! / !SHAPE_AREA! * 100", "PYTHON_9.3", None)
        # select buildings and blocks below footprintdensitythreshold an return them
        arcpy.MakeFeatureLayer_management(Bloecke, "Blocks_FL")
        Overlap = "OVERLAP > {}".format(footprintdensitythreshold)
        NewSelection = arcpy.management.SelectLayerByAttribute("Blocks_FL", "NEW_SELECTION", Overlap)
        arcpy.CopyFeatures_management(NewSelection, Blocks_red)

        DelName([HU_input_SP, HU_Rectangle, HU_Rect_Buff, HU_Bloeck_Merge, HU_Bloeck_Merge_Join, "Blocks_FL", \
                 NewSelection])
        if Blocks_red is not None:
            Log("Debug", "Building coverage - Blocks_red {} ".format(CountPrint(Blocks_red)))

        return Blocks_red


    def FootprintDensity_blockwise(self, HU_Input, Bloecke, share, Buffer=18):

        """
        :param HU_Input:
        :param Bloecke:
        :param footprintdensitythreshold:
        :return: City blocks and related buildings below given footprintdensitythreshold

        - calculates Overlap ratio of sum of building footprints area to area of city block for each block
        - returns buildings and city blocks below footprintdensitythreshold
        """

        # locale variables

        HU_input_SP = mem("HU_input_SP")
        HU_Rectangle = mem("HU_Rectangle")
        HU_Rect_Buff = mem("HU_Rect_Buff")
        SelBlock = tmp("SelBlock.shp")
        Bloeck_Merge = tmp("Bloeck_Merge.shp")
        HUInput_red = tmp("HUInput_red.shp")
        Bloeck_Merge_Join = tmp("Block_Merge_Join.shp")
        Blocks_red2 = tmp("Blocks_red2.shp")

        MergeList = arcpy.ListFeatureClasses('BlockClip_*')
        DelName(MergeList)
        arcpy.AddField_management(Bloecke, "SHAPE_AREA", "DOUBLE")
        arcpy.management.CalculateField(Bloecke, "SHAPE_AREA", "!shape.geodesicArea@SQUAREMETERS!", "PYTHON_9.3", None)
        arcpy.management.MultipartToSinglepart(HU_Input, HU_input_SP)
        arcpy.management.MinimumBoundingGeometry(HU_input_SP, HU_Rectangle, "RECTANGLE_BY_AREA", "NONE", None,
                                                 "NO_MBG_FIELDS")
        arcpy.analysis.Buffer(HU_Rectangle, HU_Rect_Buff, "{} Meters".format(Buffer), "FULL", "ROUND", "ALL", None,
                              "GEODESIC")
        Bloecke_FL = arcpy.MakeFeatureLayer_management(Bloecke)
        HU_Rect_Buff_FL = arcpy.MakeFeatureLayer_management(HU_Rect_Buff)
        with arcpy.da.SearchCursor(Bloecke, ["FID"]) as cursor16:
            for x in cursor16:
                BlockClip = ("BlockClip_{}.shp".format(x[0]))
                whereclause = "FID = {}".format(x[0])
                Sel = arcpy.management.SelectLayerByAttribute(Bloecke_FL, "NEW_SELECTION", whereclause)
                arcpy.CopyFeatures_management(Sel, SelBlock)
                SelBlock_FL = arcpy.MakeFeatureLayer_management(SelBlock)
                arcpy.analysis.Clip(HU_Rect_Buff_FL, SelBlock_FL, BlockClip, None)
                arcpy.AddField_management(BlockClip, "NAME", "TEXT")
                Exp = '"BLK_{}_o"'.format(x[0])
                arcpy.management.CalculateField(BlockClip, "NAME", Exp, "PYTHON_9.3")
        del cursor16
        MergeList = arcpy.ListFeatureClasses('BlockClip_*')
        arcpy.management.Merge(MergeList, Bloeck_Merge)
        DelName(MergeList)

        arcpy.AddField_management(Bloeck_Merge, "AREA_BLK_M", "DOUBLE")
        arcpy.management.CalculateField(Bloeck_Merge, "AREA_BLK_M", "!shape.geodesicArea@SQUAREMETERS!", "PYTHON_9.3",
                                        None)
        Join_Field(Bloecke, "NAME", Bloeck_Merge, "NAME", "AREA_BLK_M")
        arcpy.AddField_management(Bloecke, "OVERLAP", "DOUBLE")
        arcpy.management.CalculateField(Bloecke, "OVERLAP", "!AREA_BLK_M! / !SHAPE_AREA! * 100", "PYTHON_9.3", None)
        arcpy.MakeFeatureLayer_management(Bloecke, "Blocks_FL")
        Overlap = "OVERLAP < {}".format(share)
        NewSelection = arcpy.management.SelectLayerByAttribute("Blocks_FL", "NEW_SELECTION", Overlap)
        arcpy.CopyFeatures_management(NewSelection, Blocks_red2)
        arcpy.MakeFeatureLayer_management(HU_Input, "InputHU_FL")
        arcpy.MakeFeatureLayer_management(Blocks_red2, "Blocks_red_FL")
        NewSelection = arcpy.management.SelectLayerByLocation("InputHU_FL", "INTERSECT", "Blocks_red_FL", None,
                                                              "NEW_SELECTION", "NOT_INVERT")
        arcpy.CopyFeatures_management(NewSelection, HUInput_red)
        DelName([HU_input_SP, HU_Rectangle, HU_Rect_Buff, Bloeck_Merge, Bloeck_Merge_Join, "InputHU_FL",
                 "Blocks_red_FL", "Blocks_FL", SelBlock_FL, Bloecke_FL, HU_Rect_Buff_FL, NewSelection, Sel])

        return Blocks_red2, HUInput_red


    def CalcFootprintDensity(self, InputBdg, InputStrNetwork, Buffer=100, GlobalThreshold=18, Ext='local',
                             MinBdgCount=20, Partition=''):
        """
        :param InputBdg: polygon shape with building footprints
        :param InputStrNetwork: polyline shape with road network
        :param Buffer: Buffer distance to determine dense settlement areas
        :param GlobalThreshold: fall back value of GlobelThreshold, if there can not be calculated a local threshold
        :param Ext: Extend of area to calculate (values: local or global)
        :param Partition: partition of whole study area is needed, if :param Ext is set to 'global'
        :return: Global overlap value in percent

        - Calculates the degree of overlap of the given building footprints on the city blocks constructed of the
        given road network
        """

        SelHU = tmp("SelHU2.shp")
        SelStrassen = tmp("SelStrassen2.shp")
        SelPart = mem("SelPart2")
        Merge_Dummy8 = "Merge_Dummy8.shp"
        Inner_Blocks = tmp("Inner_Blocks.shp")
        Blocks_inside = mem("Blocks_inside")
        Blocks_join = mem("Blocks_join")
        SelBdg = mem("SelBdg")
        Log("Debug", "Building coverage Start")

        DelName([Merge_Dummy8])
        arcpy.management.CreateFeatureclass(Workspace, Merge_Dummy8, "POLYGON", None, "DISABLED", "DISABLED", None,
                                            None, 0, 0, 0)

        def SelectBlock(InputStrNetwork, InputBdg, Buffer):

            InputBdg_Buff = mem("InputBdg_Buff")
            InputStrNetwork_Poly = tmp("InputBdg_Buff_Poly.shp")  # mem
            Inner_Blocks = tmp("Inner_Blocks2.shp")
            InputBdg_Buff_Diss = mem("InputBdg_Buff_Diss")
            InputBdg_Buff_Line = tmp("InputBdg_Buff_Line.shp")  # mem

            arcpy.FeatureToPolygon_management(InputStrNetwork, InputStrNetwork_Poly)
            arcpy.analysis.Buffer(InputBdg, InputBdg_Buff, "{} Meters".format(Buffer), "FULL", "ROUND", "ALL", None,
                                  "GEODESIC")
            arcpy.Dissolve_management(InputBdg_Buff, InputBdg_Buff_Diss)
            arcpy.FeatureToLine_management(InputBdg_Buff_Diss, InputBdg_Buff_Line)
            InputBdg_Buff_Line_FL = arcpy.MakeFeatureLayer_management(InputBdg_Buff_Line)
            InputStrNetwork_Poly_FL = arcpy.MakeFeatureLayer_management(InputStrNetwork_Poly)
            arcpy.management.SelectLayerByLocation(InputStrNetwork_Poly_FL, "INTERSECT", InputBdg_Buff_Line_FL, None,
                                                   "NEW_SELECTION", "INVERT")
            InputBdg_FL = arcpy.MakeFeatureLayer_management(InputBdg)
            Sel = arcpy.management.SelectLayerByLocation(InputStrNetwork_Poly_FL, "INTERSECT", InputBdg_FL, None,
                                                         "SUBSET_SELECTION")

            arcpy.CopyFeatures_management(Sel, Blocks_inside)
            arcpy.analysis.SpatialJoin(Blocks_inside, InputBdg_FL, Blocks_join,
                                       "JOIN_ONE_TO_ONE", "KEEP_ALL", None, "INTERSECT", None, '')
            Blocks_join_FL = arcpy.MakeFeatureLayer_management(Blocks_join)
            Sel = arcpy.management.SelectLayerByAttribute(Blocks_join_FL, "NEW_SELECTION",
                                                          "Join_Count > {} ".format(MinBdgCount))
            arcpy.CopyFeatures_management(Sel, Inner_Blocks)
            #DelName([Sel, InputBdg_Buff, InputBdg_Buff_Diss, InputBdg_Buff_Line, InputBdg_Buff_Line_FL,
             #        InputStrNetwork_Poly_FL, InputBdg_FL, Blocks_join_FL])
            return Inner_Blocks

        if Ext == "global":

            with arcpy.da.SearchCursor(Partition, ["NAME"]) as cursor23:
                for x in cursor23:
                    Partition_FL = arcpy.MakeFeatureLayer_management(Partition)
                    Strassen_FL = arcpy.MakeFeatureLayer_management(InputStrNetwork)
                    InputHU_FL = arcpy.MakeFeatureLayer_management(InputBdg)

                    Part_Name = x[0]
                    whereclause = '"NAME" = \'%s\'' % (Part_Name)
                    Sel = arcpy.management.SelectLayerByAttribute(Partition_FL, "NEW_SELECTION", whereclause)
                    arcpy.CopyFeatures_management(Sel, SelPart)
                    SelPart_FL = arcpy.MakeFeatureLayer_management(SelPart)

                    Sel = arcpy.management.SelectLayerByLocation(InputHU_FL, "INTERSECT", SelPart_FL)
                    arcpy.CopyFeatures_management(Sel, SelHU)
                    Sel = arcpy.management.SelectLayerByLocation(Strassen_FL, "INTERSECT", SelPart_FL)
                    arcpy.CopyFeatures_management(Sel, SelStrassen)
                    Inner_BlocksPart = SelectBlock(SelStrassen, SelHU, Buffer)
                    arcpy.Merge_management([Inner_BlocksPart, Merge_Dummy8], Inner_Blocks)
                    arcpy.management.Delete(Merge_Dummy8)
                    arcpy.CopyFeatures_management(Inner_Blocks, Merge_Dummy8)
                del cursor23
            #DelName([Sel, SelHU, SelHU, SelStrassen, SelPart, SelPart_FL, Partition_FL, Strassen_FL, InputHU_FL])

        elif Ext == 'local':
            Inner_Blocks = SelectBlock(InputStrNetwork, InputBdg, Buffer)

        arcpy.management.AddField(Inner_Blocks, "NAME", "Text", None, None, None, None, "NULLABLE", "NON_REQUIRED",
                                  None)
        Expression = '"Block_{}".format(!FID!)'
        arcpy.management.CalculateField(Inner_Blocks, "NAME", Expression, "PYTHON_9.3", None)

        result = arcpy.GetCount_management(Inner_Blocks)
        count = int(result.getOutput(0))
        Log("Debug", "InnerBlocks: {}".format(count))
        if count > 5:
            Inner_Blocks_FL = arcpy.MakeFeatureLayer_management(Inner_Blocks)
            InputBdg_FL = arcpy.MakeFeatureLayer_management(InputBdg)
            Sel = arcpy.management.SelectLayerByLocation(InputBdg_FL, "INTERSECT", Inner_Blocks_FL)
            arcpy.CopyFeatures_management(Sel, SelBdg)
            print (CountPrint(SelBdg))
            Blocks_red = IbTool.FootprintDensity(self, SelBdg, Inner_Blocks, 0)
            sum = 0
            with arcpy.da.SearchCursor(Blocks_red, ["OVERLAP"]) as cursor22:
                for x in cursor22:
                    sum += x[0]
            del cursor22
            DelName([Inner_Blocks_FL, InputBdg_FL, SelBdg, Sel])
            globfpdenshresld = sum / count
        else:
            globfpdenshresld = GlobalThreshold

        DelName([Merge_Dummy8])
        return globfpdenshresld


    def MST(self, InputBdg, Strassen, Part_Name, road_length=50):
        """
        :param InputBdg:
        :param Strassen:
        :param Part_Name:
        :param road_length:
        :return: MST (Shape file)

        - minimum spanning tree (MST) is calculated from buildings 
        - edges of the graph are weighted by the distance from building edge to building edge
        -  all edges of the graph are deleted, which roads cross longer than 50 meters
        """

        Log("Debug", "MST start")

        def Uniq(input):
            """
            :param input: list of string or integer
            :return: list

            - filters a list so that each element occurs only once
            """
            output = []
            for x in input:
                if x not in output:
                    output.append(x)
            return output

        def NodesDetect(InputStrNetz, Count):
            """
            INPUTS
            InputStrNetz            = entire road network to be processed
            Count                   = number of road sections at the junction

            OUTPUT
            nodes                   = knots as point feature
            
            - 
            """

            # Local variables
            InputStrNetz_Vertices = mem("InputStrNetz_Vertices")
            InputStrNetz_Multi = mem("InputStrNetz_Multi")
            InputStrNetz_Vertices_SpatialJoin = mem("InputStrNetz_Vertices_SpatialJoin")
            InputStrNetz_Vertices_SpatialJoin_Diss = mem("InputStrNetz_Vertices_SpatialJoin_Diss")

            # Identify nodes
            arcpy.FeatureVerticesToPoints_management(InputStrNetz, InputStrNetz_Vertices, "BOTH_ENDS")
            arcpy.AddXY_management(InputStrNetz_Vertices)

            # Attach attribute to node
            arcpy.management.MultipartToSinglepart(InputStrNetz, InputStrNetz_Multi)
            arcpy.analysis.SpatialJoin(InputStrNetz_Vertices, InputStrNetz_Multi, InputStrNetz_Vertices_SpatialJoin,
                                       "JOIN_ONE_TO_ONE")
            arcpy.Dissolve_management(InputStrNetz_Vertices_SpatialJoin, InputStrNetz_Vertices_SpatialJoin_Diss,
                                      "Join_Count;POINT_X;POINT_Y", "", "SINGLE_PART", "DISSOLVE_LINES")
            InputStrNetz_Vertices_SpatialJoin_Diss_FL = arcpy.MakeFeatureLayer_management(
                InputStrNetz_Vertices_SpatialJoin_Diss)

            # Output all nodes
            if Count == 0:
                nodes = mem("Knots_All")
                arcpy.CopyFeatures_management(InputStrNetz_Vertices_SpatialJoin_Diss, nodes)
            else:
                # Select and output nodes which match count
                Expression = "Join_Count = {}".format(Count)
                Selection = arcpy.SelectLayerByAttribute_management(InputStrNetz_Vertices_SpatialJoin_Diss_FL,
                                                                    "NEW_SELECTION", Expression)
                nodes = mem("Knots_{}".format(Count))
                arcpy.CopyFeatures_management(Selection, nodes)

            DelName([InputStrNetz_Vertices, InputStrNetz_Multi, InputStrNetz_Vertices_SpatialJoin,
                     InputStrNetz_Vertices_SpatialJoin_Diss, InputStrNetz_Vertices_SpatialJoin_Diss_FL, Selection])
            return nodes

     
        # Local variables
        arcpy.env.overwriteOutput = True
        i = Part_Name
        MST = "lines_{}.shp".format(i)
        point_input = "point_input_{}.shp".format(i)
        InputBdgJoin = "InputBdgJoin_{}.shp".format(i)
        InputBdgJoinPoints = "InputBdgJoinPoints_{}.shp".format(i)
        in_table = "in_table_{}.dbf".format(i)
        DelaunayLines = mem("DelaunayLines_{}".format(i))  # mem
        SelectionDelaunayLines = "SelectionDelaunayLines.shp"  # mem
        Strassen_Copy = tmp("Strassen_Copy.shp")
        InputBdgMBG = mem("InputBdgMBG")
        SelectionDelaunayLinesJoin = mem("SelectionDelaunayLinesJoin")
        SelectionDelaunayLinesJoinSort = mem("SelectionDelaunayLinesJoinSort")

        arcpy.Delete_management(point_input)
        arcpy.Delete_management(MST)
        arcpy.CopyFeatures_management(Strassen, Strassen_Copy)

        h_table = arcpy.CreateTable_management("in_memory", "h_table")
        arcpy.AddField_management(h_table, 'x1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
        arcpy.AddField_management(h_table, 'y1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
        arcpy.AddField_management(h_table, 'x2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
        arcpy.AddField_management(h_table, 'y2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
        arcpy.AddField_management(h_table, 'DIST', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')

        point_table = arcpy.CreateTable_management("in_memory", "point_table")
        arcpy.AddField_management(point_table, 'x1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
        arcpy.AddField_management(point_table, 'y1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
        arcpy.AddField_management(point_table, 'x2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')
        arcpy.AddField_management(point_table, 'y2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED', '#')

        Delaunay_point_table = arcpy.CreateTable_management("in_memory", "Delaunay_point_table")
        arcpy.AddField_management(Delaunay_point_table, 'EDGE', 'TEXT', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED',
                                  '#')
        arcpy.AddField_management(Delaunay_point_table, 'x1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED',
                                  '#')
        arcpy.AddField_management(Delaunay_point_table, 'y1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED',
                                  '#')
        arcpy.AddField_management(Delaunay_point_table, 'x2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED',
                                  '#')
        arcpy.AddField_management(Delaunay_point_table, 'y2', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED',
                                  '#')

        Graph_Edge_Weight_Table = arcpy.CreateTable_management("in_memory", "Graph_Edge_Weight_Table")
        arcpy.AddField_management(Graph_Edge_Weight_Table, 'z1', 'TEXT', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED',
                                  '#')
        arcpy.AddField_management(Graph_Edge_Weight_Table, 'z2', 'TEXT', '#', '#', '#', '#', 'NULLABLE', 'NON_REQUIRED',
                                  '#')
        arcpy.AddField_management(Graph_Edge_Weight_Table, 'x1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE',
                                  'NON_REQUIRED', '#')
        arcpy.AddField_management(Graph_Edge_Weight_Table, 'w', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE',
                                  'NON_REQUIRED', '#')

        ListOpPointsAndNodes_Tbl = arcpy.CreateTable_management("in_memory", "ListOpPointsAndNodes_Tbl")
        arcpy.AddField_management(ListOpPointsAndNodes_Tbl, 'x1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE',
                                  'NON_REQUIRED', '#')
        arcpy.AddField_management(ListOpPointsAndNodes_Tbl, 'y1', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE',
                                  'NON_REQUIRED', '#')
        arcpy.AddField_management(ListOpPointsAndNodes_Tbl, 'node', 'DOUBLE', '#', '#', '#', '#', 'NULLABLE',
                                  'NON_REQUIRED', '#')

        e = []

        arcpy.management.FeatureToPoint(InputBdg, point_input, "INSIDE")
        arcpy.AddXY_management(point_input)

        arcpy.TableToTable_conversion(point_input, self.workspace, in_table)
        with arcpy.da.SearchCursor(in_table, ["POINT_X", "POINT_Y"]) as cursor3:
            for i in cursor3:
                x = cursor3[0]
                y = cursor3[1]
                e.append([x, y])
        del cursor3
        points = np.array(e)
        nr_of_points = len(points)
        list_of_points = []

        for x in range(0, nr_of_points):
            o = [0, 0]
            list_of_points.append(o)

        #  tri = Delaunay(points, qhull_options="QJ Pp")
        #  Qhull option QJ, Qhull does not guarantee that each input point appears as a vertex in the Delaunay triangulation
        tri = Delaunay(points)

        ListOpPointsAndNodes = []
        G = nx.Graph()
        G2 = nx.Graph()
        G3 = nx.Graph()
        DelaunayList = []

        # Transfer of the edges of the Delaunay triangulation into a table

        for x in range(len(tri.simplices)):  # tri.simplices contain three nodes each
            list_of_points[tri.simplices[x, 0]] = points[
                tri.simplices[x, 0]].tolist()  # coordinates (xy) of the first node
            list_of_points[tri.simplices[x, 1]] = points[tri.simplices[x, 1]].tolist()
            list_of_points[tri.simplices[x, 2]] = points[tri.simplices[x, 2]].tolist()

            x0, y0 = points[tri.simplices[x, 0]]
            x1, y1 = points[tri.simplices[x, 1]]
            x2, y2 = points[tri.simplices[x, 2]]

            if int(tri.simplices[x, 0]) < int(tri.simplices[x, 1]):  # arrange the node pairs
                e1 = [tri.simplices[x, 0], tri.simplices[x, 1]]
                DelaunayList.append([str(e1), x0, y0, x1, y1])

            else:
                e1 = [tri.simplices[x, 1], tri.simplices[x, 0]]
                DelaunayList.append([str(e1), x1, y1, x0, y0])

            if int(tri.simplices[x, 0]) < int(tri.simplices[x, 2]):
                e2 = [tri.simplices[x, 0], tri.simplices[x, 2]]
                DelaunayList.append([str(e2), x0, y0, x2, y2])
            else:
                e2 = [tri.simplices[x, 2], tri.simplices[x, 0]]
                DelaunayList.append([str(e2), x2, y2, x0, y0])

            if int(tri.simplices[x, 1]) < int(tri.simplices[x, 2]):
                e3 = [tri.simplices[x, 1], tri.simplices[x, 2]]
                DelaunayList.append([str(e3), x1, y1, x2, y2])
            else:
                e3 = [tri.simplices[x, 2], tri.simplices[x, 1]]
                DelaunayList.append([str(e3), x2, y2, x1, y1])

            ListOpPointsAndNodes.append([x0, y0, int(tri.simplices[x, 0])])
            ListOpPointsAndNodes.append([x1, y1, int(tri.simplices[x, 1])])
            ListOpPointsAndNodes.append([x2, y2, int(tri.simplices[x, 2])])

        a = Uniq(ListOpPointsAndNodes)
        ListOpPointsAndNodes = a

        a = Uniq(DelaunayList)
        DelaunayList = a

        with arcpy.da.InsertCursor(Delaunay_point_table, ["EDGE", "x1", "y1", "x2", "y2"]) as cursor4:
            for j in range(len(DelaunayList)):
                cursor4.insertRow(DelaunayList[j])
        del cursor4

        with arcpy.da.InsertCursor(ListOpPointsAndNodes_Tbl, ["x1", "y1", "node"]) as cursor6:
            for p in ListOpPointsAndNodes:
                insert_array = [p[0], p[1], p[2]]
                cursor6.insertRow(insert_array)
        del cursor6

        # Join the node to the building

        arcpy.JoinField_management(point_input, "POINT_X", ListOpPointsAndNodes_Tbl, "x1", "node")
        InputBdg_FL = arcpy.MakeFeatureLayer_management(InputBdg)
        point_input_FL = arcpy.MakeFeatureLayer_management(point_input)
        arcpy.analysis.SpatialJoin(InputBdg_FL, point_input_FL, InputBdgJoin, "JOIN_ONE_TO_ONE", "KEEP_COMMON", "#",
                                   "INTERSECT", None, None)
        arcpy.FeatureVerticesToPoints_management(InputBdgJoin, InputBdgJoinPoints, "ALL")
        arcpy.AddXY_management(InputBdgJoinPoints)

        # Calculation of the distance between the two nodes
        ListOfNodes = []
        SubList = []
        h2 = 0
        l = 0
        result = arcpy.GetCount_management(InputBdgJoinPoints)
        count = int(result.getOutput(0))

        with arcpy.da.SearchCursor(InputBdgJoinPoints, ["POINT_X", "POINT_Y", "node"]) as cursor8:
            for r in cursor8:
                l = l + 1
                h1 = r[2]

                if (h2 != h1) or (l == count):
                    ListOfNodes.append([h2, SubList])

                    SubList = []
                    h2 = h1

                else:
                    SubList.append([r[0], r[1]])
        del cursor8
        DictListOfNodes = dict(ListOfNodes)

        arcpy.XYToLine_management(Delaunay_point_table, DelaunayLines, "x1", "y1", "x2", "y2", "GEODESIC", "EDGE", sr)

        DelaunayLines_FL = arcpy.MakeFeatureLayer_management(DelaunayLines)

        # Delating streets shorter than road_length
        Shp_Length(Strassen_Copy)
        Strassen_FL = arcpy.MakeFeatureLayer_management(Strassen_Copy)

        Knots_1 = NodesDetect(Strassen_Copy, 1)
        Knots_1_FL = arcpy.MakeFeatureLayer_management(Knots_1)
        arcpy.SelectLayerByLocation_management(Strassen_FL, "INTERSECT", Knots_1_FL, "",
                                               "NEW_SELECTION", "NOT_INVERT")
        whereclause = "Shape_Len > {}".format(road_length)
        arcpy.management.SelectLayerByAttribute(Strassen_FL, "REMOVE_FROM_SELECTION", whereclause)
        arcpy.DeleteFeatures_management(Strassen_FL)

        Selection = arcpy.SelectLayerByLocation_management(DelaunayLines_FL, "INTERSECT", Strassen_FL, "",
                                                           "NEW_SELECTION", "INVERT")
        arcpy.CopyFeatures_management(Selection, SelectionDelaunayLines)

        # Calculation of the distance between the two nodes
        with arcpy.da.SearchCursor(SelectionDelaunayLines, ["x1", "y1", "x2", "y2", "EDGE"]) as cursor5:
            for z in cursor5:
                string1 = str(z[4])
                string2 = string1.replace("[", "")
                string = string2.replace("]", "")
                node1, node2 = string.split(",", 1)

                # Calculation of shortest distance

                x1, y1, x2, y2 = z[0], z[1], z[2], z[3]

                try:
                    XA = DictListOfNodes[int(node1)]
                    XB = DictListOfNodes[int(node2)]

                    # Calculation of the distance between the two nodes
                    y = sp.spatial.distance.cdist(XA, XB, metric='euclidean', p=2, V=None, VI=None, w=None)
                    w = y.min()
                    if w < 1:
                        w = 1

                    G.add_edge(int(node1), int(node2), weight=w)
                    with arcpy.da.InsertCursor(Graph_Edge_Weight_Table, ["z1", "z2", "x1", "w"]) as cursor9:
                        cursor9.insertRow([node1, node2, x1, w])
                    del cursor9

                except:
                    if InputBdgJoinPoints is not None and node1 is not None and node2 is not None:
                        Log('Warning', 'Building skipped while creating the MST. Check input buildings and {} at node {} and node {} for topology error (overlaping polygons).'.format(
                            InputBdgJoinPoints, node1, node2))

        Shp_Area(InputBdg)
        Rename_Field(InputBdg, "Shape_Area", "Area", "DOUBLE")
        arcpy.management.MinimumBoundingGeometry(InputBdg, InputBdgMBG, "RECTANGLE_BY_AREA", "NONE", None, "MBG_FIELDS")
        arcpy.management.AddJoin(point_input_FL, "ORIG_FID", InputBdgMBG, "ORIG_FID", "KEEP_ALL")

        arcpy.analysis.SpatialJoin(SelectionDelaunayLines, point_input_FL, SelectionDelaunayLinesJoin,
                                   "JOIN_ONE_TO_MANY", "KEEP_ALL", None, "INTERSECT", None, '')
        arcpy.management.Sort(SelectionDelaunayLinesJoin, SelectionDelaunayLinesJoinSort, "EDGE ASCENDING", "UR")

        EDGE2 = 0
        with arcpy.da.SearchCursor(SelectionDelaunayLinesJoinSort, ["x1", "y1", "x2", "y2", "EDGE", "InputBdgMBG_Area",
                                                                    "InputBdgMBG_MBG_Orientation"]) as cursor5:
            # calculation of the area and orientation of the MBG
            for z in cursor5:
                string1 = str(z[4])
                string2 = string1.replace("[", "")
                string = string2.replace("]", "")
                node1, node2 = string.split(",", 1)

                x1, y1, x2, y2, EDGE, Area, MBG_Orient = z[0], z[1], z[2], z[3], z[4], z[5], z[6]
                # calculation area weight and orientation weight
                if EDGE == EDGE2:
                    if Area > Area2:
                        areadiff = 1 - Area2 / Area
                    else:
                        areadiff = 1 - Area / Area2
                    MBG_Orient = (math.cos(math.radians(MBG_Orient)))
                    MBG_Orient2 = (math.cos(math.radians(MBG_Orient2)))
                    orintdiff = abs(abs(MBG_Orient) - abs(MBG_Orient2))
                    G2.add_edge(int(node1), int(node2), weight=areadiff)
                    G3.add_edge(int(node1), int(node2), weight=orintdiff)
                EDGE2, Area2, MBG_Orient2 = EDGE, Area, MBG_Orient
        del cursor5

        mst = nx.minimum_spanning_edges(G, data=True)  # a generator of MST edges
        edgelist = list(mst)  # make a list of the edges
        ArrayOfLines = []
        for x in range(len(edgelist)):
            p1, p2, w = edgelist[x]
            weight = w['weight']
            x1, y1 = list_of_points[p1]
            x2, y2 = list_of_points[p2]
            ArrayOfLines.append([[x1, y1], [x2, y2], weight])
        arcpy.CopyFeatures_management(Polyline2(ArrayOfLines), MST)

        DelName([h_table, point_input, in_table, DelaunayLines, Delaunay_point_table, point_table, \
                 Graph_Edge_Weight_Table, InputBdgJoinPoints, InputBdgJoin, "ListOpPointsAndNodes", InputBdg_FL, \
                 point_input_FL, DelaunayLines_FL, "Strassen_FL", point_input_FL, \
                 Selection, Knots_1_FL, SelectionDelaunayLines])
        if MST is not None:
            Log("Debug", "MST finish - lines_* {}".format(CountPrint(MST)))
        return (MST)



    def MST_Clustering(self, HU_Input, MST_Input, Overlap_Ratio=18):
        """
        :param HU_Input: Building footprints
        :param MST_Input: Minimum spanning tree as polyline shape
        :return: Aggregated building footprints as polygon shape

        - Clustering building footprints along MST weighted with distance
        """

        HU_Points = mem("HU_Points")
        MST_Input_Join = mem("MST_Input_Join")
        SelMST = tmp("SElMST.shp")
        Merge_Dummy5 = "Merge_Dummy5.shp"
        Merge_Dummy6 = "Merge_Dummy6.shp"
        Rect_Merge = "Rect_Merge.shp"
        IbTools7 = IbTool(self.workspace)

        Log("Debug", "MST Clustering Start")

        DelField(HU_Input, ["Join_Count", "TARGET_FID", "JOIN_FID", "ORIG_FID", "FeatID", "ID"])

        arcpy.management.CreateFeatureclass(self.workspace, Merge_Dummy5, "POLYGON", None, "DISABLED", "DISABLED", None,
                                            None, 0, 0, 0)
        arcpy.management.CreateFeatureclass(self.workspace, Merge_Dummy6, "POLYGON", None, "DISABLED", "DISABLED", None,
                                            None, 0, 0, 0)

        HU_Input_FL = arcpy.MakeFeatureLayer_management(HU_Input)
        MST_Input_FL = arcpy.MakeFeatureLayer_management(MST_Input)
        Sel = arcpy.SelectLayerByLocation_management(MST_Input_FL, "INTERSECT", HU_Input_FL)
        arcpy.CopyFeatures_management(Sel, SelMST)

        # Convert Bdg footprints to polyline
        Shp_Area(HU_Input, 'Area')

        PolyLineXY = IbTools7.HUtoLineXY(HU_Input, "POINT_X;POINT_Y; ORIG_FID")
        arcpy.CopyFeatures_management(PolyLineXY, gdb("HUPOINTS"))
        HULineList = []

        # Convert polyline to dictionary
        with arcpy.da.SearchCursor(PolyLineXY,
                                   ["FID_ORIG", "POINT_X", "POINT_Y", "POINT_X_1", "POINT_Y_1",
                                    "Shape_Len"]) as cursor20:
            for row in cursor20:
                FID_ORIG, X11, Y11, X12, Y12, LENGHTH = row
                HULineList.append([FID_ORIG, X11, Y11, X12, Y12, LENGHTH])
            del cursor20

        HULineListSort = sorted(HULineList, key=itemgetter(0))
        HULineArray = []
        sublist = []
        j = HULineListSort[0][0]
        for i in HULineListSort:
            FID_ORIG, x1, y1, x2, x2, L = i
            if FID_ORIG == j:
                sublist.append(i[1:])
            else:
                HULineArray.append([j, sublist])
                sublist = []
                sublist.append(i[1:])
            j = FID_ORIG
        HULineArray.append([j, sublist])
        dict_HU = dict(list(HULineArray))

        arcpy.management.FeatureToPoint(HU_Input, HU_Points, "INSIDE")
        arcpy.AddField_management(SelMST, "DIFF_LENG", "DOUBLE")
        arcpy.management.CalculateField(SelMST, "DIFF_LENG", "!Shape_Len!", "PYTHON_9.3", '')
        arcpy.analysis.SpatialJoin(SelMST, HU_Points, MST_Input_Join, "JOIN_ONE_TO_MANY", "KEEP_ALL", None, "INTERSECT",
                                   None, '')
        MST_List = []
        with arcpy.da.SearchCursor(MST_Input_Join,
                                   ["TARGET_FID", "ORIG_FID", "DIFF_LENG", "Area"]) as  cursor21:
            for row in cursor21:
                TARGET_FID, ORIG_FID, MST_DIFF, Area = row
                MST_List.append([TARGET_FID, ORIG_FID, MST_DIFF, Area])  # ORIG_FID-1 because of file typ change
            del cursor21

        ORIG_FID2 = 0
        Area2 = 0
        MST_Pair_List = []
        dict_FID_Area = {}
        j = "x"

        ListOutsorted = []
        # sorted from shortest MST_DIFF to longest
        MST_List_Sort = sorted(MST_List, key=itemgetter(2))

        for i in MST_List_Sort:
            TARGET_FID, ORIG_FID1, MST_DIFF, Area1 = i
            if TARGET_FID == j:
                MST_Pair_List.append([MST_DIFF, Area1, Area2, ORIG_FID1, ORIG_FID2])
            j = TARGET_FID
            dict_FID_Area[ORIG_FID1] = Area1
            ORIG_FID2 = ORIG_FID1
            Area2 = Area1

        # MST_Pair_List = MST_Pair_List[:]
        dict_member_groub = {}
        dict_group_all_members = {}

        group_number = 0
        for element in MST_Pair_List:
            MST_DIFF, Area1, Area2, ORIG_FID1, ORIG_FID2 = element
            groupestatus = False
            # if there is only one ORIG_FID continue with next element
            if ORIG_FID1 in dict_HU and ORIG_FID2 in dict_HU:
                pass
            else:
                Log("Alert", "ORIG_FID in MST_Cluster missing")
                continue
            # one Bdg is already member of a group
            if ORIG_FID1 in dict_member_groub or ORIG_FID2 in dict_member_groub:
                if ORIG_FID1 in dict_member_groub:
                    group_id = dict_member_groub[ORIG_FID1]
                    new_FID = ORIG_FID2
                else:
                    group_id = dict_member_groub[ORIG_FID2]
                    new_FID = ORIG_FID1
                members_group_id = dict_group_all_members[group_id][:]
                members_group_id.extend([new_FID])
                members_group_id_coords = []

                for i in members_group_id:
                    members_group_id_coords.extend(dict_HU[i])

                Rect, AreaRect = IbTools7.CalcBoundingRect(members_group_id_coords, Merge_Dummy6, "list")
                sumarea = 0
                for i in members_group_id:
                    sumarea = dict_FID_Area[i] + sumarea

                Ratio = sumarea / AreaRect * 100

                if Ratio > Overlap_Ratio:
                    dict_group_all_members[group_id] = members_group_id
                    dict_member_groub[new_FID] = group_id
                    groupestatus = True

                else:
                    pass
                    # check if small group is possible
                    ListOutsorted.append(["G", ORIG_FID1, ORIG_FID2])

            if (ORIG_FID1 in dict_member_groub or ORIG_FID2 in dict_member_groub) is not True or groupestatus is False:

                if ORIG_FID1 in dict_HU:
                    Coords1 = dict_HU[ORIG_FID1][:]
                else:
                    Log("Alert", "Error in dict_HU:{} was not found".format(ORIG_FID1))
                    continue
                if ORIG_FID2 in dict_HU:
                    Coords2 = dict_HU[ORIG_FID2][:]
                else:
                    Log("Alert", "Error in dict_HU:{} was not found".format(ORIG_FID2))
                    continue
                Coords1.extend(Coords2)

                Rect, AreaRect = IbTools7.CalcBoundingRect(Coords1, Merge_Dummy6, "list")
                Ratio = (Area1 + Area2) / AreaRect * 100

                if Ratio > Overlap_Ratio:
                    dict_member_groub[ORIG_FID1] = group_number
                    dict_member_groub[ORIG_FID2] = group_number
                    dict_group_all_members[group_number] = [ORIG_FID1, ORIG_FID2]
                    group_number = group_number + 1
                else:
                    ListOutsorted.append(["S", ORIG_FID1, ORIG_FID2])

        for single_group in dict_group_all_members:
            single_group_list = dict_group_all_members[single_group][:]
            members_group_id_coords = []
            for j in single_group_list:
                members_group_id_coords.extend(dict_HU[j])

            Rect, AreaRect = IbTools7.CalcBoundingRect(members_group_id_coords, Merge_Dummy6, "list")

            try:
                arcpy.Merge_management([Merge_Dummy5, Rect], Rect_Merge)
                arcpy.management.Delete(Merge_Dummy5)
                arcpy.CopyFeatures_management(Rect_Merge, Merge_Dummy5)
            except:
                if single_group_list is not None:
                    Log("Debug", "Group could not merged: {}".format(single_group_list))
                else:
                    Log("Debug", "Group could not merged: None-Type")

        DelName([Merge_Dummy6, Merge_Dummy5, MST_Input_FL, SelMST, Sel])
        if Rect_Merge is not None:
            Log("Debug", "MST Clustering End - Rect Merge {}".format(CountPrint(Rect_Merge)))
        return Rect_Merge


    def AddSinglBdg(self, InputHU, Rect_Merge, threshold=300):
        """
        :param InputHU: building footprints
        :param Rect_Merge: Geometry to which the buildings are to be attached
        :param threshold: area threshold value
        :return: Merged geometry

        - Refinement function
        - Adds detached buildings to the boundary depending on the size of the footprint area.
        """

        SelHU = mem('SelHU')
        SelHU2 = mem('SelHU2')
        HU_Rect = mem('HU_Rect')
        BigSinglBdg = "BigSinglBdg.shp"

        IbTools6 = IbTool(self.workspace)

        Log("Debug", "AddSinglBdg Start")
        Rect_Merge_FL = arcpy.MakeFeatureLayer_management(Rect_Merge)
        InputHU_FL = arcpy.MakeFeatureLayer_management(InputHU)
        Sel = arcpy.SelectLayerByLocation_management(InputHU_FL, "INTERSECT", Rect_Merge_FL, None, "NEW_SELECTION",
                                                     "INVERT")
        arcpy.CopyFeatures_management(Sel, SelHU)
        SelHU_FL = arcpy.MakeFeatureLayer_management(SelHU)
        if len(arcpy.ListFields(SelHU_FL, "Shape_Area")) == 0:
            Shp_Area(SelHU_FL)
        arcpy.management.SelectLayerByAttribute(SelHU_FL, "NEW_SELECTION",
                                                "Shape_Area < {}".format(threshold))
        arcpy.DeleteFeatures_management(SelHU_FL)
        result = arcpy.GetCount_management(SelHU_FL)
        Anz = int(result.getOutput(0))
        if Anz > 0:
            with arcpy.da.SearchCursor(SelHU_FL, ["FID"]) as cursor27:
                for x in cursor27:
                    HUPoly = "HUPoly_{}.shp".format(x[0])
                    whereclause = "FID = {}".format(x[0])
                    Sel = arcpy.management.SelectLayerByAttribute(SelHU_FL, "NEW_SELECTION", whereclause)
                    arcpy.CopyFeatures_management(Sel, SelHU2)
                    Rect = IbTools6.PolyMainAngle(SelHU2)
                    arcpy.CopyFeatures_management(Rect, HUPoly)
            del cursor27

            MergeList = arcpy.ListFeatureClasses('HUPoly_*')
            arcpy.management.Merge(MergeList, HU_Rect)
            DelName(MergeList)

            arcpy.Merge_management([Rect_Merge, HU_Rect], BigSinglBdg)
            Log("Debug", "AddSinglBdg End - BigSumglBdg {}".format(CountPrint(BigSinglBdg)))
            DelName([HU_Rect, SelHU_FL, SelHU2, Rect_Merge_FL, InputHU_FL])
            return BigSinglBdg
        else:
            Log("Debug", "AddSinglBdg End - No Buildings Added")
            return Rect_Merge

    def HoleClose(self, InputPoly, MaxHoleSize):
        """
        :param InputPoly: Polygon shape
        :param MinArea: Area threshold in hectare
        :return: Closes holes within an input polygon up to an area size MinArea ha

        - Refinement function
        -
        """

        InputPoly_line = mem('InputPoly_line')
        InputPoly_poly = mem("InputPoly_poly")
        holepoly = mem('holepoly')
        ges_out_Hole = mem('ges_out_Hole')
        ges_out_h = tmp("hole_close.shp")
        Hole_sel = mem('Hole_sel')

        result = arcpy.GetCount_management(InputPoly)
        Anz = int(result.getOutput(0))
        if Anz > 0:
            arcpy.RepairGeometry_management(InputPoly)
            arcpy.FeatureToLine_management(InputPoly, InputPoly_line, "#", "ATTRIBUTES")
            arcpy.FeatureToPolygon_management(InputPoly_line, InputPoly_poly, "#", "ATTRIBUTES", "#")
            # Select holes
            InputPoly_poly_FL = arcpy.MakeFeatureLayer_management(InputPoly_poly)
            InputPoly_FL = arcpy.MakeFeatureLayer_management(InputPoly)
            Sel = arcpy.management.SelectLayerByLocation(InputPoly_poly_FL, "ARE_IDENTICAL_TO", InputPoly_FL, None,
                                                         "NEW_SELECTION", "INVERT")
            result = arcpy.GetCount_management(Sel)
            Anz = int(result.getOutput(0))
            if Anz > 0:
                arcpy.CopyFeatures_management(Sel, holepoly)
                Shp_Area(holepoly)
                arcpy.MakeFeatureLayer_management(holepoly, 'select_hole', "Shape_Area < {}".format(MaxHoleSize), "#")
                arcpy.CopyFeatures_management('select_hole', Hole_sel)
                arcpy.Merge_management([Hole_sel, InputPoly], ges_out_Hole)
                arcpy.RepairGeometry_management(ges_out_Hole)
                arcpy.management.Dissolve(ges_out_Hole, ges_out_h, "#", "#", "SINGLE_PART", "DISSOLVE_LINES")

            else:
                ges_out_h = InputPoly
            DelName([ges_out_Hole, InputPoly_FL, InputPoly_poly_FL, Sel, Hole_sel, holepoly, InputPoly_line])

        else:
            ges_out_h = InputPoly

        return ges_out_h

    def GapClose(self, imput_deli, Blocks, MaxHoleSize, MaxGapSize, GapDist=30):
        """
        :param imput_deli: Input polygon shape
        :param Blocks: Street blocks polygon shape
        :param MaxHoleSize: Threshold value for holes
        :param MaxGapSize: Threshold value for gaps
        :param GapDist: Distance for double buffer
        :return: Refined input polygon

        - Closes gaps and holes up to the given threshold
        """


        IbTools4 = IbTool(self.workspace)
        Blocks_SymDiff = mem("Blocks_SymDiff")
        Blocks_SymDiff_SinglePart = mem("Blocks_SymDiff_SinglePart")
        BlockParts = tmp("BlockParts.shp")
        BlockParts_Merge = tmp("BlockParts_Merge.shp")
        BlockParts_Merge2 = tmp("BlockParts_Merge2.shp")
        Inner_Areas_Diss = "Inner_Areas_Diss.shp"
        Inner_Areas_Diss_Buff = mem("Inner_Areas_Diss_Buff")
        InnerAreasOutline = mem("InnerAreasOutline")
        InnerAreasOutline_Buff = mem("InnerAreasOutline_Buff")
        Inner_Areas_Erase = tmp("Inner_Areas_Erase.shp")  # mem
        Inner_Areas_Erase_Erase = mem("Inner_Areas_Erase_Erase")
        Inner_Areas_Erase_Erase_SingP = mem("Inner_Areas_Erase_Erase_SingP")
        Inner_Areas_Erase_Simpl = tmp("Inner_Areas_Erase_Simpl.shp")  # mem

        Log("Debug", "gap_close Start")

        def GapSelect(InputPoly, InputGaps, lengthpercentage):
            """
            :param InputPoly: Input polygon
            :param InputGaps: Gaps polygon
            :param lengthpercentage: Threshold value for closing a gap
            :return: Gap polygons, which are above the threshold value fulfill

            - Checks the proportion of the edges of the gap polygon to the input polygon
            """

            InputPoly_line = mem('InputPoly_line')
            InputPoly_diss = mem('InputPoly_diss')
            InputGaps_diss = mem('InputGaps_diss')
            InputGaps_line = mem('InputGaps_line')
            InputGaps_line_vert = tmp('InputGaps_line_vert.shp')
            InputGaps_line_diss = tmp('InputGaps_line_diss.shp')
            SelGaps = tmp('SelGaps.shp')

            arcpy.Dissolve_management(InputPoly, InputPoly_diss)
            arcpy.FeatureToLine_management(InputPoly_diss, InputPoly_line)

            arcpy.FeatureToLine_management(InputGaps, InputGaps_line)
            arcpy.Dissolve_management(InputGaps_line, InputGaps_diss, "#", "#", "SINGLE_PART", "DISSOLVE_LINES")
            arcpy.AddField_management(InputGaps_diss, "ID", "TEXT")
            arcpy.management.CalculateField(InputGaps_diss, "ID", "!FID!", "PYTHON_9.3")
            Shp_Length(InputGaps_diss)
            Rename_Field(InputGaps_diss, "Shape_Len", "Shape_L1", "DOUBLE")
            arcpy.management.SplitLine(InputGaps_diss, InputGaps_line_vert)
            Shp_Length(InputGaps_line_vert)
            InputGaps_line_vert_FL = arcpy.MakeFeatureLayer_management(InputGaps_line_vert)
            InputPoly_line_FL = arcpy.MakeFeatureLayer_management(InputPoly_line)

            arcpy.SelectLayerByLocation_management(InputGaps_line_vert_FL, "INTERSECT", InputPoly_line_FL)
            arcpy.SelectLayerByAttribute_management(InputGaps_line_vert_FL, "SWITCH_SELECTION")
            arcpy.DeleteFeatures_management(InputGaps_line_vert_FL)
            arcpy.management.Dissolve(InputGaps_line_vert_FL, InputGaps_line_diss, "Id", "Shape_Len SUM; Shape_L1 MEAN",
                                      "MULTI_PART", "DISSOLVE_LINES")
            arcpy.AddField_management(InputGaps_line_diss, "LengPer", "DOUBLE")
            arcpy.management.CalculateField(InputGaps_line_diss, "LengPer", "(!SUM_Shape_! / !MEAN_Shape! * 100)",
                                            "PYTHON_9.3")
            InputGaps_line_diss_FL = arcpy.MakeFeatureLayer_management(InputGaps_line_diss)
            Sel = arcpy.management.SelectLayerByAttribute(InputGaps_line_diss_FL, "NEW_SELECTION",
                                                          "LengPer < {}".format(lengthpercentage))
            arcpy.CopyFeatures_management(Sel, SelGaps)
            SelGaps_FL = arcpy.MakeFeatureLayer_management(SelGaps)
            InputGaps_FL = arcpy.MakeFeatureLayer_management(InputGaps)
            arcpy.SelectLayerByLocation_management(InputGaps_FL, "INTERSECT", SelGaps_FL, None, "NEW_SELECTION",
                                                   "NOT_INVERT")
            arcpy.DeleteFeatures_management(InputGaps_FL)
            DelName([InputPoly_line, InputPoly_line_FL, InputGaps_line, InputGaps_line_vert, InputGaps_line_vert_FL,
                     InputGaps_line_diss, InputGaps_FL, SelGaps])

            return InputGaps

        result = arcpy.GetCount_management(imput_deli)
        count = int(result.getOutput(0))
        if count > 0:

            # Closing Holes
            PolyHoleClose = IbTools4.HoleClose(imput_deli, MaxHoleSize)

            # Detect small gaps to Block boarders an close them
            arcpy.analysis.SymDiff(Blocks, PolyHoleClose, Blocks_SymDiff, "ALL", None)

            arcpy.management.MultipartToSinglepart(Blocks_SymDiff, Blocks_SymDiff_SinglePart)

            Shp_Area(Blocks_SymDiff_SinglePart)
            Blocks_SymDiff_SinglePart_FL = arcpy.MakeFeatureLayer_management(Blocks_SymDiff_SinglePart)
            Selection = arcpy.management.SelectLayerByAttribute(Blocks_SymDiff_SinglePart_FL, "NEW_SELECTION",
                                                                "Shape_Area < {}".format(MaxGapSize))
            result = arcpy.GetCount_management(Selection)
            count = int(result.getOutput(0))
            if count > 0:

                arcpy.CopyFeatures_management(Selection, BlockParts)
                GapOut = GapSelect(imput_deli, BlockParts, 70)
                arcpy.Merge_management([GapOut, PolyHoleClose], BlockParts_Merge)
                arcpy.RepairGeometry_management(BlockParts_Merge)
                arcpy.Dissolve_management(BlockParts_Merge, Inner_Areas_Diss, "#", "#", "SINGLE_PART", "DISSOLVE_LINES")
            else:
                Inner_Areas_Diss = PolyHoleClose
                BlockParts_Merge = PolyHoleClose

            # Double buffer
            arcpy.analysis.Buffer(Inner_Areas_Diss, Inner_Areas_Diss_Buff, "{} Meters".format(GapDist), "FULL", "FLAT",
                                  "ALL", None,
                                  "PLANAR")
            arcpy.management.FeatureToLine(Inner_Areas_Diss_Buff, InnerAreasOutline, None, "ATTRIBUTES")
            arcpy.analysis.Buffer(InnerAreasOutline, InnerAreasOutline_Buff, "{} Meters".format(GapDist), "FULL",
                                  "FLAT", "NONE", None,
                                  "PLANAR")
            arcpy.analysis.Erase(Inner_Areas_Diss_Buff, InnerAreasOutline_Buff, Inner_Areas_Erase, None)
            arcpy.analysis.Erase(Inner_Areas_Erase, Inner_Areas_Diss, Inner_Areas_Erase_Erase, None)
            arcpy.management.MultipartToSinglepart(Inner_Areas_Erase_Erase, Inner_Areas_Erase_Erase_SingP)
            arcpy.CopyFeatures_management(Inner_Areas_Erase_Erase_SingP, Inner_Areas_Erase_Simpl)  ##############
            # Delete small patches in the Edges
            Shp_Area(Inner_Areas_Erase_Erase_SingP)
            Inner_Areas_Erase_Erase_SingP_FL = arcpy.MakeFeatureLayer_management(Inner_Areas_Erase_Erase_SingP)
            where_clause = 'Shape_Area < {}'.format(200 * GapDist / 15)
            arcpy.SelectLayerByAttribute_management(Inner_Areas_Erase_Erase_SingP_FL, "NEW_SELECTION", where_clause)
            arcpy.DeleteFeatures_management(Inner_Areas_Erase_Erase_SingP_FL)

            GapOut = GapSelect(imput_deli, Inner_Areas_Erase_Erase_SingP, 70)
            arcpy.Merge_management([GapOut, BlockParts_Merge], BlockParts_Merge2)  #TODO MaxGapSize missing
            arcpy.RepairGeometry_management(BlockParts_Merge2)
            arcpy.Dissolve_management(BlockParts_Merge2, Inner_Areas_Diss, "#", "#", "SINGLE_PART", "DISSOLVE_LINES")

            PolyHoleClose = IbTools4.HoleClose(Inner_Areas_Diss, MaxHoleSize)
            Log("Debug", "gap_close End-  PolyHoleClose {}".format(CountPrint(PolyHoleClose)))

            DelName([Blocks_SymDiff, Blocks_SymDiff_SinglePart, BlockParts,
                     Inner_Areas_Diss_Buff, InnerAreasOutline, InnerAreasOutline_Buff,
                     Blocks_SymDiff_SinglePart_FL, Selection])

            return PolyHoleClose
        else:
            # arcpy.AddMessage("Eingabelayer Loecher ist leer!")
            pass

            return imput_deli

    def EdgeCatch(self, Grouped_Bdgs, HU_Input, RoadNetwork, Bloecke):
        """
        :param Grouped_Bdgs: Input polygon, which should snap to the roads
        :param HU_Input: Building footprints
        :param RoadNetwork: Roadnetwork
        :param Bloecke: Street blocks
        :return: Refined input polygon

        - Closes gaps between input polygons and roads
        """
        # Local variables
        Group = tmp("Group.shp")
        Merge_Dummy7 = "Merge_Dummy7.shp"
        Block_Sel = tmp("Block2_Sel.shp") #tmp
        HU_Outline = mem("HU_Outline")  # mem
        Sel_HU_Vertics = mem("Sel_HU_Vertics")  # mem
        NearTbl = mem("NearTbl")
        Merge_All = mem("Merge_All")  # mem
        Merge_Poly = mem("Merge_Poly")  # mem
        Merge_Poly_Sel = mem("Merge_Poly_Sel")
        HU_Vert_Ortho = mem("HU_Vert_Ortho") #tmp
        Sel_Copy = mem("Sel_Copy") #tmp
        DelineateSinglBdgPoly = mem("DelineateSinglBdgPoly")  # mem
        DeliBdg = tmp("DeliBdg.shp")
        PointsRNLine = mem("PointsRNLine")
        blocksel = mem("blocksel")
        roadsel = mem("roadsel")

        Log("Debug", "EdgeCatch Start")

        def Point(ArrayOfPoints):
            # Creates point shape file from array of coordinates
            # Source: https://pro.arcgis.com/de/pro-app/arcpy/classes/pointgeometry.htm
            point_feature = mem("point_feature")
            point = arcpy.Point()
            pointGeometryList = []

            for pt in ArrayOfPoints:
                point.X = pt[0]
                point.Y = pt[1]
                pointGeometry = arcpy.PointGeometry(point, sr)
                pointGeometryList.append(pointGeometry)
            arcpy.CopyFeatures_management(pointGeometryList, point_feature)

            return point_feature

        IbTools8 = IbTool(self.workspace)
        DelName([Merge_Dummy7, DeliBdg])

        arcpy.management.CreateFeatureclass(self.workspace, Merge_Dummy7, "POLYGON", None, "DISABLED", "DISABLED", None,
                                            None, 0, 0, 0)
        Shp_Area(Grouped_Bdgs)

        Grouped_Bdgs_FL = arcpy.MakeFeatureLayer_management(Grouped_Bdgs)
        merge_count = 0
        MergeList = arcpy.ListFeatureClasses('DelineateSinglBdgPolyMerge_*')
        DelName(MergeList)

        with arcpy.da.SearchCursor(Grouped_Bdgs, ["FID", "Shape_Area"]) as cursor22:
            for grprow in cursor22:

                i = grprow[0]
                shapeareagroup = grprow[1]
                where_clause = 'FID = {}'.format(str(i))

                Grouped_Bdgs_FL = arcpy.MakeFeatureLayer_management(Grouped_Bdgs)
                Selection = arcpy.SelectLayerByAttribute_management(Grouped_Bdgs_FL, "NEW_SELECTION", where_clause)
                arcpy.CopyFeatures_management(Selection, Group)

                arcpy.management.FeatureVerticesToPoints(Group, Sel_HU_Vertics, "ALL")
                Sel_HU_Vertics_FL = arcpy.MakeFeatureLayer_management(Sel_HU_Vertics)
                Bloecke_FL = arcpy.MakeFeatureLayer_management(Bloecke)
                sel = arcpy.management.SelectLayerByLocation(Bloecke_FL, "INTERSECT", Sel_HU_Vertics_FL, None,
                                                             "NEW_SELECTION", "NOT_INVERT")
                arcpy.CopyFeatures_management(sel, blocksel)

                blocksel_FL = arcpy.MakeFeatureLayer_management(blocksel)
                RoadNetwork_FL = arcpy.MakeFeatureLayer_management(RoadNetwork)
                sel = arcpy.management.SelectLayerByLocation(RoadNetwork_FL, "INTERSECT", blocksel_FL, None,
                                                             "NEW_SELECTION", "NOT_INVERT")
                arcpy.CopyFeatures_management(sel, roadsel)

                arcpy.analysis.GenerateNearTable(Sel_HU_Vertics, roadsel, NearTbl, None, "LOCATION", "ANGLE",
                                                 "CLOSEST", 1, "PLANAR")

                List = []

                with arcpy.da.SearchCursor(NearTbl, ["FROM_X", "FROM_Y", "NEAR_X", "NEAR_Y", "NEAR_ANGLE",
                                                     "NEAR_DIST"]) as cursor15:
                    # Threshold for length cut
                    for row in cursor15:
                        if row[5] < 70:
                            List.append([[row[0], row[1]], [row[2], row[3]], np.cos(row[4]), row[5]])
                del cursor15

                # Sort all by angle
                groups = []

                if len(List) > 0:
                    data = sorted(List, key=itemgetter(-2))
                    # make group of lines with similar angle
                    groups.append([data[0]])
                    for x in data[1:]:
                        if abs(x[2] - groups[-1][-1][2]) <= 1:
                            groups[-1].append(x)
                        else:
                            groups.append([x])

                    # if there are at least 2 groups, then calculate average distance for each group
                    if len(groups) > 2:
                        sumlist = []
                        for e in groups:
                            sum = 0
                            anz = 0
                            for j in e:
                                sum = j[3] + sum
                                anz = anz + 1
                            sumlist.append(sum / anz)
                        # remove group with significant longer distance
                        h, b = 0, 0
                        k = -1

                        for e in sumlist:
                            k = k + 1
                            if e > h:
                                b = h
                                h = e
                                p = k
                        if h * 1.5 > b:
                            groups.pop(p)
                    else:
                        pass
                    ArrayOfLines = []
                    ArrayOfPointsRN = []

                    try:

                        for e in groups:
                            for grow in e:
                                ArrayOfLines.append([grow[0], grow[1]])
                                ArrayOfPointsRN.append(grow[1])
                    except:

                        for e in groups:
                            for k in e:
                                for grow in k:
                                    ArrayOfLines.append([grow[0], grow[1]])
                                    ArrayOfPointsRN.append(grow[1])

                    PointsRN = Point(ArrayOfPointsRN)
                    arcpy.PointsToLine_management(PointsRN, PointsRNLine)
                    #PointsRN_FL = arcpy.MakeFeatureLayer_management(PointsRN)
                    arcpy.CopyFeatures_management(Polyline2(ArrayOfLines), HU_Vert_Ortho)
                    Shp_Length(HU_Vert_Ortho)
                    arcpy.MakeFeatureLayer_management(HU_Vert_Ortho, "HU_Vert_Ortho_FL")
                    #arcpy.RepairGeometry_management(Group)
                    arcpy.management.PolygonToLine(Group, HU_Outline)
                    arcpy.Delete_management(Group)
                    Sel = arcpy.management.SelectLayerByLocation(RoadNetwork_FL, "INTERSECT", "HU_Vert_Ortho_FL", None,
                                                                 "NEW_SELECTION", "NOT_INVERT")
                    arcpy.CopyFeatures_management(Sel, Sel_Copy)
                    arcpy.Merge_management([Sel_Copy, HU_Outline, HU_Vert_Ortho], Merge_All)
                    if len(List) == 0:
                        CountPrint(Merge_All)

                    #arcpy.RepairGeometry_management(Merge_All)
                    arcpy.management.FeatureToPolygon(Merge_All, Merge_Poly, None, "ATTRIBUTES", None)
                    Merge_Poly_FL = arcpy.MakeFeatureLayer_management(Merge_Poly)  # Problem
                    InputHU_FL = arcpy.MakeFeatureLayer_management(HU_Input)  # Problem
                    Sel = arcpy.management.SelectLayerByLocation(Merge_Poly_FL, "INTERSECT", InputHU_FL, None,
                                                                 "NEW_SELECTION", "NOT_INVERT")

                    arcpy.CopyFeatures_management(Sel, Merge_Poly_Sel)
                    arcpy.Delete_management(Merge_Poly_FL)
                    arcpy.Delete_management(Sel)

                    # Cut of Block from Merged Poly
                    Bloecke_FL = arcpy.MakeFeatureLayer_management(Bloecke)  # problem
                    Selection = arcpy.SelectLayerByLocation_management(Bloecke_FL, "INTERSECT", InputHU_FL, "",
                                                                       "NEW_SELECTION", "")

                    arcpy.CopyFeatures_management(Selection, Block_Sel)
                    arcpy.Intersect_analysis([Merge_Poly_Sel, Block_Sel], DelineateSinglBdgPoly)
                    Shp_Area(DelineateSinglBdgPoly)

                    DelineateSinglBdgPoly_FL = arcpy.MakeFeatureLayer_management(DelineateSinglBdgPoly)

                    where_clause = 'Shape_Area < {}'.format((shapeareagroup * 3))
                    Sel = arcpy.SelectLayerByAttribute_management(DelineateSinglBdgPoly_FL, "NEW_SELECTION",
                                                                  where_clause)

                    arcpy.SelectLayerByAttribute_management(DelineateSinglBdgPoly_FL, "SWITCH_SELECTION")
                    arcpy.DeleteFeatures_management(DelineateSinglBdgPoly_FL)

                    try:
                        merge_count += 1
                        arcpy.CopyFeatures_management(DelineateSinglBdgPoly, "DelineateSinglBdgPolyMerge_{}.shp".format(merge_count))
                    except:
                        if grprow[0] is not None:
                            Log("Alert", "{} in EdgeCatch skiped".format(grprow[0]))

                    DelName(
                        [Selection, Sel_HU_Vertics, NearTbl, "HU_Vert_Ortho_FL", RoadNetwork_FL, InputHU_FL, Bloecke_FL, DelineateSinglBdgPoly_FL, DelineateSinglBdgPoly])

        del cursor22
        MergeList = arcpy.ListFeatureClasses('DelineateSinglBdgPolyMerge_*')
        arcpy.management.Merge(MergeList, DeliBdg)
        DelName(MergeList)

        DelName([Sel_HU_Vertics, Merge_Poly_Sel, Sel_Copy, HU_Outline, NearTbl, \
                 Merge_All, Merge_Poly_Sel, HU_Vert_Ortho, Block_Sel, Bloecke_FL, InputHU_FL,
                 Merge_Poly_FL, RoadNetwork_FL, "HU_Vert_Ortho_FL", Grouped_Bdgs_FL, DelineateSinglBdgPoly, \
                 Selection, Sel, Merge_Poly, Merge_Dummy7])
        if DeliBdg is not None:
            Log("Debug", "EdgeCatch End - DeliBdg {}".format(CountPrint(DeliBdg)))

        return DeliBdg

    def GapFix(self, Inputpoly, InputRoadnetwork, bufferwidth=70):
        """
        :param Inputpoly: Combined boundaries from all partitions as polygon shape
        :param InputRoadnetwork: Road network
        :param bufferwidth: Threshold for buffer
        :return: Refined polygon shape

        - Closes gaps between boundaries of different partitions
        """


        ugb_line = mem('ugb_line')
        ugb_buff = mem('ugb_buff')
        ugb_buff_intsec1 = mem('ugb_buff_intsec1')
        ugb_buff_intsec2 = mem('ugb_buff_intsec2')
        ugb_buff_intsec_diss = mem('ugb_buff_intsec_diss')
        ugb_symdiff = mem('ugb_symdiff')
        rn_merge = mem('rn_merge')
        rn_merge_ply = mem('rn_merge_ply')
        RoBl_Merge = mem('RoBl_Merge')
        RoBl_sel = tmp('RoBl_sel.shp')
        inputpoly_merge = mem('inputpoly_merge')
        GapFix_out = "GapFix.shp"

        Log("Debug", "GapFix Start")

        result = arcpy.GetCount_management(Inputpoly)
        Anz_Input = int(result.getOutput(0))
        if Anz_Input > 0:
            ugb_FL = arcpy.MakeFeatureLayer_management(Inputpoly)
            arcpy.management.FeatureToLine(Inputpoly, ugb_line, None, "ATTRIBUTES")
            arcpy.analysis.Buffer(ugb_line, ugb_buff, "{} Meters".format(bufferwidth), "FULL", "ROUND", "NONE", None, "PLANAR")
            arcpy.analysis.Intersect(ugb_buff, ugb_buff_intsec1, "ALL", None, "INPUT")
            arcpy.analysis.Intersect(ugb_buff_intsec1, ugb_buff_intsec2, "ALL", None, "INPUT")
            arcpy.management.Dissolve(ugb_buff_intsec2, ugb_buff_intsec_diss, None, None, "SINGLE_PART", "DISSOLVE_LINES")
            arcpy.analysis.SymDiff(ugb_buff_intsec_diss, Inputpoly, ugb_symdiff, "ALL", None)
            ugb_symdiff_FL = arcpy.MakeFeatureLayer_management(ugb_symdiff)
            arcpy.management.SelectLayerByLocation(ugb_symdiff_FL, "WITHIN", ugb_FL, None, "NEW_SELECTION", "NOT_INVERT")
            arcpy.DeleteFeatures_management(ugb_symdiff_FL)
            arcpy.management.SelectLayerByLocation(ugb_symdiff_FL, "INTERSECT", ugb_FL, None, "NEW_SELECTION", "INVERT")
            arcpy.DeleteFeatures_management(ugb_symdiff_FL)

            result = arcpy.GetCount_management(ugb_symdiff_FL)
            Anz = int(result.getOutput(0))
            if Anz > 0:
                arcpy.management.Merge([InputRoadnetwork, ugb_line], rn_merge)
                arcpy.management.FeatureToPolygon(rn_merge, rn_merge_ply, None, "ATTRIBUTES", None)
                arcpy.AddField_management(rn_merge_ply, "Name", "TEXT")
                try:
                    arcpy.management.CalculateField(rn_merge_ply, "Name", "'RoBl_'+ str(!OID!)", "PYTHON_9.3", None)
                except:
                    pass
                arcpy.analysis.Split(ugb_symdiff_FL, rn_merge_ply, "Name", Workspace, None)
                MergeList = arcpy.ListFeatureClasses('RoBl_*')
                arcpy.management.Merge(MergeList, RoBl_Merge)
                DelName(MergeList)
                rn_merge_ply_FL = arcpy.MakeFeatureLayer_management(rn_merge_ply)
                RoBl_Merge_FL = arcpy.MakeFeatureLayer_management(RoBl_Merge)
                sel = arcpy.management.SelectLayerByLocation(rn_merge_ply_FL, "WITHIN", RoBl_Merge_FL, None,
                                                             "NEW_SELECTION", "NOT_INVERT")
                arcpy.CopyFeatures_management(sel, RoBl_sel)

                arcpy.management.Merge([Inputpoly, RoBl_sel], inputpoly_merge)
                arcpy.management.Dissolve(inputpoly_merge, GapFix_out, None, None, "SINGLE_PART", "DISSOLVE_LINES")

                DelName([])
                if GapFix_out is not None:
                    Log("Debug", "GapFix End - Patches {}".format(CountPrint(GapFix_out)))
                return GapFix_out
            else:
                Log("Debug", "No gaps to Gapfix")
                return Inputpoly
        else:
            Log("Debug", "No gaps to Gapfix")
            return Inputpoly

    def PatchRemove(self, InputPoly, InputBdg, MinPatchSize=10000, MinBdgCount=20,
                    footprintdensitythreshold=18):
        """
        :param InputPoly: Input polygon shape
        :param InputBdg: building footprints
        :param MinPatchSize: Threshold value for minimumm patch size
        :param MinBdgCount: Threshold value for minimum buildings within patch
        :param footprintdensitythreshold: Threshold value for footprintdensity
        :return: Refined polygon shape

        - Removes delineation that is too small in area or contains too few buildings
        """

        CheckFileType(InputPoly, "ShapeFile", "Polygon")
        CheckFileType(InputBdg, "ShapeFile", "Polygon")

        InputPoly_Join = mem("InputPoly_Join")
        InputPoly_Merge = mem('InputPoly_Merge')
        InputPoly_Diss = mem('InputPoly_Diss')
        PatchRemove = ("PatchRemove.shp")
        IbTools5 = IbTool(self.workspace)

        Log("Debug", "PatchRemove Start")

        arcpy.management.AddField(InputPoly, "NAME", "Text", None, None, None, None, "NULLABLE", "NON_REQUIRED", None)
        Expression = '"Block_{}".format(!FID!)'
        arcpy.management.CalculateField(InputPoly, "NAME", Expression, "PYTHON_9.3", None)
        Parts_Overlap = IbTools5.FootprintDensity(InputBdg, InputPoly, footprintdensitythreshold)
        arcpy.analysis.SpatialJoin(InputPoly, InputBdg, InputPoly_Join, "JOIN_ONE_TO_ONE", "KEEP_ALL", '', "INTERSECT",
                                   None, '')
        Shp_Area(InputPoly_Join)
        InputPoly_Join_FL = arcpy.MakeFeatureLayer_management(InputPoly_Join)

        arcpy.management.SelectLayerByAttribute(InputPoly_Join_FL, "NEW_SELECTION",
                                                "Join_Count < {0} Or Shape_Area < {1}".format(MinBdgCount,
                                                                                              MinPatchSize))
        arcpy.DeleteFeatures_management(InputPoly_Join_FL)

        Parts_Overlap_FL = arcpy.MakeFeatureLayer_management(Parts_Overlap)
        arcpy.management.SelectLayerByAttribute(Parts_Overlap_FL, "NEW_SELECTION",
                                                "Shape_Area < {} Or AREA_BLK_M < 6000".format(MinPatchSize))
        arcpy.DeleteFeatures_management(Parts_Overlap_FL)
        arcpy.Merge_management([InputPoly_Join_FL, Parts_Overlap_FL], InputPoly_Merge)
        arcpy.Dissolve_management(InputPoly_Merge, InputPoly_Diss, None, None, "SINGLE_PART",
                                 "DISSOLVE_LINES")
        arcpy.CopyFeatures_management(InputPoly_Diss, PatchRemove)
        Log("Debug", "PatchRemove End - PatchRemove {}".format(CountPrint(PatchRemove)))

        return PatchRemove


def main():


    # GLOBALE VARIABLEN

    global startzeit
    global lockswitch
    global partlist
    global PartLogPath
    startzeit = time.strftime("%Y_%m_%d_%H_%M")
    arcpy.env.overwriteOutput = True
    lockswitch = False
    AuxLayers_Line = mem("AuxLayers_Line")
    AuxLayers_Poly = mem("AuxLayers_Poly")

    # PARAMETER

    try:
        MinOverlapBlocks, globfpdenshresld, MinArea, MinBdgCount, MinPatchSize, MaxHoleSize, MaxGapSize, partstart, partend, partlist, PathCommonWorkspace, DelPartLog = Starter(
            valuelist)
        Log('Info', "PARAMETERS")
        Log('Info', "Script file = " + str(os.path.realpath(__file__)))
        Log('Info', "Workspace = " + str(Workspace))
        Log('Info', "MinOverlapBlocks = {}\n" \
                    "                   GlobalFootprintDensity = {}\n" \
                    "                   MinArea = {}\n" \
                    "                   MinBdgCount = {}\n" \
                    "                   MinPatchSize = {}\n" \
                    "                   max_hole_size = {}\n" \
                    "                   max_gap_size = {}\n" \
                    "                   PartStart = {}\n" \
                    "                   PartEnd = {}\n" \
                    "                   Partlist = {}\n".format(MinOverlapBlocks, globfpdenshresld, MinArea, MinBdgCount, MinPatchSize,
                                           MaxHoleSize, MaxGapSize, partstart, partend, partlist))

        # MAIN PROGRAM

        #  reset temporary folder
        DelName(["Tmp"])
        arcpy.CreateFolder_management(Workspace, "Tmp")

        # Create log folder and dummy files
        Merge_Dummy4 = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "Merge_Dummy4.shp"
        PartLogPath = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + 'IB_Tool2_Log.txt'
        PartLogFin = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "IB_Tool2_Log_Fin.txt"

        if DelPartLog == 'True':
            os.chdir(PathCommonWorkspace)
            DelName(['IB_Tool_Results'])
            os.makedirs('IB_Tool_Results')
            if not os.path.isfile(Merge_Dummy4):
                arcpy.management.CreateFeatureclass(PathCommonWorkspace + os.path.sep + 'IB_Tool_Results',
                                                    'Merge_Dummy4.shp', "POLYGON", None, "DISABLED",
                                                    "DISABLED", None, None, 0, 0, 0)

        # set OS workspace directory
        os.chdir(Workspace)

        # check python version
        if sys.version_info[0] > 2:
            raise Exception(Log('Alert', "Python has to be Python 2"))

        # create auxiliary data
        j = 1
        AuxFileList = []
        AuxLayers = [Veg_Layer] #TODO
        for i in AuxLayers:
            filename = tmp("AuxFile_{}.shp".format(j))
            desc = arcpy.Describe(i)
            if "Polyline" != desc.shapeType:
                arcpy.FeatureToLine_management(i, filename)
            else:
                filename = i
            AuxFileList.append(filename)
            j = j + 1
        AuxFileList.append(Strassen)
        arcpy.Merge_management(AuxFileList, AuxLayers_Line)
        arcpy.RepairGeometry_management(AuxLayers_Line)
        arcpy.FeatureToPolygon_management(AuxLayers_Line, AuxLayers_Poly)

        IbToolsStart = IbTool(Workspace)

        # create list of partitions depending on given parameters
        if str(partlist[0]) == str('#'):
            if partstart == -1 or partend == -1:
                # print("partlist and partstart without values")
                partlist = []
                with arcpy.da.SearchCursor(Partition, ["NAME"]) as CursorPartitionen:
                    for i in CursorPartitionen:
                        partlist.append(i)
                del CursorPartitionen, i
            if partstart != -1 and partend != -1:
                # print("partstart with values")
                partlist = []
                with arcpy.da.SearchCursor(Partition, ["NAME"]) as CursorPartitionen:
                    for i in CursorPartitionen:
                        partlist.append(i)
                del CursorPartitionen, i
                partlist = partlist[partstart:partend]
            newlist = []
            for j in partlist:
                unicodestr = j[0]
                utf8str = unicodestr.encode("utf-8")
                newlist.append(utf8str)
            partlist = newlist
        else:
            newlist = []
            # print("partlist with values")
            for j in partlist:
                newlist.append(j.replace('\n', ''))
            partlist = newlist

        if DelPartLog == 'True':
            if os.path.isfile(PartLogPath):
                os.remove(PartLogPath)

            Partlog = open(PartLogFin, 'w')
            Partlog.write("")
            Partlog.close()

        if not os.path.isfile(PartLogPath):
            Partlog = open(PartLogPath, 'w')
            Partlog.write("")
            Partlog.close()

        # calculate threshold value for footprint density
        if globfpdenshresld == 0:
            globfpdenshresld = IbToolsStart.CalcFootprintDensity(InputHU, Strassen, 100, 0, 'global', MinBdgCount,
                                                                 Partition)
        else:
            pass

        Log('Debug', "Global building coverage threshold =" + str(globfpdenshresld))


        lenpartlist = len(partlist)
        for i in partlist:

            a = 0
            isin = False
            Partlog = open(PartLogPath, 'r+')
            for row in Partlog:
                part = str(row).replace('\n', '')
                if part == i:
                    isin = True
                a = a + 1
            if isin is False:
                Partlog.write("\n" + i)
                Partlog.close()
            if isin is True:
                Partlog.close()
                continue

            try:
                IbTools = IbTool(Workspace)

                Blocks_Veg = tmp("Blocks_Veg.shp")
                Inner_Areas = tmp("Inner_Areas.shp")
                Inner_Areas_Dissolve = "Inner_Areas_Dissolve.shp"  # tmp
                Inner_Areas_Fin_Merge = "Inner_Areas_Fin_Merge_{}.shp".format(startzeit)
                SelHU = tmp("SelHU.shp")
                SelStrassen = tmp("SelStrassen.shp")
                SelStrassen_Diss = tmp("SelStrassen_Diss.shp")  # mem
                Feat_Merge = ("Feat_Merge.shp")
                SelPart = mem("SelPart")
                Blocks_red = mem("Blocks_red_overlap_main")
                HU_Filter_Copy = tmp("HU_Filter_Copy.shp")

                Partition_FL = arcpy.MakeFeatureLayer_management(Partition)
                Strassen_FL = arcpy.MakeFeatureLayer_management(Strassen)
                InputHU_FL = arcpy.MakeFeatureLayer_management(InputHU)

                global Part_Name
                Part_Name = i

                Log('Info', "#######################################################################################")
                Log('Info', "PARTITION: " + str(Part_Name) + " - " + str(a) + " of " + str(len(partlist)))

                whereclause = "NAME = '{}'".format(Part_Name)

                Sel = arcpy.management.SelectLayerByAttribute(Partition_FL, "NEW_SELECTION", whereclause)
                arcpy.CopyFeatures_management(Sel, SelPart)
                SelPart_FL = arcpy.MakeFeatureLayer_management(SelPart)
                Sel = arcpy.management.SelectLayerByLocation(InputHU_FL, "INTERSECT", SelPart_FL)
                arcpy.CopyFeatures_management(Sel, SelHU)
                result = arcpy.GetCount_management(SelHU)
                Anz = int(result.getOutput(0))
                if Anz < 10:
                    PartLogFin = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "IB_Tool2_Log_Fin.txt"
                    Partlog = open(PartLogFin, 'a')
                    Partlog.write("\n" + Part_Name)
                    Partlog.close()
                    Log("Warning", "No or less then 10 buildings selected in partition")
                    continue
                Sel = arcpy.management.SelectLayerByLocation(Strassen_FL, "INTERSECT", SelPart_FL)
                arcpy.CopyFeatures_management(Sel, SelStrassen)
                result = arcpy.GetCount_management(SelStrassen)
                Anz = int(result.getOutput(0))
                if Anz < 5:
                    PartLogFin = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "IB_Tool2_Log_Fin.txt"
                    Partlog = open(PartLogFin, 'a')
                    Partlog.write("\n" + Part_Name)
                    Partlog.close()
                    Log("Warning", "No or less then 5 roads selected in partition")
                    continue

                Log("Debug", "SelHU {}".format(CountPrint(SelHU)))
                Log("Debug", "SelStrassen {}".format(CountPrint(SelStrassen)))

                MinOverlapMST = IbTools.CalcFootprintDensity(SelHU, SelStrassen, 100, globfpdenshresld, 'local',
                                                             MinBdgCount)

                Log("Debug", "Local building coverage =" + str(MinOverlapMST))



                Blocks = IbTools.Blocker(AuxLayers_Line, SelHU, SelPart_FL)
                arcpy.CopyFeatures_management(Blocks, Blocks_Veg)


                HU_Filter = IbTools.InputHU_Filter(SelHU, MinArea)
                if HU_Filter == None:
                    PartLogFin = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "IB_Tool2_Log_Fin.txt"
                    Partlog = open(PartLogFin, 'a')
                    Partlog.write("\n" + Part_Name)
                    Partlog.close()
                    Log("Warning", "No HU_Filter selected.")
                    continue
                arcpy.CopyFeatures_management(HU_Filter, HU_Filter_Copy)

                OverlapCalcOutput = IbTools.FootprintDensity(HU_Filter, Blocks_Veg, MinOverlapBlocks)

                arcpy.CopyFeatures_management(OverlapCalcOutput, Blocks_red)

                HU_Filter_FL = arcpy.MakeFeatureLayer_management(HU_Filter)
                OverlapCalcOutput_FL = arcpy.MakeFeatureLayer_management(OverlapCalcOutput)
                Sel = arcpy.SelectLayerByLocation_management(HU_Filter_FL, "INTERSECT", OverlapCalcOutput_FL, None,
                                                             "NEW_SELECTION", "NOT_INVERT")
                arcpy.DeleteFeatures_management(HU_Filter_FL)


                Blocks = IbTools.Blocker(SelStrassen, SelHU, SelPart_FL)

                DelName([SelPart_FL, Strassen_FL, InputHU_FL, Sel, whereclause])


                MST = IbTools.MST(HU_Filter, SelStrassen, Part_Name)


                Cluster_Features = IbTools.MST_Clustering(HU_Filter, MST, MinOverlapMST)

                BigSinglBdg = IbTools.AddSinglBdg(HU_Filter, Cluster_Features)

                arcpy.Merge_management([BigSinglBdg, Blocks_red], Feat_Merge)
                arcpy.RepairGeometry_management(Feat_Merge)
                Log("Debug", "Merge Rectangels - FeatMerge {}".format(CountPrint(Feat_Merge)))

                Deli_Areas = IbTools.EdgeCatch(Feat_Merge, HU_Filter, SelStrassen, Blocks)

                arcpy.Merge_management([Deli_Areas, Blocks_red], Inner_Areas)
                arcpy.RepairGeometry_management(Inner_Areas)
                Log("Debug", "Merge Inner_Areas {}".format(CountPrint(Inner_Areas)))
                arcpy.management.Dissolve(Inner_Areas, Inner_Areas_Dissolve, None, None, "SINGLE_PART",
                                          "DISSOLVE_LINES")

                Inner_Areas_Fin = IbTools.GapClose(Inner_Areas_Dissolve, Blocks, MaxHoleSize, MaxGapSize)


                PatchRemove = IbTools.PatchRemove(Inner_Areas_Fin, HU_Filter_Copy, MinPatchSize,
                                                  MinBdgCount, MinOverlapMST)

                #  Lock while mergeing results
                os.chdir(PathCommonWorkspace)
                while os.path.exists('Lock'):
                    time.sleep(5)
                os.makedirs('Lock')
                lockswitch = True

                Merge_Dummy4 = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "Merge_Dummy4.shp"
                result = arcpy.GetCount_management(Merge_Dummy4)
                Anz1 = int(result.getOutput(0))
                result = arcpy.GetCount_management(PatchRemove)
                Anz2 = int(result.getOutput(0))

                whileswitch = True
                while whileswitch:
                    arcpy.Merge_management([PatchRemove, Merge_Dummy4], Inner_Areas_Fin_Merge)
                    arcpy.RepairGeometry_management(Inner_Areas_Fin_Merge)
                    result = arcpy.GetCount_management(Inner_Areas_Fin_Merge)
                    Anz3 = int(result.getOutput(0))
                    if Anz1 + Anz2 != Anz3:
                        Log("Warning", "Final merge not finished: {} + {} = {}".format(Anz1, Anz3, Anz3))
                        time.sleep(5)
                    else:
                        whileswitch = False

                arcpy.management.Delete(Merge_Dummy4)
                arcpy.CopyFeatures_management(Inner_Areas_Fin_Merge, Merge_Dummy4)
                DelName([Inner_Areas_Fin_Merge])
                os.rmdir('Lock')
                lockswitch = False
                os.chdir(Workspace)

                DelName(arcpy.ListFeatureClasses('point_input_Block_*'))
                DelName(arcpy.ListFeatureClasses('MST_Block_*'))
                DelName(arcpy.ListFeatureClasses('lines_Zone*'))
                DelName(arcpy.ListFeatureClasses('DelaunayLines_Block_*'))
                DelName(arcpy.ListFeatureClasses('HU_sel_FL_Block_*'))
                DelName(arcpy.ListFeatureClasses('lines_Block_*'))
                DelName(arcpy.ListTables('testtable_Block_*'))
                DelName(["Block_Table", Inner_Areas, Inner_Areas_Dissolve, Inner_Areas_Fin, MST, PatchRemove, \
                         Partition_FL, Strassen_FL, InputHU_FL, HU_Filter, HU_Filter_FL, Feat_Merge, "polyline2.shp",
                         Cluster_Features, HU_Filter_Copy, BigSinglBdg])

                PartLogFin = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "IB_Tool2_Log_Fin.txt"
                Partlog = open(PartLogFin, 'a')
                Partlog.write("\n" + Part_Name)
                Partlog.close()

                Log("Info", 'COMPLETED SUCCESSFULLY')

                del IbTools, Inner_Areas, HU_Filter, SelPart, MST, SelHU, Deli_Areas, \
                    Blocks_red, PatchRemove,  Strassen_FL, SelStrassen,  whereclause, \
                    SelPart_FL, Cluster_Features,  SelStrassen_Diss, Blocks, \
                    Blocks_Veg, Partition_FL, Inner_Areas_Fin, InputHU_FL, Inner_Areas_Dissolve, Feat_Merge, \
                    Sel

            except arcpy.ExecuteError:
                # If a ArcGIS tool error occurs, current partition will be calculated again at the end.

                exc_type, exc_value, exc_traceback = sys.exc_info()
                print ("ToolError:")
                traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
                print ("ToolError (long)")
                traceback.print_exception(exc_type, exc_value, exc_traceback,
                                         limit=2, file=sys.stdout)

                try:
                    Partlog = open(PartLogPath, 'r')
                    lines = Partlog.readlines()
                    Partlog.close()
                    os.remove(PartLogPath)
                    Partlog = open(PartLogPath, 'w')

                    for line in lines:
                        if line == Part_Name or line == "\n":
                            pass
                        else:
                            Partlog.write(line)
                    Partlog.close()
                    partlist.append(i)
                    Log("Debug", "{} removed from PartLog.".format(Part_Name))

                    if lockswitch == True:
                        os.chdir(PathCommonWorkspace)
                        os.rmdir('Lock')
                        lockswitch = False
                        os.chdir(Workspace)


                except Exception as e:

                    Log("Alert", str(e))
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    print ("Error in ToolError exception")
                    traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout)


            except TypeError as e:

                Log("Alert", str(e))
                exc_type, exc_value, exc_traceback = sys.exc_info()
                print ("TypeError")
                traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
                print ("TypeError (long)")
                traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout)


            except Exception as e:
                Log("Alert", str(e))
                exc_type, exc_value, exc_traceback = sys.exc_info()
                print ("General python error:")
                traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
                print ("General python error (long):")
                traceback.print_exception(exc_type, exc_value, exc_traceback, limit=2, file=sys.stdout)


        Log("Info", "Worker process finished queue.")


        with open(PartLogFin, "r") as file:
            List_Parts_Fin = file.readlines()

        if (lenpartlist + 1) == len(List_Parts_Fin):  # All parts are completed successfully
            IbTools = IbTool(Workspace)
            Merge_Dummy4 = PathCommonWorkspace + os.path.sep + 'IB_Tool_Results' + os.path.sep + "Merge_Dummy4.shp"

            GapFix_out = IbTools.GapFix(Merge_Dummy4, Strassen)

            FinData = PathCommonWorkspace + os.path.sep + "B_FinData_{}.shp".format(startzeit)
            Inner_Areas_Fin = IbTools.HoleClose(GapFix_out, MaxHoleSize)
            arcpy.CopyFeatures_management(Inner_Areas_Fin, FinData)
            Log("Info", "Refinement successful")
        else:
            Log("Info", "No Refinement")

        DelName([AuxLayers_Line, AuxLayers_Poly, GapFix_out])
        arcpy.Delete_management("Tmp.gdb")
        DelName(['IB_Tool_Results', 'Tmp'])

    except Exception as e:

        time.sleep(3)
        raw_input("Press key to exit.")
        sys.exit(-1)


if __name__ == '__main__':
    main()
