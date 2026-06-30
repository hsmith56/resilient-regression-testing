from __future__ import annotations

from typing import Any

from .client import get_dotted
from .models import ValidationFailure

_MISSING = object()


def validate_incident(incident: dict[str, Any], expectations: dict[str, Any]) -> list[ValidationFailure]:
    failures: list[ValidationFailure] = []
    for path, expectation in expectations.items():
        actual = get_dotted(incident, path, default=_MISSING)
        if isinstance(expectation, dict) and _is_assertion_dict(expectation):
            for assertion, expected in expectation.items():
                failure = _validate_assertion(path, assertion, expected, actual)
                if failure:
                    failures.append(failure)
        else:
            failure = _validate_assertion(path, "equals", expectation, actual)
            if failure:
                failures.append(failure)
    return failures


def _is_assertion_dict(value: dict[str, Any]) -> bool:
    return any(key in {"contains", "equals", "exists", "not_null", "is_null"} for key in value)


def _validate_assertion(path: str, assertion: str, expected: Any, actual: Any) -> ValidationFailure | None:
    if assertion == "equals":
        passed = actual is not _MISSING and actual == expected
    elif assertion == "contains":
        passed = actual is not _MISSING and _contains(actual, expected)
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
        actual=_display_actual(actual),
        message=f"{path} {assertion} failed",
    )


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
