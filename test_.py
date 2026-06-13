from datetime import datetime

import arcpy
import dataclasses
import pytest
import shutil
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Optional

from archaic import Mapper


def _setup_workspace() -> None:
    geodatabase = "data/world.geodatabase"
    test_geodatabase = "data/test.geodatabase"
    shutil.copyfile(geodatabase, test_geodatabase)
    arcpy.env.workspace = test_geodatabase


_setup_workspace()


@dataclasses.dataclass
class ObjectID:
    objectid: int = dataclasses.field(default=-1, init=False)


@dataclasses.dataclass
class GlobalID:
    globalid: str = dataclasses.field(default="", init=False)


@dataclasses.dataclass
class EditTracking:
    created_user: Optional[str] = dataclasses.field(default=None, init=False)
    created_date: Optional[datetime] = dataclasses.field(default=None, init=False)
    last_edited_user: Optional[str] = dataclasses.field(default=None, init=False)
    last_edited_date: Optional[datetime] = dataclasses.field(default=None, init=False)


def _read(mapper: Mapper) -> None:
    cities = list(mapper.read("city_name LIKE 'To%o'"))
    assert len(cities) > 1

    globalids = []
    objectids = []

    for city in cities:
        assert city.city_name.startswith("To") and city.city_name.endswith("o")
        if city.city_name in ["Tokyo", "Toronto"]:
            assert city.pop > 1_000_000
        globalids.append(city.globalid)
        objectids.append(city.objectid)

    cities_by_gid = list(mapper.read(globalids))
    assert len(cities_by_gid) == len(cities)

    city_by_gid = mapper.get(globalids[0])
    assert city_by_gid and city_by_gid.globalid == globalids[0]
    assert city_by_gid.shape.spatialReference.factoryCode == 4326

    cities_by_oid = list(mapper.read(objectids))
    assert len(cities_by_oid) == len(cities)

    city_by_oid = mapper.get(objectids[0], 3857)
    assert city_by_oid and city_by_oid.objectid == objectids[0]
    assert city_by_oid.shape.spatialReference.factoryCode == 3857


def _read_via_lambda(mapper: Mapper) -> None:
    cities = list(
        mapper.read(
            lambda c: (
                c.city_name.startswith("st") and c.pop > 100_000 and c.pop < 800_000
            )
        )
    )

    for city in cities:
        assert city.city_name.lower().startswith("st")
        assert city.pop > 100_000 and city.pop < 800_000


def _crud(
    mapper: Mapper,
    create_city: Callable[[str, int], Any],
    cleanup_filter: Optional[str] = None,
    update_city: Optional[Callable[[Any, int], Any]] = None,
) -> None:
    if cleanup_filter:
        mapper.delete_where(cleanup_filter)

    created = mapper.insert(create_city("CRUD:seed", 100))
    by_oid = mapper.get(created.objectid)
    assert by_oid and by_oid.city_name == "CRUD:seed"

    if hasattr(created, "globalid") and getattr(created, "globalid"):
        by_gid = mapper.get(created.globalid)
        assert by_gid and by_gid.objectid == created.objectid

    if update_city:
        mapper.update_where(
            [by_oid.objectid],
            lambda current: update_city(current, 101),
        )
    else:
        by_oid.pop = 101
        mapper.update(by_oid)
    updated = mapper.get(by_oid.objectid)
    assert updated and updated.pop == 101

    many_ids = mapper.insert_many(
        [create_city("CRUD:many-a", 201), create_city("CRUD:many-b", 202)]
    )
    many = list(mapper.read(many_ids))
    assert len(many) == 2

    deleted = set(mapper.delete([created.objectid, *many_ids]))
    assert deleted == {created.objectid, *many_ids}
    assert mapper.get(created.objectid) is None


def test_crud_dataclass_init_true_city():
    @dataclass
    class DataclassCity(ObjectID, GlobalID):
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[DataclassCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: DataclassCity(name, pop, (-120, 50)),
        "city_name LIKE 'CRUD:%'",
    )


def test_crud_dataclass_init_false_city():
    @dataclass(init=False)
    class DataclassInitFalseCity(ObjectID, GlobalID):
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[DataclassInitFalseCity]("cities")

    def create_city(name: str, pop: int) -> DataclassInitFalseCity:
        city = DataclassInitFalseCity()
        city.city_name = name
        city.pop = pop
        city.shape = (-120, 50)
        return city

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(mapper, create_city, "city_name LIKE 'CRUD:%'")


def test_crud_dataclass_frozen_city():
    @dataclass(frozen=True)
    class DataclassFrozenCity:
        objectid: int = dataclasses.field(default=-1, init=False)
        globalid: str = dataclasses.field(default="", init=False)
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[DataclassFrozenCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: DataclassFrozenCity(name, pop, (-120, 50)),
        "city_name LIKE 'CRUD:%'",
        lambda city, pop: dataclasses.replace(city, pop=pop),
    )


