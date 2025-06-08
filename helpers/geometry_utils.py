import networkx as nx
from pandas.core.arrays.categorical import contains

from qgis.core import (
    Qgis,
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsFields,
    QgsField,
    QgsVectorFileWriter,
    QgsCoordinateReferenceSystem,
    QgsProcessingFeatureSourceDefinition,
    QgsVectorDataProvider,
    QgsWkbTypes,
    QgsPolygon,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessing,
    edit
)
from qgis.PyQt.QtCore import QVariant, QMetaType
from qgis import processing
from .system_utils import save_temp_layer_to_gpkg
from .message import msg
from .logger import Logger
import os
from shapely.geometry import LineString, MultiLineString

Logger = Logger()


def polyline2(array_of_lines, output_path, output_format="shp"):
    """
    :param array_of_lines: Array of tuples where each tuple contains two points and a length value
                           [("x1", "y1", "x2", "y2", "Shape_Len")].
    :param output_path: Path to save the output file (shapefile or GeoPackage).
    :param output_format: Format of the output file ("shp" for shapefile, "gpkg" for GeoPackage).
    :return: Path to the created polyline file.

    - Creates a polyline file with the given array of lines and length field.
    """

    # Define the fields for the layer
    fields = QgsFields()
    fields.append(QgsField("x1", QMetaType.Double))
    fields.append(QgsField("y1", QMetaType.Double))
    fields.append(QgsField("x2", QMetaType.Double))
    fields.append(QgsField("y2", QMetaType.Double))
    fields.append(QgsField("Shape_Len", QMetaType.Double))

    # Create a memory layer to build the features
    layer = QgsVectorLayer("LineString?crs=EPSG:4326", "PolylineLayer", "memory")
    if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
        layer.dataProvider().createSpatialIndex()
    else:
        Logger.log("Räumlicher Index kann nicht erstellt werden.", 'CRITICAL')
    provider = layer.dataProvider()

    # Add fields to the layer
    provider.addAttributes(fields)
    layer.updateFields()

    # Create features from the array of lines
    for line in array_of_lines:
        x1, y1 = line[0]
        x2, y2 = line[1]
        shape_len = line[2] if len(line) > 2 and line[2] is not None else 0

        # Create a new feature
        feature = QgsFeature()

        # Define geometry as a line from point 1 to point 2
        geometry = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
        feature.setGeometry(geometry)

        # Set attribute values
        feature.setAttributes([x1, y1, x2, y2, shape_len])

        # Add the feature to the layer
        provider.addFeature(feature)

    # Save the layer to the specified output format
    if output_format.lower() == "gpkg":
        QgsVectorFileWriter.writeAsVectorFormat(
            layer, output_path, "utf-8", layer.crs(), "GPKG"
        )
    else:  # Default to ESRI Shapefile
        QgsVectorFileWriter.writeAsVectorFormat(
            layer, output_path, "utf-8", layer.crs(), "ESRI Shapefile"
        )

    return output_path

# Example usage (uncomment and customize):
# result = Polyline2([
#     [(0, 0), (1, 1), 1.414],
#     [(2, 2), (3, 3), 1.414]
# ], "polyline2.gpkg", output_format="gpkg")
# print(f"File created at: {result}")


def check_projection(SpatialReference, inputlist):
    # Ziel-Koordinatenreferenzsystem
    sr_i = SpatialReference

    for f in inputlist:
        # Prüfen, ob die Datei existiert
        if not os.path.exists(f):
            Logger.log("Alert: File {} does not exist!".format(f), level=Qgis.Critical)
            continue

        # Laden der Datei als Layer
        layer = QgsVectorLayer(f, os.path.basename(f), "ogr")

        if not layer.isValid():
            Logger.log("Alert: Unable to load file {} as a valid layer!".format(f), level=Qgis.Critical)
            continue
        if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
            layer.dataProvider().createSpatialIndex()
        else:
            Logger.log("Räumlicher Index kann nicht erstellt werden.", 'CRITICAL')

        # Abrufen des Koordinatenreferenzsystems des Layers
        sr_f = layer.crs()

        if sr_i.authid() != sr_f.authid():
            Logger.log("Alert: Projection of {} is not {}, but {}!".format(f, sr_i.authid(), sr_f.authid() ), level=Qgis.Critical)


