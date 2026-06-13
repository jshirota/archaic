import arcpy
import ast
import re
from _ast import Attribute, BoolOp, Call, Compare, Constant, Name
from datetime import datetime
from functools import cached_property
from inspect import getsource, signature
from types import SimpleNamespace
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    Type,
    TypeVar,
    Union,
)


class DataclassLike(Protocol):
    __dataclass_fields__: ClassVar[Dict[str, Any]]


class PydanticModelLike(Protocol):
    model_fields: ClassVar[Dict[str, Any]]


class PydanticV1ModelLike(Protocol):
    __fields__: ClassVar[Dict[str, Any]]


T = TypeVar("T", bound=Union[DataclassLike, PydanticModelLike, PydanticV1ModelLike])


class Mapper(Generic[T]):
    def __init__(self, data_path: str, **mapping: str) -> None:
        """Initializes the mapper.

        Args:
            data_path (str): Feature class path.
            mapping: Custom mapping of property to field.

        Examples:
            ```
            @dataclass
            class City:
                objectid: int = field(default=-1, init=False)
                city_name: str
                pop: int
                shape: arcpy.PointGeometry
                last_edited_date: datetime | None = field(default=None, init=False)

            mapper = Mapper[City]('world.gdb/cities')

            for city in mapper.read():
                print(city.city_name, city.shape.WKT)
            ```
        """
        self._data_path = data_path
        self._mapping = mapping

    @cached_property
    def info(self):
        return Info[T](self)

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
            filter: Where clause, lambda, object ids or global ids.  Defaults to None.
            wkid: Well-known id (e.g. 4326).  Defaults to None.

        Returns:
            Iterable[T]: Items.
        """
        if wkid is not None:
            kwargs["spatial_reference"] = arcpy.SpatialReference(wkid)
        data_path = self.info.data_path
        fields = list(self.info.properties.values())
        properties = self.info.properties
        for where_clause in self._get_where_clauses_from_filter(filter):
            with arcpy.da.SearchCursor(
                data_path, fields, where_clause, **kwargs
            ) as cursor:
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
            Optional[T]: Item if found.
        """
        for where_clause in self._get_where_clauses_from_ids(id):
            for item in self.read(where_clause, wkid):
                return item
        return None

    def insert_many(self, items: Iterable[T], **kwargs: Any) -> List[int]:
        """Inserts multiple items.

        Args:
            items: Items to insert.

        Returns:
            List[int]: List of object ids.
        """
        data_path = self.info.data_path
        fields = list(self.info.edit_properties.values())
        properties = self.info.edit_properties
        inserted: List[int] = []
        with arcpy.da.InsertCursor(data_path, fields, **kwargs) as cursor:
            for item in items:
                inserted.append(cursor.insertRow(self._get_values(item, properties)))
        return inserted

    def insert(self, item: T) -> T:
        """Inserts a single item.

        Args:
            item: Item to insert.

        Returns:
            T: Created item.
        """
        inserted_id = self.insert_many([item])[0]
        inserted = self.get(inserted_id)
        if not inserted:
            raise RuntimeError("Failed to insert item.")
        return inserted

    def update_where(
        self,
        filter: Union[str, Callable[[T], bool], Iterable[int], Iterable[str], None],
        update: Callable[[T], Union[None, T]],
        **kwargs: Any,
    ) -> List[int]:
        """Updates items based on a procedure.

        Args:
            filter: Where clause, lambda, object ids or global ids.  If None, all items are updated.
            update: Update procedure.  It may return an item (replacement) or None (mutation).

        Returns:
            List[int]: List of object ids.
        """
        data_path = self.info.data_path
        fields = list(self.info.edit_properties.values())
        properties = self.info.edit_properties
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_filter(filter):
            with arcpy.da.UpdateCursor(
                data_path, fields, where_clause, **kwargs
            ) as cursor:
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
        """Updates items based on their mutated state.

        Args:
            items: Items to update.

        Returns:
            List[int]: List of object ids.
        """
        if isinstance(items, self.info.model):
            items = [items]
        elif isinstance(items, Iterable):
            items = list(items)
        else:
            items = [items]
        cache = {self._get_oid(x): x for x in items}
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_ids(items):
            for id in self.update_where(
                where_clause, lambda x: cache[self._get_oid(x)]
            ):
                ids.add(id)
        return list(ids)

    def delete_where(self, filter: Union[str, Callable[[T], bool], None]) -> List[int]:
        """Deletes items based on a filter.

        Args:
            filter: Where clause or lambda.  If None, all items are deleted.

        Returns:
            List[int]: List of object ids.
        """
        data_path = self.info.data_path
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_filter(filter):
            with arcpy.da.UpdateCursor(
                data_path, self.info.oid_field, where_clause
            ) as cursor:
                for row in cursor:
                    cursor.deleteRow()
                    ids.add(row[0])
        return list(ids)

    def delete(
        self, items: Union[T, int, str, Iterable[T], Iterable[int], Iterable[str]]
    ) -> List[int]:
        """Deletes items specified or by object ids or global ids.

        Args:
            items: Items, object ids or global ids.

        Returns:
            List[int]: List of object ids.
        """
        ids: Set[int] = set()
        for where_clause in self._get_where_clauses_from_ids(items):
            for id in self.delete_where(where_clause):
                ids.add(id)
        return list(ids)

    def _create(self, **kwargs: Any) -> T:
        dataclass_params = getattr(self.info.model, "__dataclass_params__", None)
        is_dataclass = dataclass_params is not None
        has_init = getattr(dataclass_params, "init", True)
        is_frozen = bool(getattr(dataclass_params, "frozen", False))

        def assign_property(item: T, property_name: str, value: Any) -> None:
            if is_frozen:
                object.__setattr__(item, property_name, value)
            else:
                setattr(item, property_name, value)

        if is_dataclass and not has_init:
            item = self.info.model()
            for property in self.info.properties:
                assign_property(item, property, kwargs.get(property))
        else:
            constructor_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k in self.info.properties and k in self.info.keys
            }
            item = self.info.model(**constructor_kwargs)
            for property in self.info.properties:
                if property not in self.info.keys:
                    assign_property(item, property, kwargs.get(property))

        return item

    def _get_values(self, item: T, properties: Iterable[str]) -> List[Any]:
        values: List[Any] = []
        for property in properties:
            value = getattr(item, property, None)
            field_name = (
                properties[property] if isinstance(properties, dict) else property
            )
            if field_name == "SHAPE@" and isinstance(value, tuple) and len(value) >= 2:
                value = arcpy.PointGeometry(arcpy.Point(value[0], value[1]))
            values.append(value)
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
        if isinstance(obj, (int, str)):
            yield obj
        elif isinstance(obj, self.info.model):
            yield self._get_oid(obj)
        else:
            yield from (id for o in obj for id in self._get_ids(o))

    def _get_oid(self, item) -> int:
        if not self.info.oid_property:
            raise TypeError(
                f"'{self.info.model.__name__}' is missing the OID property."
            )
        return getattr(item, self.info.oid_property)


