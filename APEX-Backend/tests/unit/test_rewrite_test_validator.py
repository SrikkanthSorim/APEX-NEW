from app.domain.models.unit_test_report import ClassInventoryEntry, MethodInventoryEntry
from app.infrastructure.testing.rewrite_test_validator import RewriteTestValidator

_CLASS_ENTRY = ClassInventoryEntry(
    class_name="UserService",
    package_name="com.example.service",
    source_path="src/main/java/com/example/service/UserService.java",
    class_type="SERVICE",
    is_interface=False,
    is_abstract=False,
    annotations=[],
    dependencies=["UserRepository"],
    methods=[
        MethodInventoryEntry(
            name="createUser", visibility="public", return_type="User",
            parameters=[{"name": "request", "type": "UserRequest"}],
            branch_count=1, throws_exceptions=False,
        )
    ],
    existing_test_class=None,
    existing_test_count=0,
)

_VALID_RESPONSE = {
    "testClassName": "UserServiceTest",
    "packageName": "com.example.service",
    "targetPath": "src/test/java/com/example/service/UserServiceTest.java",
    "framework": "JUNIT_5",
    "testCases": [
        {
            "methodName": "createUser_shouldCreateUser_whenValid",
            "type": "POSITIVE",
            "targetMethod": "createUser",
            "scenario": "valid request",
            "expectedResult": "user created",
        }
    ],
    "sourceCode": "package com.example.service;\nclass UserServiceTest { void createUser_shouldCreateUser_whenValid() {} }",
}


def _validator_with_parse_result(monkeypatch, parse_result: dict):
    validator = RewriteTestValidator()
    monkeypatch.setattr(validator, "_parse_source", lambda source: parse_result)
    return validator


def _matching_parse_result() -> dict:
    return {
        "valid": True,
        "packageName": "com.example.service",
        "className": "UserServiceTest",
        "imports": [],
        "parseErrors": [],
    }


def test_validate_schema_reports_missing_fields():
    validator = RewriteTestValidator()
    errors = validator.validate_schema({"testClassName": "Foo"})
    assert any("packageName" in e for e in errors)
    assert any("sourceCode" in e for e in errors)


def test_validate_schema_accepts_well_formed_response():
    validator = RewriteTestValidator()
    errors = validator.validate_schema(_VALID_RESPONSE)
    assert errors == []


def test_validate_accepts_a_fully_valid_response(monkeypatch):
    validator = _validator_with_parse_result(monkeypatch, _matching_parse_result())
    result = validator.validate(_VALID_RESPONSE, class_entry=_CLASS_ENTRY, existing_test_class_names=set())
    assert result.valid is True
    assert result.errors == []
    assert result.class_name == "UserServiceTest"


def test_validate_rejects_duplicate_test_class(monkeypatch):
    validator = _validator_with_parse_result(monkeypatch, _matching_parse_result())
    result = validator.validate(
        _VALID_RESPONSE, class_entry=_CLASS_ENTRY, existing_test_class_names={"UserServiceTest"},
    )
    assert result.valid is False
    assert any("Duplicate test class" in e for e in result.errors)


def test_validate_rejects_package_mismatch(monkeypatch):
    validator = _validator_with_parse_result(monkeypatch, _matching_parse_result())
    response = {**_VALID_RESPONSE, "packageName": "com.example.other"}
    result = validator.validate(response, class_entry=_CLASS_ENTRY, existing_test_class_names=set())
    assert result.valid is False
    assert any("does not match production class package" in e for e in result.errors)


def test_validate_rejects_unknown_target_method(monkeypatch):
    validator = _validator_with_parse_result(monkeypatch, _matching_parse_result())
    response = {
        **_VALID_RESPONSE,
        "testCases": [{**_VALID_RESPONSE["testCases"][0], "targetMethod": "deleteEverything"}],
    }
    result = validator.validate(response, class_entry=_CLASS_ENTRY, existing_test_class_names=set())
    assert result.valid is False
    assert any("deleteEverything" in e for e in result.errors)


def test_validate_rejects_forbidden_placeholder_assertion(monkeypatch):
    validator = _validator_with_parse_result(monkeypatch, _matching_parse_result())
    response = {**_VALID_RESPONSE, "sourceCode": _VALID_RESPONSE["sourceCode"] + "\nassertTrue(true);"}
    result = validator.validate(response, class_entry=_CLASS_ENTRY, existing_test_class_names=set())
    assert result.valid is False
    assert any("disallowed placeholder assertion" in e for e in result.errors)


def test_validate_rejects_when_openrewrite_parse_fails(monkeypatch):
    validator = _validator_with_parse_result(
        monkeypatch, {"valid": False, "parseErrors": ["expected ';'"], "packageName": None, "className": None, "imports": []},
    )
    result = validator.validate(_VALID_RESPONSE, class_entry=_CLASS_ENTRY, existing_test_class_names=set())
    assert result.valid is False
    assert "expected ';'" in result.errors


def test_validate_rejects_duplicate_method_names_within_response(monkeypatch):
    validator = _validator_with_parse_result(monkeypatch, _matching_parse_result())
    duplicate_case = _VALID_RESPONSE["testCases"][0]
    response = {**_VALID_RESPONSE, "testCases": [duplicate_case, duplicate_case]}
    result = validator.validate(response, class_entry=_CLASS_ENTRY, existing_test_class_names=set())
    assert result.valid is False
    assert any("Duplicate test method name" in e for e in result.errors)
