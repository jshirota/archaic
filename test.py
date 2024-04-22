import arcpy
import unittest
from dataclasses import dataclass
from archaic import FeatureClass

arcpy.env.workspace = ".data/canada.geodatabase"  # type: ignore


@dataclass(frozen=True)
class Mine:
    oid: int
    name_e: str
    type_e: str
    shape: arcpy.Multipoint


class TestMines(unittest.TestCase):

    def test_info(self):
        feature_class = FeatureClass[Mine]("main.mines_pt")
        info = feature_class.info
        self.assertTrue(info.catalog_path.endswith("main.mines_pt"))
