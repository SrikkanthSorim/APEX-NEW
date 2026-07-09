import tempfile
from pathlib import Path
from unittest import TestCase

from app.infrastructure.build.gradle_wrapper_upgrader import GradleWrapperUpgrader

_PROPS = (
    "distributionBase=GRADLE_USER_HOME\n"
    "distributionUrl=https\\://services.gradle.org/distributions/gradle-{v}-bin.zip\n"
    "zipStoreBase=GRADLE_USER_HOME\n"
)


class GradleWrapperUpgraderTest(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.props = self.project / "gradle" / "wrapper" / "gradle-wrapper.properties"
        self.props.parent.mkdir(parents=True)
        self.upgrader = GradleWrapperUpgrader()

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, version):
        self.props.write_text(_PROPS.format(v=version), encoding="utf-8")

    def _url(self):
        for line in self.props.read_text(encoding="utf-8").splitlines():
            if line.startswith("distributionUrl"):
                return line
        return ""

    def test_bumps_old_wrapper_for_java21(self):
        self._write("7.6.1")
        lines = self.upgrader.ensure_compatible(self.project, 21)
        self.assertEqual(len(lines), 1)
        self.assertIn("7.6.1 -> 8.9", lines[0])
        self.assertIn("gradle-8.9-bin.zip", self._url())

    def test_does_not_downgrade_newer_wrapper(self):
        self._write("8.10")
        lines = self.upgrader.ensure_compatible(self.project, 21)
        self.assertEqual(lines, [])
        self.assertIn("gradle-8.10-bin.zip", self._url())

    def test_idempotent_when_already_recommended(self):
        self._write("8.9")
        self.assertEqual(self.upgrader.ensure_compatible(self.project, 21), [])

    def test_java11_maps_to_7_6_4(self):
        self._write("6.8")
        lines = self.upgrader.ensure_compatible(self.project, 11)
        self.assertIn("gradle-7.6.4-bin.zip", self._url())
        self.assertEqual(len(lines), 1)

    def test_no_target_is_noop(self):
        self._write("7.6.1")
        self.assertEqual(self.upgrader.ensure_compatible(self.project, None), [])

    def test_missing_wrapper_is_noop(self):
        # No gradle-wrapper.properties written (e.g. non-wrapper Gradle project).
        self.assertEqual(self.upgrader.ensure_compatible(self.project, 21), [])
