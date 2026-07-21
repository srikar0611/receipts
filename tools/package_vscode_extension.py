#!/usr/bin/env python3
"""Build a minimal, dependency-free VSIX for Receipts for VS Code.

The extension has no runtime npm dependencies, so a standard-library packager
keeps the judge installation path offline and reproducible. The resulting
archive follows the VSIX layout consumed by VS Code:

  [Content_Types].xml
  extension.vsixmanifest
  extension/package.json
  extension/...
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "vscode-receipts"
DIST = ROOT / "dist"
REQUIRED_EXTENSION_FILES = (
    "package.json",
    "extension.js",
    "lib/receipt-model.js",
    "media/receipt.svg",
    "README.md",
)


def load_package() -> dict:
    with (EXTENSION / "package.json").open(encoding="utf-8") as handle:
        package = json.load(handle)
    for key in ("name", "displayName", "description", "version", "publisher"):
        if not isinstance(package.get(key), str) or not package[key].strip():
            raise ValueError(f"vscode-receipts/package.json requires a non-empty {key!r}")
    return package


def vsix_manifest(package: dict) -> str:
    name = escape(package["name"])
    version = escape(package["version"])
    publisher = escape(package["publisher"])
    display_name = escape(package["displayName"])
    description = escape(package["description"])
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Id="{name}" Version="{version}" Language="en-US" Publisher="{publisher}" />
    <DisplayName>{display_name}</DisplayName>
    <Description xml:space="preserve">{description}</Description>
    <Categories>Other,Testing</Categories>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies />
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true" />
    <Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE" Addressable="true" />
  </Assets>
</PackageManifest>
"""


def content_types() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="js" ContentType="application/javascript" />
  <Default Extension="md" ContentType="text/markdown" />
  <Default Extension="svg" ContentType="image/svg+xml" />
  <Default Extension="xml" ContentType="text/xml" />
  <Default Extension="vsixmanifest" ContentType="text/xml" />
</Types>
"""


def extension_files() -> list[Path]:
    files: list[Path] = []
    for required in REQUIRED_EXTENSION_FILES:
        candidate = EXTENSION / required
        if not candidate.is_file():
            raise FileNotFoundError(f"required extension file is missing: {candidate}")
    for candidate in EXTENSION.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(EXTENSION)
        if relative.parts[0] in {"test", "dist", ".vscode"}:
            continue
        if candidate.suffix == ".vsix" or candidate.name in {".gitignore", ".vscodeignore", "CHANGELOG.md"}:
            continue
        files.append(candidate)
    return sorted(files)


def build(output: Path) -> Path:
    package = load_package()
    DIST.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types())
        archive.writestr("extension.vsixmanifest", vsix_manifest(package))
        for source in extension_files():
            archive.write(source, f"extension/{source.relative_to(EXTENSION).as_posix()}")
        archive.write(ROOT / "LICENSE", "extension/LICENSE")
    return output


def verify(package_path: Path) -> None:
    required = {
        "[Content_Types].xml",
        "extension.vsixmanifest",
        "extension/LICENSE",
        *(f"extension/{name}" for name in REQUIRED_EXTENSION_FILES),
    }
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        missing = sorted(required - names)
        if missing:
            raise ValueError(f"VSIX missing required entries: {', '.join(missing)}")
        forbidden = sorted(name for name in names if "/node_modules/" in name or name.startswith("extension/test/"))
        if forbidden:
            raise ValueError(f"VSIX includes excluded files: {', '.join(forbidden)}")
        manifest = json.loads(archive.read("extension/package.json"))
        if manifest.get("name") != "receipts-vscode":
            raise ValueError("VSIX package manifest has an unexpected name")


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the optional Receipts VS Code extension.")
    parser.add_argument("--output", type=Path, help="VSIX output path (defaults to dist/receipts-vscode-<version>.vsix)")
    parser.add_argument("--verify", action="store_true", help="Verify the produced VSIX structure after packaging.")
    args = parser.parse_args()

    package = load_package()
    target = args.output or DIST / f"receipts-vscode-{package['version']}.vsix"
    built = build(target)
    if args.verify:
        verify(built)
    print(f"VSIX written: {built}")
    if args.verify:
        print("VSIX verification: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"VSIX packaging failed: {error}", file=sys.stderr)
        raise SystemExit(1)
