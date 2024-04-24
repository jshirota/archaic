import arcpy
from typing import Any, Callable, Generic, Iterable, List, Optional, TypeVar, Union
from archaic.info import Info
from archaic.predicate import to_sql

T = TypeVar("T")


class FeatureClass(Generic[T]):
    def __init__(self, data_path: str, **mapping: str) -> None:
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
        if wkid is not None:
            kwargs["spatial_reference"] = arcpy.SpatialReference(wkid)

        data_path = self.info.data_path
        fields = list(self.info.properties.values())
        properties = self.info.properties

        if callable(filter):
            filter = to_sql(filter, self.info.properties)

        if filter is None or isinstance(filter, str):
            where_clauses = [filter]
        else:
            where_clauses = self._get_where_clauses(list(filter))  # type: ignore

        for where_clause in where_clauses:
            with arcpy.da.SearchCursor(data_path, fields, where_clause, **kwargs) as cursor:  # type: ignore
                for row in cursor:
                    d = dict(zip(fields, row))
                    yield self._create(
                        **{p: d.get(f) if f else None for p, f in properties.items()}
                    )

    def get(self, id: Union[int, str], wkid: Optional[int] = None) -> Optional[T]:
        for where_clause in self._get_where_clauses(id):
            for item in self.read(where_clause, wkid):
                return item
        return None

    def insert_many(self, items: Iterable[T], **kwargs: Optional[Any]) -> List[int]:
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
        filter: Union[str, Callable[[T], bool], None],
        update: Callable[[T], Union[None, T]],
        **kwargs: Any,
    ) -> int:
        where_clause = (
            to_sql(filter, self.info.properties) if callable(filter) else filter
        )
        data_path = self.info.data_path
        fields = list(self.info.edit_properties.values())
        properties = self.info.edit_properties
        count = 0

        with arcpy.da.UpdateCursor(data_path, fields, where_clause, **kwargs) as cursor:  # type: ignore
            for row in cursor:
                d = dict(zip(fields, row))
                before = self._create(
                    **{p: d.get(f) if f else None for p, f in properties.items()}
                )
                result = update(before)
                after = before if result is None else result
                cursor.updateRow(self._get_values(after, properties))
                count += 1
        return count

    def update(self, items: Union[T, List[T]]) -> None:
        items = list(items) if isinstance(items, Iterable) else [items]
        cache = {self._get_oid(x): x for x in items}
        for where_clause in self._get_where_clauses(items):
            self.update_where(where_clause, lambda x: cache[self._get_oid(x)])

    def delete_where(self, filter: Union[str, Callable[[T], bool], None]) -> int:
        where_clause = (
            to_sql(filter, self.info.properties) if callable(filter) else filter
        )
        data_path = self.info.data_path
        count = 0

        with arcpy.da.UpdateCursor(data_path, self.info.oid_field, where_clause) as cursor:  # type: ignore
            for _ in cursor:
                cursor.deleteRow()
                count += 1
        return count

    def delete(self, items: Union[T, int, str, List[T], List[int], List[str]]) -> None:
        for where_clause in self._get_where_clauses(items):
            self.delete_where(where_clause)

    def _create(self, **kwargs: Any):
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

    def _get_where_clauses(
        self, obj: Union[T, int, str, List[T], List[int], List[str]]
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

        if not where_clauses:
            where_clauses.append("1=0")

        return where_clauses

    def _quote(self, value: Any) -> str:
        return f"'{value}'"

    def _get_ids(self, obj) -> Iterable[Union[int, str]]:
        if isinstance(obj, int) or isinstance(obj, str):
            yield obj
        elif isinstance(obj, self.info.model):
            yield self._get_oid(obj)
        elif isinstance(obj, list):
            for o in obj:
                for id in self._get_ids(o):
                    yield id

    def _get_oid(self, item) -> int:
        if not self.info.oid_property:
            raise TypeError(
                f"'{self.info.model.__name__}' is missing the OID property."
            )
        return getattr(item, self.info.oid_property)
