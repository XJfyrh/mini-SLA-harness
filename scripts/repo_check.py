"""Check local documentation targets and the declared console entry point, offline."""

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r'!?\[[^\]\n]*\]\((<[^>\n]+>|[^)\s]+)(?:\s+"[^"\n]*")?\)')


def local_link_errors(root: Path) -> list[str]:
    errors = []
    documents = [
        root / "README.md",
        root / "AGENTS.md",
        *sorted((root / "docs").rglob("*.md")),
        *sorted((root / ".agents" / "skills").rglob("*.md")),
    ]
    for document in documents:
        if not document.is_file():
            errors.append(f"Missing document: {document.relative_to(root)}")
            continue
        fence: str | None = None
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                marker = stripped[:3]
                if fence is None:
                    fence = marker
                elif fence == marker:
                    fence = None
                continue
            if fence is not None:
                continue
            line = re.sub(r"`+[^`]*`+", "", line)
            for match in LINK.finditer(line):
                target = match.group(1).strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                resolved = (document.parent / unquote(parsed.path)).resolve()
                location = f"{document.relative_to(root)}:{number}"
                if not resolved.is_relative_to(root):
                    errors.append(f"{location}: link escapes repository: {target}")
                elif not resolved.exists():
                    errors.append(f"{location}: missing link target: {target}")
    return errors


def entry_point_errors(root: Path) -> list[str]:
    try:
        with (root / "pyproject.toml").open("rb") as stream:
            configuration = tomllib.load(stream)
        entry: object = configuration.get("project", {}).get("scripts", {}).get("mini-sla")
        if not isinstance(entry, str) or not re.fullmatch(r"\w+(?:\.\w+)*:\w+", entry):
            return ["pyproject.toml: missing or invalid mini-sla console entry"]
        module, function = entry.split(":")
        path = root / "src" / Path(*module.split(".")).with_suffix(".py")
        if not path.is_file():
            return [f"mini-sla entry module is missing: {path.relative_to(root)}"]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if not any(
            isinstance(node, ast.FunctionDef) and node.name == function for node in tree.body
        ):
            return [f"mini-sla entry function is missing: {entry}"]
    except (OSError, ValueError, SyntaxError, AttributeError) as error:
        return [f"Cannot resolve mini-sla entry: {error}"]
    return []


def skill_errors(root: Path) -> list[str]:
    directory = root / ".agents" / "skills"
    errors: list[str] = []
    if not directory.is_dir():
        return errors
    for folder in sorted(path for path in directory.iterdir() if path.is_dir()):
        path = folder / "SKILL.md"
        location = str(path.relative_to(root))
        if not path.is_file():
            errors.append(f"{location}: skill entry is missing")
            continue
        content = path.read_text(encoding="utf-8")
        frontmatter, separator, body = content.removeprefix("---\n").partition("\n---\n")
        if not content.startswith("---\n") or not separator or not body.strip():
            errors.append(f"{location}: expected YAML frontmatter and nonempty instructions")
            continue
        try:
            metadata: object = yaml.safe_load(frontmatter)
        except yaml.YAMLError as error:
            errors.append(f"{location}: invalid skill YAML: {error}")
            continue
        if not isinstance(metadata, dict):
            errors.append(f"{location}: skill metadata must be a mapping")
            continue
        name = metadata.get("name")
        description = metadata.get("description")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
            or len(name) > 64
            or name != folder.name
        ):
            errors.append(f"{location}: name must match its lowercase hyphenated folder name")
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
            errors.append(f"{location}: description must be nonempty text, at most 1024 characters")
    return errors


def check_repository(root: Path) -> list[str]:
    root = root.resolve()
    return local_link_errors(root) + entry_point_errors(root) + skill_errors(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        errors = check_repository(args.root)
    except (OSError, ValueError) as error:
        errors = [str(error)]
    if errors:
        for issue in errors:
            print(f"error: {issue}", file=sys.stderr)
        return 1
    print(
        "Repository checks passed: local documentation targets, mini-sla entry and project skills"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
