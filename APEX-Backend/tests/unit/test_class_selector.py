import unittest

from app.core.config import settings
from app.domain.models.unit_test_report import ClassInventoryEntry, MethodInventoryEntry, ProjectInventory
from app.infrastructure.testing.class_selector import REASON_NO_MEANINGFUL_METHODS, _skip_reason, select_classes_for_generation


def _class(
    name: str,
    class_type: str,
    *,
    existing_test_count: int = 0,
    branch_count: int = 1,
    throws: bool = False,
    is_interface: bool = False,
    is_abstract: bool = False,
) -> ClassInventoryEntry:
    return ClassInventoryEntry(
        class_name=name,
        package_name="com.example",
        source_path=f"src/main/java/com/example/{name}.java",
        class_type=class_type,
        is_interface=is_interface,
        is_abstract=is_abstract,
        annotations=[],
        dependencies=[],
        methods=[
            MethodInventoryEntry(
                name="doWork", visibility="public", return_type="void",
                parameters=[], branch_count=branch_count, throws_exceptions=throws,
            )
        ],
        existing_test_class=None,
        existing_test_count=existing_test_count,
    )


class ClassSelectorTests(unittest.TestCase):
    def test_selects_eligible_untested_classes_only(self) -> None:
        inventory = ProjectInventory(
            project_dir="/tmp/project",
            production_file_count=5,
            test_file_count=0,
            production_classes=[
                _class("UserService", "SERVICE"),
                _class("UserDto", "DTO"),
                _class("AppConfig", "CONFIGURATION"),
                _class("OrderValidator", "VALIDATOR"),
            ],
            test_classes=[],
        )

        selected = select_classes_for_generation(inventory)

        self.assertEqual({c.class_name for c in selected}, {"UserService", "OrderValidator"})

    def test_skips_classes_that_already_have_tests(self) -> None:
        inventory = ProjectInventory(
            project_dir="/tmp/project",
            production_file_count=2,
            test_file_count=1,
            production_classes=[_class("UserService", "SERVICE", existing_test_count=3)],
            test_classes=[],
        )

        selected = select_classes_for_generation(inventory)

        self.assertEqual(selected, [])

    def test_prioritizes_service_before_utility_and_respects_max_classes(self) -> None:
        inventory = ProjectInventory(
            project_dir="/tmp/project",
            production_file_count=3,
            test_file_count=0,
            production_classes=[
                _class("StringUtils", "UTILITY"),
                _class("UserService", "SERVICE"),
                _class("PriceConverter", "CONVERTER"),
            ],
            test_classes=[],
        )

        selected = select_classes_for_generation(inventory, max_classes=2)

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0].class_name, "UserService")

    def test_excludes_classes_with_no_meaningful_methods(self) -> None:
        empty_service = ClassInventoryEntry(
            class_name="EmptyService", package_name="com.example",
            source_path="src/main/java/com/example/EmptyService.java",
            class_type="SERVICE", is_interface=False, is_abstract=False, annotations=[],
            dependencies=[], methods=[], existing_test_class=None, existing_test_count=0,
        )
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=1, test_file_count=0,
            production_classes=[empty_service], test_classes=[],
        )

        selected = select_classes_for_generation(inventory)

        self.assertEqual(selected, [])

    def test_interface_is_skipped_even_when_misclassified_as_service(self) -> None:
        # Defense-in-depth: even if a classifier bug ever again returns
        # "SERVICE" for an interface (the ITodoService regression), the
        # explicit is_interface check must still exclude it.
        interface_entry = _class("ITodoService", "SERVICE", is_interface=True)
        concrete_entry = _class("TodoService", "SERVICE")
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=2, test_file_count=0,
            production_classes=[interface_entry, concrete_entry], test_classes=[],
        )

        selected = select_classes_for_generation(inventory)

        self.assertEqual({c.class_name for c in selected}, {"TodoService"})

    def test_interface_classified_correctly_is_skipped(self) -> None:
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=1, test_file_count=0,
            production_classes=[_class("ITodoService", "INTERFACE_ONLY", is_interface=True)],
            test_classes=[],
        )

        selected = select_classes_for_generation(inventory)

        self.assertEqual(selected, [])

    def test_abstract_class_is_skipped(self) -> None:
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=1, test_file_count=0,
            production_classes=[_class("AbstractBaseService", "ABSTRACT_CLASS", is_abstract=True)],
            test_classes=[],
        )

        selected = select_classes_for_generation(inventory)

        self.assertEqual(selected, [])

    def test_skip_reasons_are_logged(self) -> None:
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=2, test_file_count=0,
            production_classes=[
                _class("ITodoService", "INTERFACE_ONLY", is_interface=True),
                _class("TodoService", "SERVICE"),
            ],
            test_classes=[],
        )

        with self.assertLogs("app.infrastructure.testing.class_selector", level="INFO") as captured:
            select_classes_for_generation(inventory)

        self.assertTrue(
            any("class=ITodoService" in line and "reason=INTERFACE" in line for line in captured.output)
        )


    def test_controller_other_converter_domain_and_entity_are_eligible_when_they_have_real_methods(self) -> None:
        # Controllers, SOAP clients/scheduled classes (OTHER), converters,
        # domain classes, and entities are generation candidates when the
        # inventory shows at least one non-accessor method.
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=5, test_file_count=0,
            production_classes=[
                _class("AttendanceController", "CONTROLLER"),
                _class("SoapClient", "OTHER", branch_count=0),
                _class("AttendanceReportLog", "ENTITY"),
                _class("PriceConverter", "CONVERTER"),
                _class("AttendanceRecord", "DOMAIN"),
            ],
            test_classes=[],
        )

        selected = select_classes_for_generation(inventory, max_classes=10)

        self.assertEqual(
            {c.class_name for c in selected},
            {"AttendanceController", "SoapClient", "AttendanceReportLog", "PriceConverter", "AttendanceRecord"},
        )

    def test_entity_with_only_getters_and_setters_is_still_skipped(self) -> None:
        pure_service = ClassInventoryEntry(
            class_name="EmptyGetterSetterService", package_name="com.example",
            source_path="src/main/java/com/example/EmptyGetterSetterService.java",
            class_type="SERVICE", is_interface=False, is_abstract=False, annotations=[], dependencies=[],
            methods=[
                MethodInventoryEntry(
                    name="getId", visibility="public", return_type="Long",
                    parameters=[], branch_count=0, throws_exceptions=False,
                ),
                MethodInventoryEntry(
                    name="setId", visibility="public", return_type="void",
                    parameters=[{"type": "Long", "name": "id"}], branch_count=0, throws_exceptions=False,
                ),
            ],
            existing_test_class=None, existing_test_count=0,
        )
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=1, test_file_count=0,
            production_classes=[pure_service], test_classes=[],
        )

        self.assertEqual(_skip_reason(pure_service), REASON_NO_MEANINGFUL_METHODS)
        self.assertEqual(select_classes_for_generation(inventory), [])

    def test_unbounded_when_configured_max_classes_is_none(self) -> None:
        # `max_classes` not given at the call site falls back to
        # settings.unit_test_generation_max_classes -- setting that to None
        # (rather than its configured default) is unbounded: every eligible
        # class gets generation.
        original = settings.unit_test_generation_max_classes
        settings.unit_test_generation_max_classes = None
        try:
            classes = [_class(f"Service{i}", "SERVICE") for i in range(12)]
            inventory = ProjectInventory(
                project_dir="/tmp/project", production_file_count=12, test_file_count=0,
                production_classes=classes, test_classes=[],
            )

            selected = select_classes_for_generation(inventory)
        finally:
            settings.unit_test_generation_max_classes = original

        self.assertEqual(len(selected), 12)

    def test_uses_configured_generation_max_classes_when_set(self) -> None:
        # settings.unit_test_generation_max_classes (UNIT_TEST_GENERATION_MAX_CLASSES)
        # defaults to a small number (2); a deployment can raise or lower it
        # to bound how many Groq calls/Maven runs a single migration job
        # can trigger.
        original = settings.unit_test_generation_max_classes
        settings.unit_test_generation_max_classes = 3
        try:
            classes = [_class(f"Service{i}", "SERVICE") for i in range(12)]
            inventory = ProjectInventory(
                project_dir="/tmp/project", production_file_count=12, test_file_count=0,
                production_classes=classes, test_classes=[],
            )

            selected = select_classes_for_generation(inventory)
        finally:
            settings.unit_test_generation_max_classes = original

        self.assertEqual(len(selected), 3)

    def test_main_application_and_repository_interface_stay_excluded(self) -> None:
        inventory = ProjectInventory(
            project_dir="/tmp/project", production_file_count=2, test_file_count=0,
            production_classes=[
                _class("ProjectApplication", "MAIN_APPLICATION"),
                _class("AttendanceReportLogRepository", "REPOSITORY_INTERFACE", is_interface=True),
            ],
            test_classes=[],
        )

        selected = select_classes_for_generation(inventory)

        self.assertEqual(selected, [])


if __name__ == "__main__":
    unittest.main()
