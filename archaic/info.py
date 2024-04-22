import arcpy
import re

from inspect import signature
from itertools import chain
from types import SimpleNamespace
from typing import Dict, Generic, Set, Type, TypeVar

T = TypeVar("T")


class Info(Generic[T]):
    def __init__(self, feature_class) -> None:
        if hasattr(feature_class, "__orig_class__"):
            self.model: Type[T] = feature_class.__orig_class__.__args__[0]
            self.dynamic = False
        else:
            self.model = SimpleNamespace  # type: ignore
            self.dynamic = True

        description = arcpy.Describe(feature_class._table)
        self.catalog_path: str = description.catalogPath  # type: ignore

        upper_field_names: Dict[str, str] = {}
        upper_read_only_field_names: Set[str] = set()

        self.oid_field_name: str
        self.oid_property_name: str

        for field in description.fields:  # type: ignore
            if not re.match(r"^(?!\d)[\w$]+$", field.name):
                continue

            upper_field_names[field.name.upper()] = field.name

            if field.type == "OID":
                self.oid_field_name = field.name
            elif not field.editable:
                upper_read_only_field_names.add(field.name.upper())

        keys = chain(
            signature(self.model.__init__).parameters.keys(),
            signature(self.model.__new__).parameters.keys(),
        )

        self.has_parameterless_constructor = len(set(keys)) == 3

        self.properties: Dict[str, str] = {}
        self.edit_properties: Dict[str, str] = {}

        if self.dynamic:
            for upper_field_name, field_name in upper_field_names.items():
                if field_name == self.oid_field_name:
                    self.oid_property_name = field_name
                self.properties[field_name] = field_name
                if upper_field_name not in upper_read_only_field_names:
                    self.edit_properties[field_name] = field_name
            return

        def get_field_name(property: str):
            field_name: str = feature_class._mapping.get(property) or property
            upper_field_name = property.upper()

            if upper_field_name == "SHAPE":
                return "SHAPE@"
            if upper_field_name.startswith("SHAPE_"):
                return upper_field_name.replace("SHAPE_", "SHAPE@")

            if upper_field_name not in upper_field_names:
                raise ValueError(f"'{field_name}' not found in {self.catalog_path}.")

            return upper_field_names[upper_field_name]

        for model_type in reversed(self.model.mro()):
            if hasattr(model_type, "__annotations__"):
                for property in model_type.__annotations__:
                    field_name = get_field_name(property)
                    if field_name == self.oid_field_name:
                        self.oid_property_name = property
                    self.properties[property] = field_name
                    if field_name.upper() not in upper_read_only_field_names:
                        self.edit_properties[property] = field_name
