# coding=utf-8
"""Unit tests for helpers.data_loader"""

import os
import tempfile
import unittest
from unittest.mock import patch

from helpers import data_loader

from .utilities import get_qgis_app
from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
from PyQt5.QtCore import QVariant

QGIS_APP = get_qgis_app()

class DummyLineEdit:
    def __init__(self):
        self._text = ""

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

class DummyDlg:
    def __init__(self):
        self.HuPath = DummyLineEdit()
        self.RnPath = DummyLineEdit()
        self.PartPath = DummyLineEdit()
        self.AuxPath = DummyLineEdit()
        self.OutputPath = DummyLineEdit()
        self.WorkspacePath = DummyLineEdit()


class TestSelectFileFunctions(unittest.TestCase):
    def setUp(self):
        self.dlg = DummyDlg()

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_hu_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_hu.shp', '')
        data_loader.select_HU_file(self.dlg)
        self.assertEqual(self.dlg.HuPath.text(), '/tmp/test_hu.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_rn_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_rn.shp', '')
        data_loader.select_RN_file(self.dlg)
        self.assertEqual(self.dlg.RnPath.text(), '/tmp/test_rn.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_part_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_part.shp', '')
        data_loader.select_PART_file(self.dlg)
        self.assertEqual(self.dlg.PartPath.text(), '/tmp/test_part.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_aux_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_aux.shp', '')
        data_loader.select_AUX_file(self.dlg)
        self.assertEqual(self.dlg.AuxPath.text(), '/tmp/test_aux.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getSaveFileName')
    def test_select_output_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/out.gpkg', '')
        data_loader.select_output_file(self.dlg)
        self.assertEqual(self.dlg.OutputPath.text(), '/tmp/out.gpkg')

    @patch('PyQt5.QtWidgets.QFileDialog.getExistingDirectory')
    def test_select_workspace_file(self, mock_dialog):
        mock_dialog.return_value = '/tmp/workspace'
        data_loader.select_workspace_file(self.dlg)
        self.assertEqual(self.dlg.WorkspacePath.text(), '/tmp/workspace')


class TestCreatePartitionsList(unittest.TestCase):
    def setUp(self):
        # Create an in-memory vector layer with NAME field
        self.layer = QgsVectorLayer('Point?crs=EPSG:4326', 'parts', 'memory')
        pr = self.layer.dataProvider()
        pr.addAttributes([QgsField('NAME', QVariant.String)])
        self.layer.updateFields()
        feats = []
        for name, x in zip(['A', 'B', 'C'], [0, 1, 2]):
            f = QgsFeature(self.layer.fields())
            f.setAttributes([name])
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, x)))
            feats.append(f)
        pr.addFeatures(feats)
        self.layer.updateExtents()

    def test_create_all_partitions(self):
        result = data_loader.create_partitions_list(self.layer, ['#'], -1, -1)
        self.assertEqual(result, ['A', 'B', 'C'])

    def test_create_range_partitions(self):
        result = data_loader.create_partitions_list(self.layer, ['#'], 0, 2)
        self.assertEqual(result, ['A', 'B'])

    def test_create_from_list(self):
        result = data_loader.create_partitions_list(self.layer, ['B', 'C\n'], -1, -1)
        self.assertEqual(result, ['B', 'C'])

    def test_invalid_layer(self):
        invalid = QgsVectorLayer()  # invalid layer
        with self.assertRaises(ValueError):
            data_loader.create_partitions_list(invalid, ['#'], -1, -1)


class TestCreateAuxiliaryData(unittest.TestCase):
    def setUp(self):
        # polygon vegetation layer
        self.veg = QgsVectorLayer('Polygon?crs=EPSG:4326', 'veg', 'memory')
        pr = self.veg.dataProvider()
        pr.addAttributes([QgsField('id', QVariant.Int)])
        self.veg.updateFields()
        f = QgsFeature(self.veg.fields())
        f.setAttributes([1])
        f.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0,0), QgsPointXY(1,0), QgsPointXY(1,1), QgsPointXY(0,1), QgsPointXY(0,0)]]))
        pr.addFeatures([f])
        self.veg.updateExtents()
        # line road layer
        self.road = QgsVectorLayer('LineString?crs=EPSG:4326', 'road', 'memory')
        pr = self.road.dataProvider()
        pr.addAttributes([QgsField('id', QVariant.Int)])
        self.road.updateFields()
        f = QgsFeature(self.road.fields())
        f.setAttributes([1])
        f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(0,0), QgsPointXY(1,1)]))
        pr.addFeatures([f])
        self.road.updateExtents()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        for f in os.listdir(self.temp_dir):
            os.remove(os.path.join(self.temp_dir, f))
        os.rmdir(self.temp_dir)

    def test_create_auxiliary_data(self):
        poly, line = data_loader.create_auxiliary_data(self.veg, self.road, self.temp_dir)
        self.assertTrue(os.path.exists(poly))
        self.assertTrue(os.path.exists(line))
        # check that returned layers are valid when loaded
        lpoly = QgsVectorLayer(poly, 'p', 'ogr')
        lline = QgsVectorLayer(line, 'l', 'ogr')
        self.assertTrue(lpoly.isValid())
        self.assertTrue(lline.isValid())
        self.assertTrue(poly.startswith(self.temp_dir))
        self.assertTrue(line.startswith(self.temp_dir))


if __name__ == '__main__':
    unittest.main()