class Info(Generic[T]):
    def __init__(self, mapper: "Mapper[T]") -> None:
        if __orig_class__ := getattr(mapper, "__orig_class__", None):
            model = __orig_class__.__args__[0]
        else:
            model = SimpleNamespace

        self.model: Type[T] = model  # type: ignore
        if __dataclass_fields__ := getattr(model, "__dataclass_fields__", None):
            self.keys = [k for k, v in __dataclass_fields__.items() if v.init]
        elif model_fields := getattr(model, "model_fields", None):
            self.keys = list(model_fields.keys())
        elif __fields__ := getattr(model, "__fields__", None):
            self.keys = list(__fields__.keys())
        else:
            self.keys = [k for k in signature(model.__init__).parameters if k != "self"]

        description = arcpy.Describe(mapper._data_path)
        self.data_path: str = description.catalogPath
        self.oid_field: str
        self.oid_property: str
        self.properties: Dict[str, str] = {}
        self.edit_properties: Dict[str, str] = {}

        upper_fields: Dict[str, str] = {}
        upper_read_only_fields: Set[str] = set()
        for field in description.fields:
            if re.match(r"^(?!\d)[\w$]+$", field.name):
                upper_fields[field.name.upper()] = field.name
                if field.type == "OID":
                    self.oid_field = field.name
                elif not field.editable:
                    upper_read_only_fields.add(field.name.upper())

        def resolve_fields():
            if model == SimpleNamespace:
                upper_field_to_property: Dict[str, str] = {
                    f.upper(): p for p, f in mapper._mapping.items()
                }
                for upper_field, field in upper_fields.items():
                    property = upper_field_to_property.get(upper_field) or field
                    if upper_field == "SHAPE":
                        field = "SHAPE@"
                    yield property, field
            else:
                for model_type in reversed(model.mro()):
                    if __annotations__ := getattr(model_type, "__annotations__", None):
                        for property in __annotations__:
                            field = mapper._mapping.get(property) or property
                            upper_field = field.upper()
                            if upper_field == "SHAPE":
                                field = "SHAPE@"
                            elif upper_field.startswith("SHAPE_"):
                                field = upper_field.replace("SHAPE_", "SHAPE@")
                            elif upper_field not in upper_fields:
                                raise ValueError(
                                    f"Field '{field}' not found in {self.data_path}."
                                )
                            else:
                                field = upper_fields[upper_field]
                            yield property, field

        for property, field in resolve_fields():
            self.properties[property] = field
            if field == self.oid_field:
                self.oid_property = property
            if field.upper() not in upper_read_only_fields:
                self.edit_properties[property] = field


