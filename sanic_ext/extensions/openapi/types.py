import json
import uuid
from datetime import date, datetime, time
from enum import Enum
from inspect import getmembers, isfunction, ismethod
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from sanic_ext.utils.typing import is_generic


class Definition:
    __nullable__: Optional[List[str]] = []
    __ignore__: Optional[List[str]] = []

    def __init__(self, **kwargs):
        self._fields: Dict[str, Any] = self.guard(kwargs)

    @property
    def fields(self):
        return self._fields

    def guard(self, fields):
        return {
            k: v
            for k, v in fields.items()
            if k in _properties(self).keys() or k.startswith("x-")
        }

    def serialize(self):
        return {
            k: self._value(v)
            for k, v in _serialize(self.fields).items()
            if (
                k not in self.__ignore__
                and (
                    v
                    or (
                        isinstance(self.__nullable__, list)
                        and (not self.__nullable__ or k in self.__nullable__)
                    )
                )
            )
        }

    def __str__(self):
        return json.dumps(self.serialize())

    @staticmethod
    def _value(value):
        if isinstance(value, Enum):
            return value.value
        return value


class Schema(Definition):
    title: str
    description: str
    type: str
    format: str
    nullable: bool
    required: bool
    default: None
    example: None
    oneOf: List[Definition]
    anyOf: List[Definition]
    allOf: List[Definition]

    additionalProperties: Dict[str, str]
    multipleOf: int
    maximum: int
    exclusiveMaximum: bool
    minimum: int
    exclusiveMinimum: bool
    maxLength: int
    minLength: int
    pattern: str
    enum: Union[List[Any], Enum]

    @staticmethod
    def make(value, **kwargs):
        _type = type(value)
        origin = get_origin(value)
        args = get_args(value)
        if origin is Union:
            if type(None) in args:
                kwargs["nullable"] = True

            filtered = [arg for arg in args if arg is not type(None)]  # noqa

            if len(filtered) == 1:
                return Schema.make(filtered[0], **kwargs)
            return Schema(
                oneOf=[Schema.make(arg) for arg in filtered], **kwargs
            )
            # return Schema.make(value, **kwargs)

        if isinstance(value, Schema):
            return value
        if value == bool:
            return Boolean(**kwargs)
        elif value == int:
            return Integer(**kwargs)
        elif value == float:
            return Float(**kwargs)
        elif value == str:
            return String(**kwargs)
        elif value == bytes:
            return Byte(**kwargs)
        elif value == bytearray:
            return Binary(**kwargs)
        elif value == date:
            return Date(**kwargs)
        elif value == time:
            return Time(**kwargs)
        elif value == datetime:
            return DateTime(**kwargs)
        elif value == uuid.UUID:
            return UUID(**kwargs)
        elif value == Any:
            return AnyValue(**kwargs)

        if _type == bool:
            return Boolean(default=value, **kwargs)
        elif _type == int:
            return Integer(default=value, **kwargs)
        elif _type == float:
            return Float(default=value, **kwargs)
        elif _type == str:
            return String(default=value, **kwargs)
        elif _type == bytes:
            return Byte(default=value, **kwargs)
        elif _type == bytearray:
            return Binary(default=value, **kwargs)
        elif _type == date:
            return Date(**kwargs)
        elif _type == time:
            return Time(**kwargs)
        elif _type == datetime:
            return DateTime(**kwargs)
        elif _type == uuid.UUID:
            return UUID(**kwargs)
        elif _type == list:
            if len(value) == 0:
                schema = Schema(nullable=True)
            elif len(value) == 1:
                schema = Schema.make(value[0])
            else:
                schema = Schema(oneOf=[Schema.make(x) for x in value])

            return Array(schema, **kwargs)
        elif _type == dict:
            return Object.make(value, **kwargs)
        elif (
            (is_generic(value) or is_generic(_type))
            and origin == dict
            and len(args) == 2
        ):
            kwargs["additionalProperties"] = Schema.make(args[1])
            return Object(**kwargs)
        elif (is_generic(value) or is_generic(_type)) and origin == list:
            return Array(Schema.make(args[0]), **kwargs)
        elif _type is type(Enum):
            available = [item.value for item in value.__members__.values()]
            available_types = list({type(item) for item in available})
            schema_type = (
                available_types[0] if len(available_types) == 1 else "string"
            )
            return Schema.make(
                schema_type,
                enum=[item.value for item in value.__members__.values()],
            )
        else:
            return Object.make(value, **kwargs)


class Boolean(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="boolean", **kwargs)


class Integer(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="integer", format="int32", **kwargs)


class Long(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="integer", format="int64", **kwargs)


class Float(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="number", format="float", **kwargs)


class Double(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="number", format="double", **kwargs)


class String(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", **kwargs)


class Byte(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="byte", **kwargs)


class Binary(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="binary", **kwargs)


class Date(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="date", **kwargs)


class Time(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="time", **kwargs)


class DateTime(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="date-time", **kwargs)


class Password(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="password", **kwargs)


class Email(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="email", **kwargs)


class UUID(Schema):
    def __init__(self, **kwargs):
        super().__init__(type="string", format="uuid", **kwargs)


class AnyValue(Schema):
    @classmethod
    def make(cls, value: Any, **kwargs):
        return cls(
            AnyValue={},
            **kwargs,
        )


class Object(Schema):
    properties: Dict[str, Schema]
    maxProperties: int
    minProperties: int

    def __init__(
        self, properties: Optional[Dict[str, Schema]] = None, **kwargs
    ):
        if properties:
            kwargs["properties"] = properties
        super().__init__(type="object", **kwargs)

    @classmethod
    def make(cls, value: Any, **kwargs):
        if hasattr(value, "__fields__"):
            properties = {}
            for k, v in _properties(value).items():
                fields = getattr(value, "__fields__", None)
                field_info = {}
                if fields:
                    field_info = _get_field_info(fields[k].field_info)
                    if field_info.get("disable_doc"):
                        continue

                properties[k] = Schema.make(
                    v,
                    **field_info
                )
        else:
            properties = {
                k: Schema.make(v) for k, v in _properties(value).items()
            }

        return cls(
            properties,
            **kwargs,
        )


class Array(Schema):
    items: Any
    maxItems: int
    minItems: int
    uniqueItems: bool

    def __init__(self, items: Any, **kwargs):
        super().__init__(type="array", items=Schema.make(items), **kwargs)


def _serialize(value) -> Any:
    if isinstance(value, Definition):
        return value.serialize()

    if isinstance(value, type) and issubclass(value, Enum):
        return [item.value for item in value.__members__.values()]

    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_serialize(v) for v in value]

    return value


def _properties(value: object) -> Dict:
    try:
        fields = {
            x: val
            for x, v in getmembers(value, _is_property)
            if (val := _extract(v)) and x in value.__dict__
        }
    except AttributeError:
        fields = {}

    cls = value if callable(value) else value.__class__
    return {
        k: v
        for k, v in {**get_type_hints(cls), **fields}.items()
        if not k.startswith("_")
    }


def _get_field_info(field_info):
    field_data = {}
    for field_key in ["description", "extra"]:
        value = getattr(field_info, field_key, None)
        if value:
            if isinstance(value, dict):
                field_data.update(value)
            else:
                field_data[field_key] = value

    if "default_value" in field_data:
        field_data["default"] = field_data.pop("default_value")
    return field_data


def _extract(item):
    if isinstance(item, property):
        hints = get_type_hints(item.fget)
        return hints.get("return")
    return item


def _is_property(item):
    return not isfunction(item) and not ismethod(item)
