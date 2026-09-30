from collections import Counter
from dataclasses import dataclass
from typing import Union

import pytest
from attrs import define

from cattrs import Converter, MappingKeyCollisionError
from cattrs.preconf.json import make_converter as make_json_converter
from cattrs.preconf.orjson import make_converter as make_orjson_converter
from cattrs.v import transform_error


@define(frozen=True)
class Coordinate:
    x: int
    y: int


@define
class Record:
    name: str
    count: int
    stats: dict[Coordinate, int]


@define
class IntRecord:
    name: str
    stats: dict[int, int]


@dataclass
class DataclassRecord:
    stats: dict[Coordinate, int]


@define
class StringRecord:
    name: str
    stats: dict[str, int]


@pytest.fixture(params=(make_json_converter, make_orjson_converter))
def preconf_converter(request):
    return request.param(lossless_mapping_keys=True)


def test_converter_unstructure_structure_roundtrip():
    converter = Converter(lossless_mapping_keys=True)
    mapping = {Coordinate(1, 2): 3}

    unstructured = converter.unstructure(mapping, unstructure_as=dict[Coordinate, int])
    assert unstructured == {'{"x":1,"y":2}': 3}
    assert converter.structure(unstructured, dict[Coordinate, int]) == mapping


def test_typed_mapping_keys_roundtrip_directly(preconf_converter):
    mapping = {Coordinate(1, 2): 3, Coordinate(4, 5): 6}

    encoded = preconf_converter.dumps(mapping, unstructure_as=dict[Coordinate, int])
    restored = preconf_converter.loads(encoded, dict[Coordinate, int])

    assert restored == mapping
    assert next(iter(restored)) == Coordinate(1, 2)


def test_typed_mapping_keys_roundtrip_in_attrs(preconf_converter):
    record = Record("example", 7, {Coordinate(1, 2): 3, Coordinate(4, 5): 6})

    encoded = preconf_converter.dumps(record)
    restored = preconf_converter.loads(encoded, Record)

    assert restored == record
    assert isinstance(restored, Record)
    assert next(iter(restored.stats)) == Coordinate(1, 2)


def test_typed_mapping_keys_roundtrip_in_dataclass(preconf_converter):
    record = DataclassRecord({Coordinate(1, 2): 3})

    encoded = preconf_converter.dumps(record)
    restored = preconf_converter.loads(encoded, DataclassRecord)

    assert restored == record
    assert next(iter(restored.stats)) == Coordinate(1, 2)


def test_typed_counter_keys_roundtrip(preconf_converter):
    counter = Counter({Coordinate(1, 2): 3})

    encoded = preconf_converter.dumps(counter, unstructure_as=Counter[Coordinate])
    restored = preconf_converter.loads(encoded, Counter[Coordinate])

    assert restored == counter
    assert isinstance(restored, Counter)


def test_structuring_key_collision_is_reported(preconf_converter):
    raw = {"01": 1, "1": 2}

    with pytest.raises(Exception) as exc_info:
        preconf_converter.structure(raw, dict[int, int])

    collision = exc_info.value.exceptions[0]
    assert isinstance(collision, MappingKeyCollisionError)
    assert collision.conflicting_keys == ("01", "1")


def test_structuring_key_collision_is_reported_in_attrs():
    converter = make_json_converter(lossless_mapping_keys=True)
    raw = {"name": "example", "stats": {"01": 1, "1": 2}}

    with pytest.raises(Exception) as exc_info:
        converter.structure(raw, IntRecord)

    messages = transform_error(exc_info.value)
    message = "\n".join(messages)
    assert "stats" in message
    assert repr("01") in message
    assert repr("1") in message


def test_unstructuring_key_collision_is_reported(preconf_converter):
    converter = make_json_converter(lossless_mapping_keys=True)

    class First:
        pass

    class Second:
        pass

    converter.register_unstructure_hook(First, lambda value: "same")
    converter.register_unstructure_hook(Second, lambda value: "same")

    with pytest.raises(MappingKeyCollisionError):
        converter.unstructure(
            {First(): 1, Second(): 2}, dict[Union[First, Second], int]
        )


def test_orjson_default_key_coercion_is_unchanged():
    converter = make_orjson_converter()

    unstructured = converter.unstructure({1: 2}, unstructure_as=dict[int, int])

    assert unstructured == {"1": 2}
    assert converter.structure(unstructured, dict[int, int]) == {1: 2}


def test_registered_key_hooks_continue_to_apply():
    converter = make_json_converter(lossless_mapping_keys=True)
    converter.register_unstructure_hook(Coordinate, lambda value: [value.x, value.y])
    converter.register_structure_hook(
        Coordinate, lambda value, _: Coordinate(value[0], value[1])
    )

    restored = converter.structure(
        converter.unstructure(
            {Coordinate(1, 2): 3}, unstructure_as=dict[Coordinate, int]
        ),
        dict[Coordinate, int],
    )

    assert restored == {Coordinate(1, 2): 3}


def test_lossless_collision_without_detailed_validation():
    converter = make_json_converter(
        lossless_mapping_keys=True, detailed_validation=False
    )

    with pytest.raises(MappingKeyCollisionError):
        converter.structure({"01": 1, "1": 2}, dict[int, int])


def test_existing_string_key_json_shape_is_unchanged():
    converter = make_json_converter()
    raw = {"stats": {"one": 1, "two": 2}, "name": "example"}

    assert converter.unstructure(
        StringRecord("example", {}), unstructure_as=StringRecord
    ) == {"stats": {}, "name": "example"}
    assert converter.dumps({"one": 1, "two": 2}) == '{"one": 1, "two": 2}'
    assert converter.structure(raw, StringRecord) == StringRecord(
        "example", {"one": 1, "two": 2}
    )