def test_crud_dataclass_slots_city():
    @dataclass(slots=True)
    class DataclassSlotsCity(ObjectID, GlobalID):
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[DataclassSlotsCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: DataclassSlotsCity(name, pop, (-120, 50)),
        "city_name LIKE 'CRUD:%'",
    )


def test_crud_plain_python_city():
    class PlainPythonCity(ObjectID, GlobalID):
        city_name: str
        pop: int
        shape: Any

        def __init__(
            self, city_name: str = "", pop: int = 0, shape: Any = None
        ) -> None:
            self.city_name = city_name
            self.pop = pop
            self.shape = shape

    mapper = Mapper[PlainPythonCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: PlainPythonCity(name, pop, (-120, 50)),
        "city_name LIKE 'CRUD:%'",
    )


def test_crud_plain_python_city_with_mixins():
    class PlainPythonCityWithMixins:
        objectid: int
        globalid: str
        city_name: str
        pop: int
        shape: Any

        def __init__(
            self, city_name: str = "", pop: int = 0, shape: Any = None
        ) -> None:
            self.objectid = -1
            self.globalid = ""
            self.city_name = city_name
            self.pop = pop
            self.shape = shape

    mapper = Mapper[PlainPythonCityWithMixins]("cities")  # type: ignore

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: PlainPythonCityWithMixins(name, pop, (-120, 50)),
        "city_name LIKE 'CRUD:%'",
    )


def test_crud_pydantic_dataclass_city():
    pydantic = pytest.importorskip("pydantic")
    pdc = pytest.importorskip("pydantic.dataclasses")

    @pdc.dataclass(config=pydantic.ConfigDict(arbitrary_types_allowed=True))
    class PydanticDataclassCity(ObjectID, GlobalID):
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[PydanticDataclassCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: PydanticDataclassCity(
            city_name=name, pop=pop, shape=(-120, 50)
        ),
        "city_name LIKE 'CRUD:%'",
    )


def test_crud_pydantic_dataclass_init_false_city():
    pydantic = pytest.importorskip("pydantic")
    pdc = pytest.importorskip("pydantic.dataclasses")

    @pdc.dataclass(init=False, config=pydantic.ConfigDict(arbitrary_types_allowed=True))
    class PydanticDataclassInitFalseCity(ObjectID, GlobalID):
        city_name: str = ""
        pop: int = 0
        shape: Any = None

    def create_city(name: str, pop: int) -> PydanticDataclassInitFalseCity:
        city = PydanticDataclassInitFalseCity()
        city.city_name = name
        city.pop = pop
        city.shape = (-120, 50)
        return city

    mapper = Mapper[PydanticDataclassInitFalseCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(mapper, create_city, "city_name LIKE 'CRUD:%'")


def test_crud_pydantic_dataclass_frozen_city():
    pydantic = pytest.importorskip("pydantic")
    pdc = pytest.importorskip("pydantic.dataclasses")

    @pdc.dataclass(
        config=pydantic.ConfigDict(arbitrary_types_allowed=True, frozen=True)
    )
    class PydanticDataclassFrozenCity:
        objectid: int = dataclasses.field(default=-1, init=False)
        globalid: str = dataclasses.field(default="", init=False)
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[PydanticDataclassFrozenCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: PydanticDataclassFrozenCity(
            city_name=name, pop=pop, shape=(-120, 50)
        ),
        "city_name LIKE 'CRUD:%'",
        lambda city, pop: dataclasses.replace(city, pop=pop),
    )


def test_crud_pydantic_dataclass_slots_city():
    pydantic = pytest.importorskip("pydantic")
    pdc = pytest.importorskip("pydantic.dataclasses")

    @pdc.dataclass(config=pydantic.ConfigDict(arbitrary_types_allowed=True), slots=True)
    class PydanticDataclassSlotsCity(ObjectID, GlobalID):
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[PydanticDataclassSlotsCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: PydanticDataclassSlotsCity(
            city_name=name, pop=pop, shape=(-120, 50)
        ),
        "city_name LIKE 'CRUD:%'",
    )


def test_crud_pydantic_model_city():
    pydantic = pytest.importorskip("pydantic")

    class PydanticModelCity(pydantic.BaseModel):
        objectid: int = -1
        globalid: str = ""
        city_name: str
        pop: int
        shape: Any

    mapper = Mapper[PydanticModelCity]("cities")

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(
        mapper,
        lambda name, pop: PydanticModelCity(city_name=name, pop=pop, shape=(-120, 50)),
        "city_name LIKE 'CRUD:%'",
    )


def test_crud_simplenamespace_city():
    mapper = Mapper(
        "cities",
        objectid="OBJECTID",
        globalid="GlobalID",
        city_name="city_name",
        pop="pop",
        shape="SHAPE",
    )

    def create_city(name: str, pop: int) -> SimpleNamespace:
        city = SimpleNamespace()
        city.objectid = -1
        city.globalid = ""
        city.city_name = name
        city.pop = pop
        city.shape = (-120, 50)
        return city

    _read(mapper)
    _read_via_lambda(mapper)
    _crud(mapper, create_city, "city_name LIKE 'CRUD:%'")
