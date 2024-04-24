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


class Glacier(Protocol):
    objectid: int
    carto_uid: int
    feature: str
    shape: arcpy.Polygon


TGlacier = TypeVar("TGlacier", bound=Glacier)


def info_glaciers(feature_class: FeatureClass[TGlacier]):
    info = feature_class.info
    assert info.data_path.endswith("main.glaciers_p")
    assert info.oid_field == "OBJECTID"
    assert info.oid_property == "objectid"


def read_glaciers(feature_class: FeatureClass[TGlacier]):
    for feature in feature_class.read(lambda f: f.carto_uid < 7000):
        assert feature.carto_uid < 7000
    for feature in feature_class.read([1, 3, 5, 7]):
        assert feature.objectid in [1, 3, 5, 7]


def get_glaciers(feature_class: FeatureClass[TGlacier]):
    glacier = feature_class.get(7)
    assert glacier and glacier.objectid == 7
    glacier = feature_class.get(9999)
    assert glacier is None


def insert_glaciers(feature_class: FeatureClass[TGlacier]):
    glacier = feature_class.get(12)
    assert glacier
    glacier2 = feature_class.insert(glacier)
    assert glacier2.objectid != glacier.objectid
    assert glacier2.feature == glacier.feature
    assert glacier2.carto_uid == glacier.carto_uid
    assert glacier2.shape.area == glacier.shape.area


def update_glaciers(feature_class: FeatureClass[TGlacier]):
    feature = uuid.uuid4().hex[:8]
    assert (glacier := feature_class.get(8)) and glacier.feature != feature
    glacier.feature = feature
    feature_class.update(glacier)
    assert (glacier := feature_class.get(8)) and glacier.feature == feature
    feature = uuid.uuid4().hex[:8]

    def update(glacier: TGlacier):
        glacier.feature = feature

    feature_class.update_where(
        lambda f: f.carto_uid > 8000 and f.carto_uid < 12000, update
    )
    for glacier in feature_class.read():
        if 8000 < glacier.carto_uid < 12000:
            assert glacier.feature == feature
        else:
            assert glacier.feature != feature


def try_mines(feature_class: FeatureClass[TGlacier]):
    info_glaciers(feature_class)
    read_glaciers(feature_class)
    get_glaciers(feature_class)
    insert_glaciers(feature_class)
    update_glaciers(feature_class)


class R:
    objectid: int


class F:
    shape: arcpy.Polygon


class Glacier1(R, F):
    feature: str
    carto_uid: int


def test_glacier1():
    try_mines(FeatureClass[Glacier1]("main.glaciers_p", feature="FEATURE_E"))
    try_mines(FeatureClass[Glacier1]("main.glaciers_p", feature="FEATURE_F"))


class Glacier2:
    objectid: int
    carto_uid: int
    feature: str
    shape: arcpy.Polygon


def test_glacier2():
    try_mines(FeatureClass[Glacier2]("main.glaciers_p", feature="FEATURE_E"))
    try_mines(FeatureClass[Glacier2]("main.glaciers_p", feature="FEATURE_F"))


@dataclass
class Glacier3:
    objectid: int
    carto_uid: int
    feature: str
    shape: arcpy.Polygon


def test_glacier3():
    try_mines(FeatureClass[Glacier3]("main.glaciers_p", feature="FEATURE_E"))
    try_mines(FeatureClass[Glacier3]("main.glaciers_p", feature="FEATURE_F"))


@dataclass
class Row:
    objectid: int


TGeometry = TypeVar("TGeometry", bound=arcpy.Geometry)


@dataclass
class Feature(Generic[TGeometry], Row):
    shape: TGeometry


@dataclass
class Glacier4(Feature[arcpy.Polygon]):
    carto_uid: int
    feature: str


def test_glacier4():
    try_mines(FeatureClass[Glacier4]("main.glaciers_p", feature="FEATURE_E"))
    try_mines(FeatureClass[Glacier4]("main.glaciers_p", feature="FEATURE_F"))


def test_glacier5():
    fc = FeatureClass(
        "main.glaciers_p",
        objectid="OBJECTID",
        carto_uid="CARTO_UID",
        feature="FEATURE_E",
        shape="SHAPE",
    )
    try_mines(fc)
