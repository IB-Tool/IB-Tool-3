import os
import networkx as nx

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsFields,
    QgsField,
    QgsVectorFileWriter,
    QgsVectorDataProvider,
    QgsWkbTypes,
    QgsProcessingFeatureSourceDefinition,
    QgsProcessing,
    edit,
)
from qgis.PyQt.QtCore import QMetaType
from qgis import processing

from .logger import Logger


# ── Module-level constants ─────────────────────────────────────────────────────
INTERSECT_BUFFER_DISTANCE = 70  # Buffer distance in meters for polygon intersection analysis


def polyline2(array_of_lines, output_path, output_format="shp"):
    """Create a polyline file from an array of line segments.

    Args:
        array_of_lines: List of tuples, each containing two points and a length
            value in the format [((x1, y1), (x2, y2), shape_len), ...].
        output_path: Path to save the output file (shapefile or GeoPackage).
        output_format: Format of the output file. Use "shp" for ESRI Shapefile
            (default) or "gpkg" for GeoPackage.

    Returns:
        Path to the created polyline file.
    """
    fields = QgsFields()
    fields.append(QgsField("x1", QMetaType.Double))
    fields.append(QgsField("y1", QMetaType.Double))
    fields.append(QgsField("x2", QMetaType.Double))
    fields.append(QgsField("y2", QMetaType.Double))
    fields.append(QgsField("Shape_Len", QMetaType.Double))

    layer = QgsVectorLayer("LineString?crs=EPSG:4326", "PolylineLayer", "memory")
    if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
        layer.dataProvider().createSpatialIndex()
    else:
        Logger.log("Spatial index could not be created.", level='CRITICAL')
    provider = layer.dataProvider()

    provider.addAttributes(fields)
    layer.updateFields()

    for line in array_of_lines:
        x1, y1 = line[0]
        x2, y2 = line[1]
        shape_len = line[2] if len(line) > 2 and line[2] is not None else 0

        feature = QgsFeature()
        geometry = QgsGeometry.fromPolylineXY([QgsPointXY(x1, y1), QgsPointXY(x2, y2)])
        feature.setGeometry(geometry)
        feature.setAttributes([x1, y1, x2, y2, shape_len])
        provider.addFeature(feature)

    if output_format.lower() == "gpkg":
        QgsVectorFileWriter.writeAsVectorFormat(
            layer, output_path, "utf-8", layer.crs(), "GPKG"
        )
    else:
        QgsVectorFileWriter.writeAsVectorFormat(
            layer, output_path, "utf-8", layer.crs(), "ESRI Shapefile"
        )

    return output_path


def check_projection(spatial_reference, inputlist):
    """Check that all layers in inputlist match the expected CRS.

    Args:
        spatial_reference: Target QgsCoordinateReferenceSystem.
        inputlist: List of file paths to check.
    """
    for f in inputlist:
        if not os.path.exists(f):
            Logger.log(f"Alert: File {f} does not exist!", level="CRITICAL")
            continue

        layer = QgsVectorLayer(f, os.path.basename(f), "ogr")

        if not layer.isValid():
            Logger.log(f"Alert: Unable to load file {f} as a valid layer!", level="CRITICAL")
            continue
        if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
            layer.dataProvider().createSpatialIndex()
        else:
            Logger.log("Spatial index could not be created.", level='CRITICAL')

        layer_crs = layer.crs()

        if spatial_reference.authid() != layer_crs.authid():
            actual_crs = layer_crs.authid() if layer_crs.authid() else "undefined/unknown"
            Logger.log(
                f"Alert: Projection of {f} is not {spatial_reference.authid()}, "
                f"but {actual_crs}!",
                level="CRITICAL",
            )


def load_to_geopackage(input_layer, output_path, layer_name, spatial_reference):
    """Load an input layer into a GeoPackage file.

    Args:
        input_layer: Path or source data of the input layer.
        output_path: Path to the output GeoPackage file.
        layer_name: Name of the layer within the GeoPackage.
        spatial_reference: Coordinate reference system for the layer.

    Returns:
        QgsVectorLayer on success.

    Raises:
        Exception: If the input layer cannot be loaded.
    """
    if os.path.exists(output_path):
        os.remove(output_path)

    layer = QgsVectorLayer(input_layer, layer_name, "ogr")
    if not layer.isValid():
        error_msg = f"Error: {input_layer} could not be loaded."
        Logger.log(error_msg, level="CRITICAL")
        raise Exception(error_msg)

    if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
        layer.dataProvider().createSpatialIndex()
    else:
        Logger.log("Spatial index could not be created.", level='CRITICAL')

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"
    options.destinationCrs = spatial_reference

    QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        output_path,
        QgsProject.instance().transformContext(),
        options
    )

    return layer


