"""Helpers for preserving typed JSON mapping keys."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping as AbcMapping
from collections.abc import MutableMapping as AbcMutableMapping
from functools import partial
from json import dumps as json_dumps
from json import loads as json_loads
from typing import Any, Callable

from .._compat import (
    Mapping,
    MutableMapping,
    get_args,
    get_origin,
    is_bare,
    is_counter,
    is_subclass,
)
from ..cols import is_defaultdict
from ..gen import mapping_structure_factory


def _has_typed_key(cl: Any) -> bool:
    """Does the mapping type declare a key other than a plain string?"""
    if is_bare(cl) or getattr(cl, "__args__", None) is None:
        return False

    args = get_args(cl)
    if not args:
        return False

    key_type = args[0]
    return not is_subclass(key_type, str)


def _make_key_decoder(loads: Callable[[str], Any]) -> Callable[[str], Any]:
    """Decode JSON-encoded keys while leaving malformed JSON to the key hook."""

    def decode_key(key: str) -> Any:
        try:
            return loads(key)
        except ValueError:
            return key

    return decode_key


def make_unstructure_mapping_factory(
    dumps: Callable[[Any], str] = json_dumps,
) -> Callable[..., Any]:
    """Create a mapping unstructure factory encoding typed keys as strings."""

    def unstructure_mapping_factory(cl: Any, converter: Any, unstructure_to=None):
        preserve_typed_key = _has_typed_key(cl)
        key_encoder = dumps if preserve_typed_key else None
        return converter.gen_unstructure_mapping(
            cl,
            unstructure_to=unstructure_to,
            key_encoder=key_encoder,
            check_key_collisions=preserve_typed_key,
        )

    return unstructure_mapping_factory


def make_structure_mapping_factory(
    loads: Callable[[str], Any] = json_loads,
) -> Callable[..., Any]:
    """Create a mapping structure factory decoding typed keys from strings."""

    def structure_mapping_factory(cl: Any, converter: Any):
        preserve_typed_key = _has_typed_key(cl)
        key_decoder = _make_key_decoder(loads) if preserve_typed_key else None

        if is_counter(cl):
            return mapping_structure_factory(
                cl,
                converter,
                structure_to=Counter,
                val_type=int,
                key_decoder=key_decoder,
                check_key_collisions=preserve_typed_key,
            )

        origin = get_origin(cl) or cl
        if origin in (Mapping, MutableMapping, AbcMapping, AbcMutableMapping):
            structure_to = dict
        elif is_defaultdict(cl):
            structure_to = partial(defaultdict, get_args(cl)[1])
        else:
            structure_to = origin

        return mapping_structure_factory(
            cl,
            converter,
            structure_to=structure_to,
            key_decoder=key_decoder,
            check_key_collisions=preserve_typed_key,
        )

    return structure_mapping_factory
