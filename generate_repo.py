#!/usr/bin/env python3
"""
Generate Kodi repository metadata:
- One <addon> entry per add-on id (latest version only)
- addons.xml at repo root
- addons.xml.md5 as MD5 of the file contents
Usage:
  python3 generate_repo.py            # run from repo root
Optional:
  python3 generate_repo.py --zips zips --out .
"""
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import hashlib
import argparse
import re
import sys

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zips", default="zips", help="Path to zips folder")
    ap.add_argument("--out", default=".", help="Output directory for addons.xml and addons.xml.md5")
    return ap.parse_args()

def normalize_version(v: str):
    """
    Convert a version string like '0.15.3', '1.0.0~alpha', '1.0.0+meta' into a tuple for comparison.
    Simple and robust for typical Kodi add-on versions.
    """
    # Keep only digits and dots for primary compare; fallback to secondary text
    primary = re.findall(r"\d+|[A-Za-z]+", v)
    parts = []
    for token in primary:
        if token.isdigit():
            parts.append((0, int(token)))  # numeric sorts before alpha
        else:
            parts.append((1, token.lower()))
    return tuple(parts)

def find_addons(zips_dir: Path):
    """
    Walk zips/ to find <addon.xml> inside each zip and yield (id, version, xml_element, zip_path)
    """
    for zip_path in zips_dir.rglob("*.zip"):
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                # look for */addon.xml inside zip
                addon_xml_name = None
                for n in z.namelist():
                    if n.lower().endswith("/addon.xml"):
                        addon_xml_name = n
                        break
                if not addon_xml_name:
                    print(f"[WARN] No addon.xml found in {zip_path}", file=sys.stderr)
                    continue
                with z.open(addon_xml_name) as f:
                    data = f.read()
                elem = ET.fromstring(data)
                addon_id = elem.attrib.get("id")
                addon_ver = elem.attrib.get("version")
                if not addon_id or not addon_ver:
                    print(f"[WARN] Missing id/version in {zip_path}", file=sys.stderr)
                    continue
                yield addon_id, addon_ver, elem, zip_path
        except zipfile.BadZipFile:
            print(f"[WARN] Bad zip file: {zip_path}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] {zip_path}: {e}", file=sys.stderr)

def build_addons_xml(entries, out_dir: Path):
    """
    Write addons.xml and addons.xml.md5
    """
    addons_root = ET.Element("addons")
    for _, _, elem, _ in entries:
        addons_root.append(elem)

    # Serialize
    xml_bytes = ET.tostring(addons_root, encoding="utf-8")
    addons_xml_path = out_dir / "addons.xml"
    with open(addons_xml_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
        f.write(xml_bytes)

    # MD5 of exact file contents
    with open(addons_xml_path, "rb") as f:
        content = f.read()
    md5 = hashlib.md5(content).hexdigest()
    (out_dir / "addons.xml.md5").write_text(md5, encoding="utf-8")
    return addons_xml_path, out_dir / "addons.xml.md5"

def main():
    args = parse_args()
    zips_dir = Path(args.zips).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Gather latest version per addon id
    latest = {}
    for addon_id, addon_ver, elem, zpath in find_addons(zips_dir):
        key = addon_id
        best = latest.get(key)
        if best is None or normalize_version(addon_ver) > normalize_version(best[1]):
            latest[key] = (addon_id, addon_ver, elem, zpath)

    if not latest:
        print(f"No add-ons found under {zips_dir}", file=sys.stderr)
        sys.exit(1)

    # Sort entries by addon id for a stable output
    selected = [latest[k] for k in sorted(latest.keys())]
    addons_xml, md5_path = build_addons_xml(selected, out_dir)

    # Log summary
    print("Generated:")
    print(" -", addons_xml)
    print(" -", md5_path)
    print("\nIncluded add-ons (latest only):")
    for addon_id, addon_ver, _, zpath in selected:
        print(f" - {addon_id} @ {addon_ver}  ({zpath.name})")

if __name__ == "__main__":
    main()
