"""EvidenceGroup ⇄ JSON для хранения рядом со снимком процесса.

Кодек обходит dataclass-поля по аннотациям, поэтому новое поле модели с
значением по умолчанию не ломает чтение старых строк (его просто нет в JSON).
"""

from __future__ import annotations

import dataclasses
import types
import typing
from datetime import date, datetime
from enum import Enum
from typing import Any

from kontur.domain.models import EvidenceGroup


def encode(value: object) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    return value


def _decode(tp: Any, raw: Any) -> Any:
    origin = typing.get_origin(tp)
    if origin in (typing.Union, types.UnionType):
        arms = typing.get_args(tp)
        if raw is None and type(None) in arms:
            return None
        for arm in arms:
            if arm is type(None):
                continue
            if arm in (str, float, bool, int) and isinstance(raw, arm):
                return raw
        if isinstance(raw, int) and float in arms and not isinstance(raw, bool):
            return float(raw)
        for arm in arms:
            if arm is type(None) or arm in (str, float, bool, int):
                continue
            return _decode(arm, raw)
        raise ValueError(f"значение {raw!r} не подходит к {tp}")
    if origin is tuple:
        args = typing.get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in raw)
        return tuple(_decode(arg, item) for arg, item in zip(args, raw, strict=True))
    if origin is dict:
        _key, item_tp = typing.get_args(tp)
        return {str(key): _decode(item_tp, item) for key, item in raw.items()}
    if isinstance(tp, type):
        if dataclasses.is_dataclass(tp):
            hints = typing.get_type_hints(tp)
            kwargs = {
                f.name: _decode(hints[f.name], raw[f.name])
                for f in dataclasses.fields(tp)
                if f.name in raw
            }
            return tp(**kwargs)
        if issubclass(tp, Enum):
            return tp(raw)
        if tp is datetime:
            return datetime.fromisoformat(raw)
        if tp is date:
            return date.fromisoformat(raw)
        if tp is float and isinstance(raw, int) and not isinstance(raw, bool):
            return float(raw)
    return raw


def encode_group(group: EvidenceGroup) -> dict[str, Any]:
    payload: dict[str, Any] = encode(group)
    return payload


def decode_group(payload: dict[str, Any]) -> EvidenceGroup:
    group = _decode(EvidenceGroup, payload)
    assert isinstance(group, EvidenceGroup)
    return group
