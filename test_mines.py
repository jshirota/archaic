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
    shape: arcpy.PointGeometry


TMine = TypeVar("TMine", bound=Mine)


def info_mines(feature_class: FeatureClass[TMine]):
    info = feature_class.info
    assert info.data_path.endswith("main.mines_pt")
    assert info.oid_field == "OBJECTID"
    assert info.oid_property == "objectid"


def read_mines(feature_class: FeatureClass[TMine]):
    for feature in feature_class.read("name_e LIKE 'c%'"):
        assert feature.name_e.startswith("C")
    for feature in feature_class.read([1, 3, 5, 7]):
        assert feature.objectid in [1, 3, 5, 7]
    features = list(feature_class.read([]))
    assert len(features) == 0
    total = int(arcpy.management.GetCount("main.mines_pt")[0])  # type: ignore
    features = list(feature_class.read())
    assert len(features) == total
    features = list(feature_class.read([1, 2, 3, 4, 5]))
    assert len(features) == 5
    features = list(feature_class.read("1>0"))
    assert len(features) == total
    features = list(feature_class.read("1<0"))
    assert len(features) == 0
    features = list(feature_class.read(lambda f: f.name_e is None))
    assert len(features) == 0
    features = list(feature_class.read(lambda f: f.name_e is not None))
    assert len(features) == total


def get_mines(feature_class: FeatureClass[TMine]):
    mine = feature_class.get(7)
    assert mine and mine.objectid == 7
    mine = feature_class.get(9999)
    assert mine is None


def insert_mines(feature_class: FeatureClass[TMine]):
    mine = feature_class.get(4)
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

    def update(mine: TMine, value: str):
        mine.type_e = value

    type_e = uuid.uuid4().hex[:8]
    feature_class.update_where("name_e LIKE '%e%'", lambda f: update(f, type_e))
    for mine in feature_class.read():
        if "e" in mine.name_e.lower():
            assert mine.type_e == type_e
        else:
            assert mine.type_e != type_e

    oids = [f.objectid for f in feature_class.read() if f.objectid % 2 == 0]

    type_e = uuid.uuid4().hex[:8]
    feature_class.update_where(oids, lambda f: update(f, type_e))
    for mine in feature_class.read():
        if mine.objectid % 2 == 0:
            assert mine.type_e == type_e
        else:
            assert mine.type_e != type_e


def delete_mines(feature_class: FeatureClass[TMine], *deletes: int):
    feature_class.delete(deletes)
    results = list(feature_class.read(deletes))
    if deletes:
        assert len(results) == 0
        for d in deletes:
            assert feature_class.get(d) is None


def try_mines(feature_class: FeatureClass[TMine], *deletes: int):
    info_mines(feature_class)
    read_mines(feature_class)
    get_mines(feature_class)
    insert_mines(feature_class)
    update_mines(feature_class)
    delete_mines(feature_class, *deletes)


class R:
    objectid: int


class F:
    shape: arcpy.PointGeometry


class Mine1(R, F):
    name_e: str
    type_e: str


def test_mine1():
    try_mines(FeatureClass[Mine1]("main.mines_pt"), 10, 11, 12)


class Mine2:
    objectid: int
    name_e: str
    type_e: str
    shape: arcpy.PointGeometry


def test_mine2():
    try_mines(FeatureClass[Mine2]("main.mines_pt"), 13, 14)


@dataclass
class Mine3:
    objectid: int
    name_e: str
    type_e: str
    shape: arcpy.PointGeometry


def test_mine3():
    try_mines(FeatureClass[Mine3]("main.mines_pt"), 15, 16)


@dataclass
class Row:
    objectid: int


TGeometry = TypeVar("TGeometry", bound=arcpy.Geometry)


@dataclass
class Feature(Generic[TGeometry], Row):
    shape: TGeometry


@dataclass
class Mine4(Feature[arcpy.PointGeometry]):
    name_e: str
    type_e: str


def test_mine4():
    try_mines(FeatureClass[Mine4]("main.mines_pt"), 17, 18)


def test_mine5():
    fc = FeatureClass(
        "main.mines_pt",
        objectid="OBJECTID",
        name_e="NAME_E",
        type_e="TYPE_E",
        shape="SHAPE",
    )
    try_mines(fc, 18, 19, 20)