def load_to_geopackage(input_layer, output_path, layer_name, SpatialReference):
    """
    Lädt einen Eingabelayer in ein GeoPackage.

    :param input_layer: Pfad oder Quelldaten des Eingabelayers.
    :param layer_name: Name des Layers im GeoPackage.
    :return: True bei Erfolg, False bei Fehler.
    """

    # Alte Datei entfernen, falls sie existiert
    if os.path.exists(output_path):
        os.remove(output_path)

    # Eingabelayer laden
    layer = QgsVectorLayer(input_layer, layer_name, "ogr")
    if not layer.isValid():
        Logger.log("Fehler: {} konnte nicht geladen werden.".format(input_layer), level=Qgis.Critical)
        return False

    if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
        layer.dataProvider().createSpatialIndex()
    else:
        Logger.log("Räumlicher Index kann nicht erstellt werden.", 'CRITICAL')

    # Optionen für den GeoPackage-Export festlegen
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"
    options.destinationCrs = SpatialReference

    # Schreiben des Layers in das GeoPackage
    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        output_path,
        QgsProject.instance().transformContext(),
        options
    )
    '''
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError("Fehler beim Schreiben in GeoPackage: {}".format(str(error)))
    else:
       msg(f"Layer '{layer_name}' erfolgreich zu '{output_path}' hinzugefügt.")
    '''
    return layer

def split_layer_by_attribute(input_layer_path, attribute_name, output_folder):
    """
    Split a vector layer into multiple layers based on unique values of an attribute.

    Parameters:
        input_layer_path (str): Path to the input vector layer (e.g., a Shapefile).
        attribute_name (str): Name of the attribute to split the layer by.
        output_folder (str): Path to the folder where the split layers will be saved.

    Returns:
        None
    """
    # Lade die Eingabedaten
    layer = QgsVectorLayer(input_layer_path, "InputLayer", "ogr")
    if not layer.isValid():
        raise Exception("Layer konnte nicht geladen werden!")
    if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
        layer.dataProvider().createSpatialIndex()
    else:
        Logger.log("Räumlicher Index kann nicht erstellt werden.", 'CRITICAL')

    # Erstelle das Verzeichnis für die Ausgabedateien, falls es noch nicht existiert
    os.makedirs(output_folder, exist_ok=True)

    # Hole alle eindeutigen Werte im Attributfeld
    if attribute_name not in [field.name() for field in layer.fields()]:
        raise Exception(f"Attribut '{attribute_name}' existiert nicht im Layer!")

    unique_values = layer.uniqueValues(layer.fields().indexFromName(attribute_name))

    # Splitte die Ebene nach Attributwerten
    for value in unique_values:
        # Filtere die Features für den aktuellen Attributwert
        query = "{} = {}".format(attribute_name, value)
        subset_layer = layer.materialize(QgsProcessingFeatureSourceDefinition(query))

        # Exportiere die gefilterte Ebene als neue Datei
        output_path = os.path.join(output_folder, f"{value}.shp")
        QgsVectorFileWriter.writeAsVectorFormat(
            subset_layer,
            output_path,
            "UTF-8",
            layer.crs(),
            "ESRI Shapefile"
        )

    print("Aufteilung abgeschlossen!")

    # Beispielaufruf der Funktion
    # split_layer_by_attribute("path_to_input_layer.shp", "NAME", "path_to_output_folder")

def select_and_save_by_location(input_layer, intersect_layer, predicate=None, method=0, output='TEMPORARY_OUTPUT'):
    """
    Führt eine Auswahl von Features auf Basis ihrer räumlichen Lage durch und speichert die ausgewählten Features.

    :param input_layer: Das Layer, auf das die Auswahl angewendet wird (z. B. 'INPUT').
    :param predicate: Ein Listentyp, der die räumliche Beziehung definiert (z. B. [0] für Überschneidet).
    :param intersect_layer: Das Layer, mit dem die räumliche Beziehung analysiert wird.
    :param method: Die Auswahlmethode (z. B. 0 für 'Neue Auswahl erstellen').
    :param output: Der Speicherort für die ausgewählten Features (Standard: 'TEMPORARY_OUTPUT').
    :return: Das Ergebnis-Layer mit den ausgewählten Features.
    """
    # Auswahl nach räumlicher Lage durchführen
    if predicate is None:
        predicate = [0]
    processing.run("native:selectbylocation", {
        'INPUT': input_layer,
        'PREDICATE': predicate,
        'INTERSECT': intersect_layer,
        'METHOD': method
    })

    # Ausgewählte Features speichern
    selected_features = processing.run(
        "native:saveselectedfeatures", {
            'INPUT': input_layer,
            'OUTPUT': output
        })['OUTPUT']

    return selected_features


