import arcpy
from typing import Any, Callable, Generic, Iterable, List, Optional, Set, TypeVar, Union
from archaic.info import Info
from archaic.predicate import to_sql

T = TypeVar("T")


class FeatureClass(Generic[T]):
    def __init__(self, data_path: str, **mapping: str) -> None:
        """Initializes the feature class.  e.g.

            class City:
                objectid: int
                city_name: str
                shape: arcpy.PointGeometry

            cities_fc = FeatureClass [City] ('world.gdb/cities')

            for city in cities_fc.read():
                print(city.city_name, city.shape.WKT)

        Args:
            data_path (str): Feature class path.
            mapping: Custom mapping of property to field.
        """
        self._data_path = data_path
        self._mapping = mapping

    @property
    def info(self):
        if not hasattr(self, "_info"):
            self._info = Info[T](self)
        return self._info

    def read(
        self,
        filter: Union[
            str, Callable[[T], bool], Iterable[int], Iterable[str], None
        ] = None,
        wkid: Optional[int] = None,
        **kwargs: Any,
    ) -> Iterable[T]:
        """Queries the feature class.

        Args:
            filter: Where clause, lambda expression, object ids or global ids.  Defaults to None.
            wkid: Well-known id (e.g. 4326).  Defaults to None.

        Returns:
            Iterable[T]: Strongly typed items.
        """
        if wkid is not None:
            kwargs["spatial_reference"] = arcpy.SpatialReference(wkid)
        data_path = self.info.data_path
        fields = list(self.info.properties.values())
        properties = self.info.properties
        for where_clause in self._get_where_clauses_from_filter(filter):
            with arcpy.da.SearchCursor(data_path, fields, where_clause, **kwargs) as cursor:  # type: ignore
                for row in cursor:
                    d = dict(zip(fields, row))
                    yield self._create(
                        **{p: d.get(f) if f else None for p, f in properties.items()}
                    )

    def get(self, id: Union[int, str], wkid: Optional[int] = None) -> Optional[T]:
        """Gets an item from the feature class.

        Args:
            id: Object id or global id.
            wkid: Well-known id (e.g. 4326).  Defaults to None.

        Returns:
            Optional[T]: Strongly typed item if found.
        """
        for where_clause in self._get_where_clauses_from_ids(id):
            for item in self.read(where_clause, wkid):
                return item
        return None

    def insert_many(self, items: Iterable[T], **kwargs: Any) -> List[int]:
        data_path = self.info.data_path
        fields = list(self.info.edit_properties.values())
        properties = self.info.edit_properties
        with arcpy.da.InsertCursor(data_path, fields, **kwargs) as cursor:  # type: ignore
            return [
                cursor.insertRow(self._get_values(item, properties)) for item in items
            ]

    def insert(self, item: T) -> T:
        return self.get(self.insert_many([item])[0])  # type: ignore

    def update_where(
        self,
        filter: Union[str, Callable[[T], bool], Iterable[int], Iterable[str], None],
        update: Callable[[T], Union[None, T]],
        **kwargs: Any,
    ) -> List[int]:
        data_path = self.info.data_path
        fields = list(self.info.edit_properties.values())
        properties = self.info.edit_properties
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_filter(filter):
            with arcpy.da.UpdateCursor(data_path, fields, where_clause, **kwargs) as cursor:  # type: ignore
                for row in cursor:
                    d = dict(zip(fields, row))
                    before = self._create(
                        **{p: d.get(f) if f else None for p, f in properties.items()}
                    )
                    result = update(before)
                    after = before if result is None else result
                    cursor.updateRow(self._get_values(after, properties))
                    ids.add(self._get_oid(before))
        return list(ids)

    def update(self, items: Union[T, List[T]]) -> List[int]:
        items = list(items) if isinstance(items, Iterable) else [items]
        cache = {self._get_oid(x): x for x in items}
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_ids(items):
            for id in self.update_where(
                where_clause, lambda x: cache[self._get_oid(x)]
            ):
                ids.add(id)
        return list(ids)

    def delete_where(self, filter: Union[str, Callable[[T], bool], None]) -> List[int]:
        data_path = self.info.data_path
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_filter(filter):
            with arcpy.da.UpdateCursor(data_path, self.info.oid_field, where_clause) as cursor:  # type: ignore
                for row in cursor:
                    cursor.deleteRow()
                    ids.add(row[0])
        return list(ids)

    def delete(
        self, items: Union[T, int, str, Iterable[T], Iterable[int], Iterable[str]]
    ) -> List[int]:
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_ids(items):
            for id in self.delete_where(where_clause):
                ids.add(id)
        return list(ids)

    def _create(self, **kwargs: Any) -> T:
        if self.info.has_default_constructor:
            item = self.info.model()
            for property in self.info.properties:
                setattr(item, property, kwargs.get(property))
            return item
        return self.info.model(
            **{k: v for k, v in kwargs.items() if k in self.info.properties}
        )

    def _get_values(self, item: T, properties: Iterable[str]) -> List[Any]:
        values: List[Any] = []
        for property in properties:
            values.append(getattr(item, property) if hasattr(item, property) else None)
        return values

    def _get_where_clauses_from_ids(
        self, obj: Union[T, int, str, Iterable[T], Iterable[int], Iterable[str]]
    ) -> List[str]:
        where_clauses: List[str] = []
        ids = list(self._get_ids(obj))
        n = 1000
        for chunk in [ids[i : i + n] for i in range(0, len(ids), n)]:
            first = chunk[0]
            if isinstance(first, int):
                where_clauses.append(
                    f"{self.info.oid_field} IN ({','.join(map(str, chunk))})"
                )
            elif isinstance(first, str):
                where_clauses.append(
                    f"GlobalID IN ({','.join(map(self._quote, chunk))})"
                )
        return where_clauses

    def _get_where_clauses_from_filter(
        self,
        filter: Union[str, Callable[[T], bool], Iterable[int], Iterable[str], None],
    ) -> List[str]:
        if filter is None:
            return [""]
        if isinstance(filter, str):
            return [filter]
        if callable(filter):
            return [to_sql(filter, self.info.properties)]
        return self._get_where_clauses_from_ids(filter)

    def _quote(self, value: Any) -> str:
        return f"'{value}'"

    def _get_ids(self, obj) -> Iterable[Union[int, str]]:
        if isinstance(obj, int) or isinstance(obj, str):
            yield obj
        elif isinstance(obj, self.info.model):
            yield self._get_oid(obj)
        else:
            for o in obj:
                for id in self._get_ids(o):
                    yield id

    def _get_oid(self, item) -> int:
        if not self.info.oid_property:
            raise TypeError(
                f"'{self.info.model.__name__}' is missing the OID property."
            )
        return getattr(item, self.info.oid_property)
