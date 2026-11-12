"""Shared specification source; relative overrides are Backend-root relative."""
import json
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent

class SpecDataError(ValueError):
    """The configured specification source cannot be used."""

def specs_path():
    value = os.environ.get("SFI_SPECS_PATH", "").strip()
    if value:
        # An explicit override is authoritative, including a missing/invalid file.
        path = Path(value).expanduser()
        return (BACKEND_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    candidates = [BACKEND_ROOT.parent / name / "_data/sfi_specs.json"
                  for name in ("Frontend", "SFI-Frontend")]
    return next((path for path in candidates if path.is_file()), candidates[0]).resolve()

def load_specs():
    path = specs_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SpecDataError(f"SFI spec data at {path}: {exc}. Set SFI_SPECS_PATH to an absolute file or clone sibling Frontend (also supports SFI-Frontend).") from exc
    def invalid(message):
        raise SpecDataError(f"Invalid SFI spec data at {path}: {message}")
    if not isinstance(data, list) or not data:
        invalid("expected a nonempty list of specification objects")
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            invalid(f"entry {i} must be an object")
        for key in ("product_name", "category"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                invalid(f"entry {i}: {key} must be a nonempty string")
        numbers = entry.get("spec_numbers")
        if not isinstance(numbers, list) or not numbers or any(not isinstance(n, str) or not n.strip() for n in numbers):
            invalid(f"entry {i}: spec_numbers must be a nonempty list of strings")
        for key in ("spec_pdfs", "manufacturer_pdfs", "products_pdfs"):
            if key in entry and (not isinstance(entry[key], list) or any(not isinstance(v, str) for v in entry[key])):
                invalid(f"entry {i}: {key} must be a list of strings")
        for key in ("subcategory", "effective_date"):
            if key in entry and not isinstance(entry[key], str):
                invalid(f"entry {i}: {key} must be a string")
    return data
