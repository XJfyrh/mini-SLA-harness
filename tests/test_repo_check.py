"""Mutate real fixture files to prove repository checks reject broken contracts."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.repo_check import check_repository

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "repo_check.py"


class RepositoryCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.root.mkdir()
        self.write("README.md", "[Architecture](docs/architecture.md)\n")
        self.write("AGENTS.md", "[Start](README.md)\n")
        self.write("docs/architecture.md", "[Entry](../src/example/cli.py)\n")
        self.write("src/example/cli.py", "def main() -> int:\n    return 0\n")
        self.write("pyproject.toml", '[project.scripts]\nmini-sla = "example.cli:main"\n')

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def skill(self, name: str, body: str = "# Fixture\n") -> None:
        self.write(
            f".agents/skills/{name}/SKILL.md",
            f'---\nname: {name}\ndescription: "Exercise fixture contracts."\n---\n\n{body}',
        )

    def test_valid_links_include_encoded_paths_and_ignore_code_and_external_urls(self) -> None:
        self.write("docs/space \u4e2d\u6587.md", "# Example\n")
        self.write(
            "docs/architecture.md",
            "[Encoded](space%20%E4%B8%AD%E6%96%87.md#section)\n"
            "[Angle](<space \u4e2d\u6587.md>)\n"
            "[Remote](https://example.invalid/missing)\n"
            "`[example](missing.md)`\n```md\n[example](missing.md)\n```\n",
        )
        self.assertEqual(check_repository(self.root), [])

    def test_broken_nested_link_fails(self) -> None:
        self.write("docs/architecture.md", "[Missing](../missing.py)\n")
        errors = check_repository(self.root)
        self.assertTrue(any("missing link target" in error for error in errors), errors)

    def test_skill_links_resolve_from_the_skill_directory_and_reject_missing_peers(self) -> None:
        self.skill(
            "example",
            "[Guide](../../../docs/architecture.md)\n[Peer](../peer/SKILL.md)\n",
        )
        self.skill("peer")
        self.assertEqual(check_repository(self.root), [])
        (self.root / ".agents/skills/peer/SKILL.md").unlink()
        command = [sys.executable, "-I", str(CHECKER), "--root", str(self.root)]
        failed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertIn(".agents", failed.stderr)
        self.assertIn("missing link target", failed.stderr)
        self.skill("peer")
        passed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_skill_reference_documents_are_checked(self) -> None:
        self.skill("example", "[Reference](references/contract.md)\n")
        self.write(
            ".agents/skills/example/references/contract.md",
            "[Contract](../../../../docs/missing.md)\n",
        )
        errors = check_repository(self.root)
        self.assertTrue(
            any("contract.md:1: missing link target" in error for error in errors), errors
        )
        self.write("docs/missing.md", "# Contract\n")
        self.assertEqual(check_repository(self.root), [])

    def test_unloadable_skill_metadata_is_rejected_and_repair_passes(self) -> None:
        command = [sys.executable, "-I", str(CHECKER), "--root", str(self.root)]
        for header in (
            'name: wrong-folder\ndescription: "Fixture"',
            'name: example\ndescription: "',
            'name: example\ndescription: ""',
            "name: example\ndescription: [one, two]",
            "name: example",
        ):
            with self.subTest(header=header):
                self.write(".agents/skills/example/SKILL.md", f"---\n{header}\n---\n\n# Fixture\n")
                failed = subprocess.run(
                    command, capture_output=True, text=True, timeout=20, check=False
                )
                self.assertEqual(failed.returncode, 1, failed.stderr)
                self.skill("example")
                passed = subprocess.run(
                    command, capture_output=True, text=True, timeout=20, check=False
                )
                self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_skill_requires_an_entry_and_instructions(self) -> None:
        self.skill("example", "")
        self.assertTrue(check_repository(self.root))
        (self.root / ".agents/skills/example/SKILL.md").unlink()
        self.assertTrue(check_repository(self.root))
        self.skill("example")
        self.assertEqual(check_repository(self.root), [])

    def test_existing_file_outside_repository_is_rejected(self) -> None:
        (self.root.parent / "outside.md").write_text("outside", encoding="utf-8")
        self.write("README.md", "[Outside](../outside.md)\n")
        errors = check_repository(self.root)
        self.assertTrue(any("escapes repository" in error for error in errors), errors)

    def test_required_navigation_documents_cannot_be_removed(self) -> None:
        for document in ("README.md", "AGENTS.md"):
            with self.subTest(document=document):
                path = self.root / document
                original = path.read_text(encoding="utf-8")
                path.unlink()
                errors = check_repository(self.root)
                self.assertTrue(any("Missing document" in error for error in errors), errors)
                path.write_text(original, encoding="utf-8")

    def test_missing_console_declaration_fails(self) -> None:
        self.write("pyproject.toml", '[project.scripts]\nother = "example.cli:main"\n')
        self.assertTrue(check_repository(self.root))

    def test_missing_console_module_fails(self) -> None:
        self.write("pyproject.toml", '[project.scripts]\nmini-sla = "example.absent:main"\n')
        errors = check_repository(self.root)
        self.assertTrue(any("entry module is missing" in error for error in errors), errors)

    def test_renaming_actual_function_breaks_console_resolution(self) -> None:
        self.write("src/example/cli.py", "def renamed() -> int:\n    return 0\n")
        errors = check_repository(self.root)
        self.assertTrue(any("entry function is missing" in error for error in errors), errors)

    def test_invalid_toml_and_python_are_rejected(self) -> None:
        self.write("pyproject.toml", "[broken\n")
        self.assertTrue(check_repository(self.root))
        self.write("pyproject.toml", '[project.scripts]\nmini-sla = "example.cli:main"\n')
        self.write("src/example/cli.py", "def main(\n")
        self.assertTrue(check_repository(self.root))

    def test_command_fails_on_broken_link_and_passes_after_repair(self) -> None:
        self.write("README.md", "[Broken](missing.md)\n")
        command = [sys.executable, "-I", str(CHECKER), "--root", str(self.root)]
        failed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.write("missing.md", "# Repaired target\n")
        passed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        self.assertEqual(passed.returncode, 0, passed.stderr)


if __name__ == "__main__":
    unittest.main()
