import arcpy
import shutil
import unittest
from dataclasses import dataclass
from archaic import FeatureClass


@dataclass(frozen=True)
class Mine:
    objectid: int
    name_e: str
    type_e: str
    shape: arcpy.Multipoint


class TestMines(unittest.TestCase):

    def setUp(self):
        geodatabase = r".data\\canada.geodatabase"
        test_geodatabase = r".data\\test.geodatabase"
        shutil.copyfile(geodatabase, test_geodatabase)
        arcpy.env.workspace = test_geodatabase  # type: ignore

    def test_info_mines(self):
        feature_class = FeatureClass[Mine]("main.mines_pt")
        info = feature_class.info
        self.assertTrue(info.catalog_path.endswith("main.mines_pt"))
        self.assertTrue(info.oid_field_name == "OBJECTID")
        self.assertTrue(info.oid_property_name == "objectid")

    def test_read_mines_1(self):
        feature_class = FeatureClass[Mine]("main.mines_pt")
        for feature in feature_class.read("name_e LIKE 'c%'"):
            self.assertTrue(feature.name_e.startswith("C"))

    def test_read_mines_2(self):
        feature_class = FeatureClass[Mine]("main.mines_pt")
        for feature in feature_class.read([1, 3, 5, 7]):
            self.assertTrue(feature.objectid in [1, 3, 5, 7])

    def test_get_mines_1(self):
        feature_class = FeatureClass[Mine]("main.mines_pt")
        mine = feature_class.get(7)
        self.assertTrue(mine and mine.objectid == 7)
        mine = feature_class.get(9999)
        self.assertTrue(mine is None)


if __name__ == "__main__":
    unittest.main()