def split_layer_by_attribute(
    input_layer_path: str,
    attribute_name: str,
    output_folder: str,
) -> None:
    """Split a vector layer into multiple layers based on unique attribute values.

    Args:
        input_layer_path: Path to the input vector layer (e.g., a Shapefile).
        attribute_name: Name of the attribute to split the layer by.
        output_folder: Path to the folder where the split layers will be saved.
    """
    layer = QgsVectorLayer(input_layer_path, "InputLayer", "ogr")
    if not layer.isValid():
        raise Exception("Layer could not be loaded!")
    if layer.dataProvider().capabilities() & QgsVectorDataProvider.CreateSpatialIndex:
        layer.dataProvider().createSpatialIndex()
    else:
        Logger.log("Spatial index could not be created.", level='CRITICAL')

    os.makedirs(output_folder, exist_ok=True)

    if attribute_name not in [field.name() for field in layer.fields()]:
        raise Exception(f"Attribute '{attribute_name}' does not exist in layer!")

    unique_values = layer.uniqueValues(layer.fields().indexFromName(attribute_name))

    for value in unique_values:
        query = "{} = {}".format(attribute_name, value)
        subset_layer = layer.materialize(QgsProcessingFeatureSourceDefinition(query))

        output_path = os.path.join(output_folder, f"{value}.shp")
        QgsVectorFileWriter.writeAsVectorFormat(
            subset_layer,
            output_path,
            "UTF-8",
            layer.crs(),
            "ESRI Shapefile"
        )

    Logger.log("Split complete.", level="INFO")


def select_and_save_by_location(
    input_layer,
    intersect_layer,
    predicate=None,
    method=0,
    output='TEMPORARY_OUTPUT',
):
    """Select features by spatial relationship and save the selection.

    Args:
        input_layer: The layer to apply the selection to.
        intersect_layer: The layer used to define the spatial relationship.
        predicate: List defining the spatial relationship (e.g., [0] for
            intersects). Defaults to [0].
        method: Selection method (e.g., 0 for 'create new selection').
        output: Output location for selected features. Defaults to
            'TEMPORARY_OUTPUT'.

    Returns:
        Output layer containing the selected features.
    """
    if predicate is None:
        predicate = [0]
    processing.run("native:selectbylocation", {
        'INPUT': input_layer,
        'PREDICATE': predicate,
        'INTERSECT': intersect_layer,
        'METHOD': method
    })

    selected_features = processing.run(
        "native:saveselectedfeatures",
        {'INPUT': input_layer,
         'OUTPUT': output
         })['OUTPUT']

    return selected_features


def create_polygons_from_lines(input_layer, output_layer_name="Polygons_from_Lines"):
    """Convert connected line features into polygons.

    Args:
        input_layer: QgsVectorLayer containing line features.
        output_layer_name: Name of the output layer.

    Returns:
        QgsVectorLayer containing the created polygons.
    """
    if not input_layer or input_layer.geometryType() != QgsWkbTypes.LineGeometry:
        raise ValueError("Input layer must be a valid line geometry layer.")

    crs = input_layer.crs().toWkt()
    output_layer = QgsVectorLayer(f"Polygon?crs={crs}", output_layer_name, "memory")
    provider = output_layer.dataProvider()

    provider.addAttributes(input_layer.fields())
    output_layer.updateFields()

    line_geometries = [feat.geometry() for feat in input_layer.getFeatures()]
    polygons = []
    used_lines = set()

    for i, geom1 in enumerate(line_geometries):
        if i in used_lines:
            continue

        current_ring = geom1.asMultiPolyline() if geom1.isMultipart() else [geom1.asPolyline()]
        ring_closed = False

        for j, geom2 in enumerate(line_geometries):
            if i == j or j in used_lines:
                continue

            for line1 in current_ring:
                for line2 in geom2.asMultiPolyline() if geom2.isMultipart() else [geom2.asPolyline()]:
                    if line1[-1] == line2[0]:
                        current_ring.append(line2)
                        break
                    elif line1[-1] == line2[-1]:
                        current_ring.append(line2[::-1])
                        break

            if current_ring[0][0] == current_ring[-1][-1]:
                ring_closed = True
                used_lines.add(j)
                break

        if ring_closed:
            polygon_geom = QgsGeometry.fromPolygonXY(
                [QgsPointXY(p) for line in current_ring for p in line]
            )
            polygons.append(polygon_geom)
            used_lines.add(i)

    for polygon in polygons:
        new_feature = QgsFeature(output_layer.fields())
        new_feature.setGeometry(polygon)
        provider.addFeatures([new_feature])

    Logger.log(
        f"{len(polygons)} polygons created and added to '{output_layer_name}' layer.",
        level="INFO",
    )

    return output_layer


