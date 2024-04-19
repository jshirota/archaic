import arcpy

from inspect import signature
from itertools import chain
from typing import Dict, Generic, Optional, Set, Type, TypeVar

T = TypeVar("T")


class Info(Generic[T]):
    def __init__(self, feature_class) -> None:
        self.model: Type[T] = feature_class.__orig_class__.__args__[0]

        description = arcpy.Describe(feature_class._table)
        self.catalog_path: str = description.catalogPath  # type: ignore

        field_names: Set[str] = set()
        edit_field_names: Set[str] = set(["OID@", "SHAPE@"])

        self.oid_field_name: Optional[str] = None
        self.oid_property_name: Optional[str] = None

        for field in description.fields:  # type: ignore
            field_name = field.name.upper()
            field_names.add(field_name)

            if field.editable:
                edit_field_names.add(field_name)

            if field.type == "OID":
                self.oid_field_name = field_name

        keys = chain(
            signature(self.model.__init__).parameters.keys(),
            signature(self.model.__new__).parameters.keys(),
        )

        self.has_parameterless_constructor = len(set(keys)) == 3

        def get_field_name(property: str):
            if property in feature_class._mapping:
                return feature_class._mapping[property].upper()

            field_name = property.upper()

            if field_name == "OID":
                self.oid_property_name = property
                return "OID@"
            if field_name == "SHAPE":
                return "SHAPE@"
            if field_name.startswith("SHAPE_"):
                return field_name.replace("SHAPE_", "SHAPE@")

            return field_name if field_name in field_names else None

        self.properties: Dict[str, Optional[str]] = {}
        self.edit_properties: Dict[str, str] = {}

        for model_type in reversed(self.model.mro()):
            if hasattr(model_type, "__annotations__"):
                for property in model_type.__annotations__:
                    field_name = get_field_name(property)
                    self.properties[property] = field_name

                    if field_name and field_name in edit_field_names:
                        self.edit_properties[property] = field_name
