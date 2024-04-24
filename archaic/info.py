import arcpy
import re

from inspect import signature
from itertools import chain
from types import SimpleNamespace
from typing import Dict, Generic, Set, Type, TypeVar

T = TypeVar("T")


class Info(Generic[T]):
    def __init__(self, feature_class) -> None:
        description = arcpy.Describe(feature_class._data_path)

        # Members.
        self.model: Type[T] = (  # type: ignore
            feature_class.__orig_class__.__args__[0]
            if hasattr(feature_class, "__orig_class__")
            else SimpleNamespace
        )
        self.has_default_constructor = (
            len(
                set(
                    chain(
                        signature(self.model.__init__).parameters.keys(),
                        signature(self.model.__new__).parameters.keys(),
                    )
                )
            )
            == 3
        )
        self.data_path: str = description.catalogPath  # type: ignore
        self.oid_field: str
        self.oid_property: str
        self.properties: Dict[str, str] = {}
        self.edit_properties: Dict[str, str] = {}

        # Inspect the fields.
        upper_fields: Dict[str, str] = {}
        upper_read_only_fields: Set[str] = set()
        for field in description.fields:  # type: ignore
            if re.match(r"^(?!\d)[\w$]+$", field.name):
                upper_fields[field.name.upper()] = field.name
                if field.type == "OID":
                    self.oid_field = field.name
                elif not field.editable:
                    upper_read_only_fields.add(field.name.upper())

        def resolve_fields():
            if self.model == SimpleNamespace:
                upper_field_to_property: Dict[str, str] = {
                    f.upper(): p for p, f in feature_class._mapping.items()
                }
                for upper_field, field in upper_fields.items():
                    property = upper_field_to_property.get(upper_field) or field
                    if upper_field == "SHAPE":
                        field = "SHAPE@"
                    yield property, field
            else:
                for model_type in reversed(self.model.mro()):
                    if hasattr(model_type, "__annotations__"):
                        for property in model_type.__annotations__:
                            field = feature_class._mapping.get(property) or property
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