def create_polygons_from_lines(input_layer, output_layer_name="Polygons_from_Lines"):
    """
    Convert connected line features into polygons in QGIS.

    Args:
        input_layer (QgsVectorLayer): The input layer containing line features.
        output_layer_name (str): Name of the output layer.
    """
    if not input_layer or input_layer.geometryType() != QgsWkbTypes.LineGeometry:
        raise ValueError("Input layer must be a valid line geometry layer.")

    # Create an output layer to store polygons
    crs = input_layer.crs().toWkt()
    output_layer = QgsVectorLayer(f"Polygon?crs={crs}", output_layer_name, "memory")
    provider = output_layer.dataProvider()

    # Add attributes from the input layer
    provider.addAttributes(input_layer.fields())
    output_layer.updateFields()

    # Group geometries to form polygons
    line_geometries = [feat.geometry() for feat in input_layer.getFeatures()]
    polygons = []
    used_lines = set()

    for i, geom1 in enumerate(line_geometries):
        if i in used_lines:
            continue

        # Start building a potential polygon
        current_ring = geom1.asMultiPolyline() if geom1.isMultipart() else [geom1.asPolyline()]
        ring_closed = False

        for j, geom2 in enumerate(line_geometries):
            if i == j or j in used_lines:
                continue

            for line1 in current_ring:
                for line2 in geom2.asMultiPolyline() if geom2.isMultipart() else [geom2.asPolyline()]:
                    if line1[-1] == line2[0]:  # Check if lines are connected
                        current_ring.append(line2)
                        break
                    elif line1[-1] == line2[-1]:  # Reverse if necessary
                        current_ring.append(line2[::-1])
                        break

            # Check if the ring is closed
            if current_ring[0][0] == current_ring[-1][-1]:
                ring_closed = True
                used_lines.add(j)
                break

        if ring_closed:
            polygon_geom = QgsGeometry.fromPolygonXY([QgsPointXY(p) for line in current_ring for p in line])
            polygons.append(polygon_geom)
            used_lines.add(i)

    # Add polygons to the output layer
    for polygon in polygons:
        new_feature = QgsFeature(output_layer.fields())
        new_feature.setGeometry(polygon)
        provider.addFeatures([new_feature])

    # Add the output layer to the project

    print(f"{len(polygons)} polygons created and added to {output_layer_name} layer.")

    return output_layer

# Usage example
#input_layer = iface.activeLayer()  # Use the active layer in QGIS
#create_polygons_from_lines(input_layer)

def extract_polygons_from_lines(line_layer, output_layer_name="Extracted Polygons"):
    """
    Extrahiert Polygone aus einem Liniennetzwerk in QGIS.

    :param line_layer: QgsVectorLayer mit Liniengeometrien.
    :param output_layer_name: Name des Ausgabe-Polygon-Layers.
    :return: QgsVectorLayer mit extrahierten Polygonen.
    """
    if line_layer.geometryType() != QgsWkbTypes.LineGeometry:
        raise ValueError("Die Eingabeebene muss Liniengeometrien enthalten.")

    # Erstelle einen leeren ungerichteten Graphen
    G = nx.Graph()

    # Füge Kanten zum Graphen hinzu basierend auf den Liniensegmenten
    for feature in line_layer.getFeatures():
        geom = feature.geometry()
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
        else:
            lines = [geom.asPolyline()]

        for line in lines:
            for i in range(len(line) - 1):
                start_point = (line[i].x(), line[i].y())
                end_point = (line[i + 1].x(), line[i + 1].y())
                G.add_edge(start_point, end_point)

    # Finde alle einfachen Zyklen im Graphen
    cycles = list(nx.simple_cycles(G.to_directed()))

    # Erstelle einen neuen Polygon-Layer im Speicher
    polygon_layer = QgsVectorLayer(
        "Polygon?crs={}".format(line_layer.crs().authid()), output_layer_name, "memory"
    )
    provider = polygon_layer.dataProvider()
    provider.addAttributes([QgsField("id", QMetaType.Int)])
    polygon_layer.updateFields()

    # Füge die gefundenen Zyklen als Polygone hinzu
    for idx, cycle in enumerate(cycles):
        # Erstelle eine Liste von QgsPointXY-Objekten
        points = [QgsPointXY(x, y) for x, y in cycle]
        # Schließe das Polygon, indem der erste Punkt erneut hinzugefügt wird
        if points[0] != points[-1]:
            points.append(points[0])
        polygon = QgsGeometry.fromPolygonXY([points])

        feature = QgsFeature()
        feature.setGeometry(polygon)
        feature.setAttributes([idx])
        provider.addFeature(feature)

    # Füge den neuen Layer zum aktuellen QGIS-Projekt hinzu
    QgsProject.instance().addMapLayer(polygon_layer)

    return polygon_layer


