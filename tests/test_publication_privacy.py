import importlib.util
import pathlib
import unittest

source = pathlib.Path(__file__).resolve().parents[1] / "scripts/check_publication_privacy.py"
spec = importlib.util.spec_from_file_location("publication_privacy", source)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PublicationPrivacyTests(unittest.TestCase):
    def test_documentation_placeholders_are_allowed(self):
        data = b"/Users/<user>/project 192.0.2.76 198.51.100.106 SHA256:<your-private-fingerprint>"
        self.assertEqual(checker.violations("README.md", data), [])
        self.assertEqual(checker.violations("backend/.env.example", b"EDGE_API_TOKEN="), [])

    def test_unrecognised_personal_paths_are_rejected(self):
        self.assertIn("personal home path", checker.violations("README.md", b"/Users/" + b"private-person/project"))
        self.assertIn("personal home path", checker.violations("README.md", b"C:" + b"\\Users\\" + b"private-person\\project"))

    def test_credentials_are_rejected_without_echoing_them(self):
        token = b"ghp_" + b"a" * 36
        findings = checker.violations("config.txt", token)
        self.assertEqual(findings, ["GitHub token"])
        self.assertNotIn(token.decode(), " ".join(findings))

    def test_local_files_are_rejected(self):
        for path in ["backend/.env", "backend/.env.production", "config/pi.local.yaml", "capture.wav", "users.sqlite"]:
            self.assertTrue(checker.violations(path, b""), path)


if __name__ == "__main__":
    unittest.main()
