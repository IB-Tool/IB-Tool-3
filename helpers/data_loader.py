from qgis.core import QgsVectorLayer


def create_partitions_list(Partition_layer, partlist, partstart, partend):
    """Return a filtered list of partition names from the given layer."""
    if not Partition_layer.isValid():
        raise ValueError("Ungültiger Layer. Überprüfen Sie den Pfad zur Partition-Tabelle.")

    if str(partlist[0]) == '#':
        if partstart == -1 or partend == -1:
            partlist = [f["NAME"] for f in Partition_layer.getFeatures()]
        else:
            partlist = [f["NAME"] for f in Partition_layer.getFeatures()]
            partlist = partlist[partstart:partend]
    else:
        partlist = [j.replace('\n', '') for j in partlist]

    return partlist