def shp_area(layer, area_field='Area'):
    """Adds shape area field to file"""

    if not layer.isValid():
        raise Exception(f"Layer {layer} is not valid")

    if area_field not in [field.name() for field in layer.fields()]:
        layer.dataProvider().addAttributes([QgsField(area_field, QMetaType.Double)])
        layer.updateFields()

    layer = processing.run("native:fieldcalculator",
                   {'INPUT': layer,
                    'FIELD_NAME': area_field,
                    'FIELD_TYPE': 0,
                    'FIELD_LENGTH': 0,
                    'FIELD_PRECISION': 0,
                    'FORMULA': ' $area ',
                    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                    })['OUTPUT']
    return layer


def shp_area2(layer, field_name="Area", logger=None):
    """
    Berechnet die Flächen (Area) für jede Geometrie in einem angegebenen Layer
    und speichert die Werte in einem neuen Feld.

    :param layer: (QgsVectorLayer) Der Eingabe-Layer, dessen Geometrien verarbeitet werden sollen.
    :param field_name: (str) Der Name des Feldes, in dem die Fläche gespeichert wird. Standard ist "Area".
    :param logger: (Logger) Optionales Logger-Objekt (z.B. für Debugging und Fehlerprotokollierung).
    :return: (bool) True, wenn die Operation erfolgreich abgeschlossen wurde, False im Fehlerfall.
    """

    #shp_area2(layer, logger=Logger) mit Logging

    # Überprüfen, ob der Layer gültig ist
    if not layer.isValid():
        if logger:
            logger.log(f"Layer '{layer.name()}' ist ungültig.", level="ERROR")
        return False

    # Überprüfen, ob das Feld bereits existiert
    field_names = [field.name() for field in layer.fields()]
    if field_name not in field_names:
        # Neues Feld hinzufügen
        layer_provider = layer.dataProvider()
        layer_provider.addAttributes([QgsField(field_name, QMetaType.Double)])
        layer.updateFields()
    else:
        if logger:
            logger.log(f"Das Feld '{field_name}' existiert bereits.", level="WARNING")

    # Geometrien iterieren und Flächen berechnen
    try:
        with edit(layer):
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                if geometry and geometry.isGeosValid():
                    # Fläche berechnen und setzen
                    area = geometry.area()
                    feature[field_name] = area
                    layer.updateFeature(feature)
                else:
                    if logger:
                        logger.log(f"Ungültige Geometrie in Feature ID: {feature.id()}. Überspringe Feature.",
                                   level="WARNING")

        if logger:
            logger.log(f"Flächenberechnung erfolgreich für Layer '{layer.name()}'.", level="INFO")
        return True

    except Exception as e:
        if logger:
            logger.log(f"Fehler bei der Flächenberechnung: {str(e)}", level="ERROR")
        return False


def shp_length(layer, Fieldname='Length'):
    """Adds length field to file"""

    if not layer.isValid():
        raise Exception(f"Layer {layer} is not valid")

    if Fieldname not in [field.name() for field in layer.fields()]:
        layer.dataProvider().addAttributes([QgsField(Fieldname, QMetaType.Double)])
        layer.updateFields()

    layer = processing.run("native:fieldcalculator",
                   {'INPUT': layer,
                    'FIELD_NAME': 'length',
                    'FIELD_TYPE': 0,
                    'FIELD_LENGTH': 0,
                    'FIELD_PRECISION': 0,
                    'FORMULA': ' $length',
                    'OUTPUT': 'TEMPORARY_OUTPUT'})
    return layer['OUTPUT']