def to_sql(predicate: Callable[[T], bool], properties: Dict[str, str]) -> str:
    class LambdaFinder(ast.NodeVisitor):
        def __init__(self, expression: Any) -> None:
            super().__init__()

            self.freevars: Dict[str, Any] = {}

            for name in expression.__code__.co_names:
                if name in expression.__globals__:
                    self.freevars[name] = expression.__globals__[name]

            closure = expression.__closure__
            if closure:
                for name, value in zip(
                    expression.__code__.co_freevars, [x.cell_contents for x in closure]
                ):
                    self.freevars[name] = value

            line = getsource(expression).strip()

            if line.endswith(":"):
                line = f"{line}\n    pass"

            self.visit(ast.parse(line))

        def visit_Lambda(self, node: ast.Lambda) -> Any:
            self.expression = node

        @staticmethod
        def find(expression: Any):
            visitor = LambdaFinder(expression)
            return visitor.expression, visitor.freevars

    class LambdaVisitor(ast.NodeVisitor):
        def __init__(self, expression: ast.expr, freevars: Dict[str, Any]) -> None:
            super().__init__()
            self._expressions: List[Union[LambdaVisitor, str]] = []
            self._freevars = freevars
            self.visit(expression)

        def visit_Attribute(self, node: Attribute) -> Any:
            attr = node.attr
            value: Any = node.value
            if value.id in self._freevars:
                self._expressions.append(
                    self._get_sql_value(getattr(self._freevars[value.id], attr))
                )
            else:
                self._expressions.append(properties[attr])

        def visit_BoolOp(self, node: BoolOp) -> Any:
            self._expressions.append("(")
            expressions: List[Union[LambdaVisitor, str]] = []
            for value in node.values:
                expressions.append(LambdaVisitor(value, self._freevars))
                expressions.append(self._convert_op(node.op))
            expressions.pop()
            self._expressions.extend(expressions)
            self._expressions.append(")")

        def visit_Call(self, node: Call) -> Any:
            if not (func := getattr(node.func, "attr"), None):
                self.generic_visit(node)
                return
            if func == "startswith":
                field_name = properties[node.func.value.attr]  # type: ignore
                self._expressions.append(
                    f"{field_name} LIKE '{self._get_value(node.args[0])}%'"
                )
            elif func == "endswith":
                field_name = properties[node.func.value.attr]  # type: ignore
                self._expressions.append(
                    f"{field_name} LIKE '%{self._get_value(node.args[0])}'"
                )

        def visit_Compare(self, node: Compare) -> Any:
            op = node.ops[0]
            if isinstance(op, ast.In):
                field_name = properties[node.comparators[0].attr]  # type: ignore
                self._expressions.append(
                    f"{field_name} LIKE '%{self._get_value(node.left)}%'"
                )
            else:
                self._expressions.append(LambdaVisitor(node.left, self._freevars))
                self._expressions.append(self._convert_op(node.ops[0]))
                self._expressions.append(
                    LambdaVisitor(node.comparators[0], self._freevars)
                )

        def visit_Constant(self, node: Constant) -> Any:
            self._expressions.append(self._get_sql_value(node.value))

        def visit_Name(self, node: Name) -> Any:
            self._expressions.append(self._get_sql_value(self._freevars[node.id]))

        def _get_sql_value(self, value: Any) -> str:
            if value is None:
                return "NULL"
            if isinstance(value, str):
                return f"'{value}'"
            if isinstance(value, datetime):
                return f"timestamp '{value:%Y-%m-%d %H:%M:%S}'"
            return str(value)

        def _get_value(self, node: Any) -> Any:
            return self._freevars[node.id] if isinstance(node, Name) else node.value

        def _convert_op(self, op: Any) -> str:
            if isinstance(op, ast.And):
                return "AND"
            if isinstance(op, ast.Or):
                return "OR"
            if isinstance(op, ast.Is):
                return "IS"
            if isinstance(op, ast.IsNot):
                return "IS NOT"
            if isinstance(op, ast.Eq):
                return "="
            if isinstance(op, ast.NotEq):
                return "<>"
            if isinstance(op, ast.Gt):
                return ">"
            if isinstance(op, ast.GtE):
                return ">="
            if isinstance(op, ast.Lt):
                return "<"
            if isinstance(op, ast.LtE):
                return "<="
            return type(op).__name__

        def to_sql(self) -> str:
            text = ""
            for e in self._expressions:
                text += e.to_sql() if isinstance(e, LambdaVisitor) else f" {e}"
            return text

    expression, freevars = LambdaFinder.find(predicate)
    where_clause = LambdaVisitor(expression, freevars).to_sql().strip()

    return where_clause