def extract_polygons_from_lines(line_layer, output_layer_name="Extracted Polygons"):
    """Extract polygons from a line network using cycle detection.

    Builds an undirected graph from line segments, detects all simple cycles,
    and creates a polygon layer from the detected cycles.

    Args:
        line_layer: QgsVectorLayer containing line geometries.
        output_layer_name: Name of the output polygon layer.

    Returns:
        QgsVectorLayer containing the extracted polygons.
    """
    if line_layer.geometryType() != QgsWkbTypes.LineGeometry:
        raise ValueError("The input layer must contain line geometries.")

    graph = nx.Graph()

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
                graph.add_edge(start_point, end_point)

    cycles = list(nx.simple_cycles(graph.to_directed()))

    polygon_layer = QgsVectorLayer(
        "Polygon?crs={}".format(line_layer.crs().authid()), output_layer_name, "memory"
    )
    provider = polygon_layer.dataProvider()
    provider.addAttributes([QgsField("id", QMetaType.Int)])
    polygon_layer.updateFields()

    for idx, cycle in enumerate(cycles):
        points = [QgsPointXY(x, y) for x, y in cycle]
        if points[0] != points[-1]:
            points.append(points[0])
        polygon = QgsGeometry.fromPolygonXY([points])

        feature = QgsFeature()
        feature.setGeometry(polygon)
        feature.setAttributes([idx])
        provider.addFeature(feature)

    QgsProject.instance().addMapLayer(polygon_layer)

    return polygon_layer


