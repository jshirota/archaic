import arcpy
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from random import randrange
from types import SimpleNamespace
from typing import Generic, List, Optional, Protocol, TypeVar

from archaic import FeatureClass

geodatabase = ".data/world.geodatabase"
test_geodatabase = f".data/test_{datetime.now():%Y_%m_%d_%H_%M_%S}.geodatabase"
shutil.copyfile(geodatabase, test_geodatabase)
arcpy.env.workspace = test_geodatabase  # type: ignore


class City(Protocol):
    objectid: int
    city_name: str
    pop: int
    shape: arcpy.PointGeometry


TCity = TypeVar("TCity", bound=City)


p = FeatureClass("cities").get(40).Shape  # type: ignore


def info_cities(feature_class: FeatureClass[TCity]):
    info = feature_class.info
    assert info.data_path.endswith("cities")
    assert info.oid_field == "OBJECTID"
    assert info.oid_property == "objectid"


def read_cities(feature_class: FeatureClass[TCity]):
    for feature in feature_class.read("city_name LIKE 'c%'"):
        assert feature.city_name.startswith("C")
    for feature in feature_class.read([1, 3, 5, 7]):
        assert feature.objectid in [1, 3, 5, 7]
    features = list(feature_class.read([]))
    assert len(features) == 0
    total = int(arcpy.management.GetCount("cities")[0])  # type: ignore
    features = list(feature_class.read())
    assert len(features) == total
    features = list(feature_class.read([1, 2, 3, 4, 5]))
    assert len(features) == 5
    features = list(feature_class.read("1>0"))
    assert len(features) == total
    features = list(feature_class.read("1<0"))
    assert len(features) == 0
    features = list(feature_class.read(lambda f: f.city_name is None))
    assert len(features) == 0
    features = list(feature_class.read(lambda f: f.city_name is not None))
    assert len(features) == total


def get_cities(feature_class: FeatureClass[TCity]):
    city = feature_class.get(7)
    assert city and city.objectid == 7
    city = feature_class.get(9999)
    assert city is None


def insert_cities(feature_class: FeatureClass[TCity]):
    city = feature_class.get(4)
    assert city
    city2 = feature_class.insert(city)
    assert city2.objectid != city.objectid
    assert city2.city_name == city.city_name
    assert city2.pop == city.pop
    assert city2.shape.firstPoint.X == city.shape.firstPoint.X
    assert city2.shape.firstPoint.Y == city.shape.firstPoint.Y


def update_cities(feature_class: FeatureClass[TCity]):
    pop = randrange(10000, 20000)
    assert (city := feature_class.get(8)) and city.pop != pop
    city.pop = pop
    feature_class.update(city)
    assert (city := feature_class.get(8)) and city.pop == pop

    def update(city: TCity, value: int):
        city.pop = value

    pop = randrange(10000, 20000)
    feature_class.update_where("city_name LIKE '%e%'", lambda f: update(f, pop))
    for city in feature_class.read():
        if "e" in city.city_name.lower():
            assert city.pop == pop
        else:
            assert city.pop != pop

    oids = [f.objectid for f in feature_class.read() if f.objectid % 2 == 0]

    pop = randrange(10000, 20000)
    feature_class.update_where(oids, lambda f: update(f, pop))
    for city in feature_class.read():
        if city.objectid % 2 == 0:
            assert city.pop == pop
        else:
            assert city.pop != pop


def delete_cities(feature_class: FeatureClass[TCity], *deletes: int):
    feature_class.delete(deletes)
    results = list(feature_class.read(deletes))
    if deletes:
        assert len(results) == 0
        for d in deletes:
            assert feature_class.get(d) is None


def insert_many_cities(feature_class: FeatureClass[TCity], inserts: List[TCity]):
    oids = feature_class.insert_many(inserts)
    assert len(inserts) == len(oids)
    cities_dict = {f.city_name: f for f in inserts}
    for city in feature_class.read(oids):
        city_before = cities_dict.get(city.city_name)
        assert city_before and city.pop == city_before.pop
        # assert city.shape.JSON == city_before.shape.JSON


def try_cities(feature_class: FeatureClass[TCity], inserts: List[TCity], *deletes: int):
    info_cities(feature_class)
    read_cities(feature_class)
    get_cities(feature_class)
    insert_cities(feature_class)
    update_cities(feature_class)
    delete_cities(feature_class, *deletes)
    insert_many_cities(feature_class, [])
    insert_many_cities(feature_class, inserts)


class R:
    objectid: int


class F:
    shape: arcpy.PointGeometry


class City1(R, F):
    city_name: str
    pop: int


def test_city1():
    def create():
        for n in range(1000):
            city = City1()
            city.city_name = f"City1:{n}"
            city.pop = n
            city.shape = p
            yield city

    try_cities(FeatureClass[City1]("cities"), list(create()), 10, 11, 12)


class City2:
    objectid: int
    city_name: str
    pop: int
    shape: arcpy.PointGeometry


def test_city2():
    def create():
        for n in range(1000):
            city = City2()
            city.city_name = f"City2:{n}"
            city.pop = n
            city.shape = p
            yield city

    try_cities(FeatureClass[City2]("cities"), list(create()), 13, 14)


@dataclass
class City3:
    objectid: int = field(default=-1, init=False)
    city_name: str
    pop: int
    shape: arcpy.PointGeometry


def test_city3():
    def create():
        for n in range(1000):
            city = City3(f"City3:{n}", n, p)
            yield city

    try_cities(FeatureClass[City3]("cities"), list(create()), 15, 16)


@dataclass
class Row:
    objectid: int


TGeometry = TypeVar("TGeometry", bound=arcpy.Geometry)


@dataclass
class Feature(Generic[TGeometry], Row):
    shape: TGeometry


@dataclass
class City4(Feature[arcpy.PointGeometry]):
    city_name: str
    pop: int


def test_city4():
    def create():
        for n in range(1000):
            city = City4(-1, p, f"City4:{n}", n)
            yield city

    try_cities(FeatureClass[City4]("cities"), list(create()), 17, 18)


def test_city5():
    fc = FeatureClass(
        "cities",
        objectid="OBJECTID",
        city_name="city_name",
        pop="pop",
        shape="SHAPE",
    )

    def create():
        for n in range(1000):
            city = SimpleNamespace()
            city.objectid = randrange(40000, 50000)
            city.city_name = f"City5:{n}"
            city.pop = n
            city.shape = p
            yield city

    try_cities(fc, [], 18, 19, 20)


@dataclass
class Tracked:
    created_user: Optional[str] = field(init=False)
    created_date: Optional[datetime] = field(init=False)
    last_edited_user: Optional[str] = field(init=False)
    last_edited_date: Optional[datetime] = field(init=False)


@dataclass
class City6(Tracked):
    objectid: int = field(default=-1, init=False)
    city_name: str
    pop: int
    shape: arcpy.PointGeometry


def test_city6():
    fc = FeatureClass[City6]("cities")
    assert fc

    city = fc.insert(City6("Lillooet", 1234, p))
    assert city.city_name == "Lillooet"
    assert city.pop == 1234
    assert city.created_date
    assert city.created_user
    assert city.last_edited_date
    assert city.last_edited_user