def create_empty_layer(layer_name: str, layer_type: str, crs: str):
    """
    Creates an empty layer with a specified geometry type and CRS.

    :param layer_type: The geometry type of the layer (e.g., "Polygon", "LineString", "Point").
    :param crs: The coordinate reference system for the layer as a string.
    :return: QgsVectorLayer object
    """
    layer = QgsVectorLayer(f"{layer_type}?crs={crs}", layer_name, "memory")
    layer_data_provider = layer.dataProvider()

    # Add required fields to the layer if needed
    layer_data_provider.addAttributes([
        QgsField("id", QMetaType.Int),  # Example attribute field
        QgsField("name", QMetaType.QString)  # Add more fields as required
    ])
    layer.updateFields()
    return layer


def create_linestring_layer_from_array(data, crs, layer_name):
    """
    Erstellt einen temporären QgsVectorLayer vom Typ LineString
    aus einer Liste von Liniensegmenten.

    Parameters:
        data (list): Liste der Form [[[x1, y1], [x2, y2], weight], ...]
        crs (str oder QgsCoordinateReferenceSystem): z. B. "EPSG:25833"
        layer_name (str): Name des temporären Layers

    Returns:
        QgsVectorLayer: Ein gültiger Linienlayer
    """
    layer = QgsVectorLayer("LineString?crs={}".format(crs.toWkt()), layer_name, "memory")
    prov = layer.dataProvider()

    # Optional: Attribut für Gewicht hinzufügen
    prov.addAttributes([QgsField("weight", QMetaType.Double)])
    layer.updateFields()

    features = []
    for segment in data:
        if len(segment) < 2:
            continue

        p1_coords, p2_coords = segment[0], segment[1]
        weight = segment[2] if len(segment) > 2 else None

        line = QgsGeometry.fromPolylineXY([
            QgsPointXY(p1_coords[0], p1_coords[1]),
            QgsPointXY(p2_coords[0], p2_coords[1])
        ])

        feat = QgsFeature()
        feat.setGeometry(line)
        feat.setAttributes([weight])
        features.append(feat)

    prov.addFeatures(features)
    layer.updateExtents()
    return layer

def nodes_detect(input_road_network, count):
    """
    QGIS-Portierung der ArcPy-Funktion NodesDetect mit Join_Count beim Zusammenführen von Punkten.
    """

    # 1. Endpunkte extrahieren
    vertices = processing.run("native:extractspecificvertices",{
        'INPUT': input_road_network,
        'VERTICES': '0, -1',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    # 2. X/Y hinzufügen, falls nicht vorhanden
    vertices = processing.run("qgis:fieldcalculator", {
        'INPUT': vertices,
        'FIELD_NAME': 'x-coord',
        'FIELD_TYPE': 0,
        'FIELD_PRECISION': 10,
        'NEW_FIELD': True,
        'FORMULA': 'x($geometry)',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    vertices = processing.run("native:aggregate", {
        'INPUT': vertices,
        'GROUP_BY': '"x-coord"',
        'AGGREGATES': [{'aggregate': 'count', 'delimiter': ',', 'input': '"x-coord"', 'length': 10, 'name': 'x-coord',
             'precision': 3, 'sub_type': 0, 'type': 6, 'type_name': 'double precision'}],
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    filtered = processing.run("native:extractbyattribute", {
        'INPUT': vertices,
        'FIELD': 'x-coord',
        'OPERATOR': 0,
        'VALUE': count,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    return filtered


def get_hole_polygons(layer1, layer2):
    """
    Gibt einen neuen Layer mit allen Polygonen aus layer1 zurück, die nicht in layer2 enthalten sind.
    """
    all_features_layer1 = list(layer1.getFeatures())
    all_features_layer2 = list(layer2.getFeatures())
    hole_features = []

    for feat1 in all_features_layer1:
        geom1 = feat1.geometry()
        is_isolated = True

        for feat2 in all_features_layer2:
            geom2 = feat2.geometry()

            # Prüfe, ob geom1 in geom2 geschnitten oder enthalten ist
            if  geom1.within(geom2):
                is_isolated = False
                break

        if is_isolated:
            hole_features.append(feat1)

    # Erstellen eines neuen Layers für die isolierten Features
    crs = layer1.crs().toWkt()
    hole_layer = QgsVectorLayer(f"Polygon?crs={crs}", "Isolated Polygons", "memory")
    provider = hole_layer.dataProvider()
    provider.addAttributes(layer1.fields())
    hole_layer.updateFields()

    provider.addFeatures(hole_features)
    hole_layer.updateExtents()

    return hole_layer
