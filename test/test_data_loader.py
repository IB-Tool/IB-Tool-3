# coding=utf-8
"""Unit tests for helpers.data_loader"""

import unittest
from unittest.mock import patch

from helpers import data_loader
from ibtool import IBTool

from .utilities import get_qgis_app
from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY
from PyQt5.QtCore import QVariant

QGIS_APP = get_qgis_app()


class TestSelectFileFunctions(unittest.TestCase):
    def setUp(self):
        _, _, iface, _ = get_qgis_app()
        self.tool = IBTool(iface)

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_hu_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_hu.shp', '')
        self.tool.select_HU_file()
        self.assertEqual(self.tool.dlg.HuPath.text(), '/tmp/test_hu.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_rn_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_rn.shp', '')
        self.tool.select_RN_file()
        self.assertEqual(self.tool.dlg.RnPath.text(), '/tmp/test_rn.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_part_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_part.shp', '')
        self.tool.select_PART_file()
        self.assertEqual(self.tool.dlg.PartPath.text(), '/tmp/test_part.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getOpenFileName')
    def test_select_aux_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/test_aux.shp', '')
        self.tool.select_AUX_file()
        self.assertEqual(self.tool.dlg.AuxPath.text(), '/tmp/test_aux.shp')

    @patch('PyQt5.QtWidgets.QFileDialog.getSaveFileName')
    def test_select_output_file(self, mock_dialog):
        mock_dialog.return_value = ('/tmp/out.gpkg', '')
        self.tool.select_output_file()
        self.assertEqual(self.tool.dlg.OutputPath.text(), '/tmp/out.gpkg')

    @patch('PyQt5.QtWidgets.QFileDialog.getExistingDirectory')
    def test_select_workspace_file(self, mock_dialog):
        mock_dialog.return_value = '/tmp/workspace'
        self.tool.select_workspace_file()
        self.assertEqual(self.tool.dlg.WorkspacePath.text(), '/tmp/workspace')


class TestCreatePartitionsList(unittest.TestCase):
    def setUp(self):
        # Create an in-memory vector layer with NAME field
        self.layer = QgsVectorLayer('Point?crs=EPSG:4326', 'parts', 'memory')
        pr = self.layer.dataProvider()
        pr.addAttributes([QgsField('NAME', QVariant.String, 'varchar', 255)])
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


if __name__ == '__main__':
    unittest.main()
