"""Проверки мёртвого кода: настройки и API-схемы должны иметь потребителя в ``src``.

Это регрессионные тесты против YAGNI-мусора: настройка ``Settings`` или Pydantic-схема
ответа, которая встречается только в своём модуле, является мусором — её либо подключают
к реальному сценарию, либо удаляют.
"""

import inspect
import re
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel

import deribit_tracker
from deribit_tracker.api import schemas
from deribit_tracker.config import Settings

PACKAGE_ROOT = Path(deribit_tracker.__file__).resolve().parent


def _names_used_outside(module_file_name: str, names: Iterable[str]) -> set[str]:
    """Возвращает имена, которые не упоминаются ни в одном модуле, кроме указанного."""
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PACKAGE_ROOT.rglob("*.py")
        if path.name != module_file_name
    )
    return {name for name in names if re.search(rf"\b{re.escape(name)}\b", sources) is None}


def test_every_setting_is_used_outside_config() -> None:
    unused = _names_used_outside("config.py", Settings.model_fields)

    assert unused == set(), (
        f"настройки без потребителя в src (мёртвая конфигурация): {sorted(unused)}"
    )


def test_every_api_schema_is_used_outside_schemas_module() -> None:
    schema_names = [
        name
        for name, value in inspect.getmembers(schemas, inspect.isclass)
        if issubclass(value, BaseModel) and value.__module__ == schemas.__name__
    ]

    unused = _names_used_outside("schemas.py", schema_names)

    assert unused == set(), (
        f"схемы ответа без потребителя в src (мёртвый контракт): {sorted(unused)}"
    )
