from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .client import get_dotted
from .models import ValidationFailure

_MISSING = object()
_ASSERTION_KEYS = {"contains", "equals", "exists", "not_null", "is_null"}

ValueResolver = Callable[[str, Any], Any]


def validate_incident(
    incident: dict[str, Any],
    expectations: dict[str, Any],
    *,
    value_resolver: ValueResolver | None = None,
) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    for path, expectation in expectations.items():
        actual = get_dotted(incident, path, default=_MISSING)
        if isinstance(expectation, dict) and _is_assertion_dict(expectation):
            for assertion, expected in expectation.items():
                failure = _validate_assertion(path, assertion, expected, actual, value_resolver=value_resolver)
                if failure:
                    failures.append(failure)
        else:
            failure = _validate_assertion(path, "equals", expectation, actual, value_resolver=value_resolver)
            if failure:
                failures.append(failure)
    return failures


def _is_assertion_dict(value: dict[str, Any]) -> bool:
    return any(key in _ASSERTION_KEYS for key in value)


def _validate_assertion(
    path: str,
    assertion: str,
    expected: Any,
    actual: Any,
    *,
    value_resolver: ValueResolver | None = None,
) -> ValidationFailure | None:
    if assertion == "equals":
        passed = actual is not _MISSING and _equals(path, actual, expected, value_resolver)
    elif assertion == "contains":
        passed = actual is not _MISSING and _contains(_resolve_actual(path, actual, value_resolver), expected)
    elif assertion == "exists":
        should_exist = bool(expected)
        passed = (actual is not _MISSING) is should_exist
    elif assertion == "not_null":
        passed = actual is not _MISSING and actual is not None
    elif assertion == "is_null":
        passed = actual is _MISSING or actual is None
    else:
        return ValidationFailure(path, assertion, expected, _display_actual(actual), f"unsupported assertion '{assertion}'")

    if passed:
        return None
    return ValidationFailure(
        path=path,
        assertion=assertion,
        expected=expected,
        actual=_display_actual(_resolve_actual(path, actual, value_resolver)),
        message=f"{path} {assertion} failed",
    )


def _equals(path: str, actual: Any, expected: Any, value_resolver: ValueResolver | None) -> bool:
    resolved_actual = _resolve_actual(path, actual, value_resolver)
    if actual == expected or resolved_actual == expected:
        return True
    if isinstance(resolved_actual, (list, tuple, set)) and not isinstance(expected, (list, tuple, set)):
        return expected in resolved_actual
    return False


def _resolve_actual(path: str, actual: Any, value_resolver: ValueResolver | None) -> Any:
    if value_resolver is None or actual is _MISSING:
        return actual
    return value_resolver(path, actual)


def _contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (list, tuple, set, str)):
        return expected in actual
    if isinstance(actual, dict):
        return expected in actual.values() or expected in actual.keys()
    return False


def _display_actual(actual: Any) -> Any:
    if actual is _MISSING:
        return "<missing>"
    return actual
