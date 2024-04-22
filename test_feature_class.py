import arcpy
import shutil
import uuid
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from archaic import FeatureClass


geodatabase = r".data\\canada.geodatabase"
test_geodatabase = r".data\\test.geodatabase"
shutil.copyfile(geodatabase, test_geodatabase)
arcpy.env.workspace = test_geodatabase  # type: ignore


class Mine(Protocol):
    objectid: int
    name_e: str
    type_e: str
    shape: arcpy.Multipoint


TMine = TypeVar("TMine", bound=Mine)


def info_mines(feature_class: FeatureClass[TMine]):
    info = feature_class.info
    assert info.catalog_path.endswith("main.mines_pt")
    assert info.oid_field_name == "OBJECTID"
    assert info.oid_property_name == "objectid"


def read_mines(feature_class: FeatureClass[TMine]):
    for feature in feature_class.read("name_e LIKE 'c%'"):
        assert feature.name_e.startswith("C")
    for feature in feature_class.read([1, 3, 5, 7]):
        assert feature.objectid in [1, 3, 5, 7]


def get_mines(feature_class: FeatureClass[TMine]):
    mine = feature_class.get(7)
    assert mine and mine.objectid == 7
    mine = feature_class.get(9999)
    assert mine is None


def insert_mines(feature_class: FeatureClass[TMine]):
    mine = feature_class.get(12)
    assert mine
    mine2 = feature_class.insert(mine)
    assert mine2.objectid != mine.objectid
    assert mine2.name_e == mine.name_e
    assert mine2.type_e == mine.type_e
    assert mine2.shape.firstPoint.X == mine.shape.firstPoint.X
    assert mine2.shape.firstPoint.Y == mine.shape.firstPoint.Y


def update_mines(feature_class: FeatureClass[TMine]):
    type_e = uuid.uuid4().hex[:8]
    assert (mine := feature_class.get(8)) and mine.type_e != type_e
    mine.type_e = type_e
    feature_class.update(mine)
    assert (mine := feature_class.get(8)) and mine.type_e == type_e
    type_e = uuid.uuid4().hex[:8]

    def update(mine: TMine):
        mine.type_e = type_e

    feature_class.update_where("name_e LIKE '%e%'", update)
    for mine in feature_class.read():
        if "e" in mine.name_e.lower():
            assert mine.type_e == type_e
        else:
            assert mine.type_e != type_e


def try_mines(feature_class: FeatureClass[TMine]):
    info_mines(feature_class)
    read_mines(feature_class)
    get_mines(feature_class)
    insert_mines(feature_class)
    update_mines(feature_class)


class R:
    objectid: int


class F:
    shape: arcpy.Multipoint


class Mine1(R, F):
    name_e: str
    type_e: str


def test_mine1():
    try_mines(FeatureClass[Mine1]("main.mines_pt"))


class Mine2:
    objectid: int
    name_e: str
    type_e: str
    shape: arcpy.Multipoint


def test_mine2():
    try_mines(FeatureClass[Mine2]("main.mines_pt"))


@dataclass
class Mine3:
    objectid: int
    name_e: str
    type_e: str
    shape: arcpy.Multipoint


def test_mine3():
    try_mines(FeatureClass[Mine3]("main.mines_pt"))


@dataclass
class Row:
    objectid: int


TGeometry = TypeVar("TGeometry", bound=arcpy.Geometry)


@dataclass
class Feature(Generic[TGeometry], Row):
    shape: TGeometry


@dataclass
class Mine4(Feature[arcpy.Multipoint]):
    name_e: str
    type_e: str


def test_mine4():
    try_mines(FeatureClass[Mine4]("main.mines_pt"))