def shp_area(layer, area_field='Area'):
    """Add a shape area field to a layer using the field calculator.

    Args:
        layer: QgsVectorLayer to process.
        area_field: Name of the area field to add. Defaults to 'Area'.

    Returns:
        QgsVectorLayer with the area field added.
    """
    if not layer.isValid():
        raise Exception(f"Layer {layer} is not valid")

    if area_field not in [field.name() for field in layer.fields()]:
        layer.dataProvider().addAttributes([QgsField(area_field, QMetaType.Double)])
        layer.updateFields()

    layer = processing.run(
        "native:fieldcalculator",
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
    """Calculate and store the area of each geometry in a layer.

    Iterates over all features in the layer and writes the computed geometry
    area to the specified field. The field is added if it does not already
    exist.

    Args:
        layer: QgsVectorLayer whose geometries will be processed.
        field_name: Name of the field to store the area. Defaults to "Area".
        logger: Optional Logger instance for debug output.

    Returns:
        True if successful, False on error.
    """
    if not layer.isValid():
        if logger:
            logger.log(f"Layer '{layer.name()}' is invalid.", level="ERROR")
        return False

    field_names = [field.name() for field in layer.fields()]
    if field_name not in field_names:
        layer_provider = layer.dataProvider()
        layer_provider.addAttributes([QgsField(field_name, QMetaType.Double)])
        layer.updateFields()
    else:
        if logger:
            logger.log(f"Field '{field_name}' already exists.", level="WARNING")

    try:
        with edit(layer):
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                if geometry and geometry.isGeosValid():
                    area = geometry.area()
                    feature[field_name] = area
                    layer.updateFeature(feature)
                else:
                    if logger:
                        logger.log(
                            f"Invalid geometry in feature ID: {feature.id()}. Skipping feature.",
                            level="WARNING",
                        )

        if logger:
            logger.log(
                f"Area calculation successful for layer '{layer.name()}'.", level="INFO"
            )
        return True

    except Exception as e:
        if logger:
            logger.log(f"Error during area calculation: {str(e)}", level="ERROR")
        return False


def shp_length(layer, field_name='Length'):
    """Add a length field to a layer using the field calculator.

    Args:
        layer: QgsVectorLayer to process.
        field_name: Name of the length field to add. Defaults to 'Length'.

    Returns:
        QgsVectorLayer with the length field added.
    """
    if not layer.isValid():
        raise Exception(f"Layer {layer} is not valid")

    if field_name not in [field.name() for field in layer.fields()]:
        layer.dataProvider().addAttributes([QgsField(field_name, QMetaType.Double)])
        layer.updateFields()

    layer = processing.run(
        "native:fieldcalculator",
        {'INPUT': layer,
         'FIELD_NAME': 'length',
         'FIELD_TYPE': 0,
         'FIELD_LENGTH': 0,
         'FIELD_PRECISION': 0,
         'FORMULA': ' $length',
         'OUTPUT': 'TEMPORARY_OUTPUT'})
    return layer['OUTPUT']


def create_empty_layer(layer_name: str, layer_type: str, crs: str) -> QgsVectorLayer:
    """Create an empty layer with a specified geometry type and CRS.

    Args:
        layer_name: Name of the new layer.
        layer_type: Geometry type of the layer (e.g., "Polygon", "LineString",
            "Point").
        crs: Coordinate reference system as a string (e.g., "EPSG:25832").

    Returns:
        QgsVectorLayer with default 'id' and 'name' fields.
    """
    layer = QgsVectorLayer(f"{layer_type}?crs={crs}", layer_name, "memory")
    layer_data_provider = layer.dataProvider()

    layer_data_provider.addAttributes([
        QgsField("id", QMetaType.Int),
        QgsField("name", QMetaType.QString)
    ])
    layer.updateFields()
    return layer


def create_linestring_layer_from_array(data, crs, layer_name):
    """Create a temporary LineString QgsVectorLayer from a list of line segments.

    Args:
        data: List of segments in the format
            [[[x1, y1], [x2, y2], weight], ...].
        crs: QgsCoordinateReferenceSystem or string, e.g. "EPSG:25833".
        layer_name: Name of the temporary layer.

    Returns:
        QgsVectorLayer: A valid line layer.
    """
    layer = QgsVectorLayer("LineString?crs={}".format(crs.toWkt()), layer_name, "memory")
    prov = layer.dataProvider()

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
    """Detect road network nodes with a specific connection count.

    QGIS port of the ArcPy NodesDetect function. Extracts endpoints from
    the road network, aggregates by X coordinate, and returns only those
    nodes matching the specified connection count.

    Args:
        input_road_network: QgsVectorLayer containing road line features.
        count: Target connection count to filter nodes by.

    Returns:
        QgsVectorLayer containing filtered network nodes.
    """
    vertices = processing.run("native:extractspecificvertices", {
        'INPUT': input_road_network,
        'VERTICES': '0, -1',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

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
        'AGGREGATES': [{
            'aggregate': 'count', 'delimiter': ',', 'input': '"x-coord"',
            'length': 10, 'name': 'x-coord', 'precision': 3,
            'sub_type': 0, 'type': 6, 'type_name': 'double precision',
        }],
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
    """Return polygons from layer1 that are not contained within any polygon in layer2.

    Args:
        layer1: QgsVectorLayer — source polygons.
        layer2: QgsVectorLayer — reference polygons used for containment check.

    Returns:
        QgsVectorLayer containing isolated (hole) polygons.
    """
    all_features_layer1 = list(layer1.getFeatures())
    all_features_layer2 = list(layer2.getFeatures())
    hole_features = []

    for feat1 in all_features_layer1:
        geom1 = feat1.geometry()
        is_isolated = True

        for feat2 in all_features_layer2:
            geom2 = feat2.geometry()

            if geom1.within(geom2):
                is_isolated = False
                break

        if is_isolated:
            hole_features.append(feat1)

    crs = layer1.crs().toWkt()
    hole_layer = QgsVectorLayer(f"Polygon?crs={crs}", "Isolated Polygons", "memory")
    provider = hole_layer.dataProvider()
    provider.addAttributes(layer1.fields())
    hole_layer.updateFields()

    provider.addFeatures(hole_features)
    hole_layer.updateExtents()

    return hole_layer


def intersect_polygons(input_polygon):
    """Identify and extract intersecting polygons from an input polygon layer.

    Buffers the input polygons by ``INTERSECT_BUFFER_DISTANCE`` meters,
    converts them to lines, polygonizes the result, and returns only those
    polygons that contain more than one centroid (i.e., intersecting polygons).

    Args:
        input_polygon: QgsVectorLayer — the input polygon layer to process.

    Returns:
        QgsVectorLayer containing intersecting polygons.
    """
    input_clean = processing.run("native:deleteduplicategeometries", {
        'INPUT': input_polygon,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    input_buff = processing.run("native:buffer", {
        'INPUT': input_clean,
        'DISTANCE': INTERSECT_BUFFER_DISTANCE, 'SEGMENTS': 5, 'END_CAP_STYLE': 0, 'JOIN_STYLE': 0,
        'MITER_LIMIT': 2, 'DISSOLVE': False, 'SEPARATE_DISJOINT': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    input_lines = processing.run("native:polygonstolines", {
        'INPUT': input_buff,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
    })['OUTPUT']

    input_lines_poly = processing.run("native:polygonize", {
        'INPUT': input_lines,
        'KEEP_FIELDS': False,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']

    lines_poly_union = processing.run("native:union", {
        'INPUT': input_lines_poly,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        'GRID_SIZE': None
    })['OUTPUT']

    centroides = processing.run("native:centroids", {
        'INPUT': lines_poly_union,
        'ALL_PARTS': False,
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    input_lines_poly_count = processing.run("native:countpointsinpolygon", {
        'POLYGONS': input_lines_poly,
        'POINTS': centroides,
        'WEIGHT': '',
        'CLASSFIELD': '',
        'FIELD': 'NUMPOINTS',
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    intersect_poly = processing.run("native:extractbyattribute", {
        'INPUT': input_lines_poly_count,
        'FIELD': 'NUMPOINTS', 'OPERATOR': 2, 'VALUE': '1',
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })['OUTPUT']

    return intersect_poly
