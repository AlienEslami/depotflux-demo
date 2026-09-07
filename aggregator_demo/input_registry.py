from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from .contracts import DemoInputResponse


class DemoInputError(RuntimeError):
    code = "demo_input_error"


class DemoInputNotFoundError(DemoInputError):
    code = "input_reference_unknown"


class DemoInputIntegrityError(DemoInputError):
    code = "input_integrity_error"


class DemoInputRegistry:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parent / "demo_data"
        manifest_path = self.root / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DemoInputIntegrityError(
                f"demo input manifest could not be loaded: {manifest_path}"
            ) from exc
        if manifest.get("manifest_version") != "v1":
            raise DemoInputIntegrityError("unsupported demo input manifest version")
        entries = manifest.get("inputs")
        if not isinstance(entries, list):
            raise DemoInputIntegrityError("demo input manifest has no inputs list")
        try:
            descriptors = [DemoInputResponse.model_validate(item) for item in entries]
        except ValidationError as exc:
            raise DemoInputIntegrityError("demo input manifest is invalid") from exc
        if len({descriptor.reference for descriptor in descriptors}) != len(descriptors):
            raise DemoInputIntegrityError("demo input references must be unique")
        self._entries = {descriptor.reference: descriptor for descriptor in descriptors}

    def list(self) -> list[DemoInputResponse]:
        return sorted(self._entries.values(), key=lambda item: item.fleet_size)

    def descriptor(self, reference: str) -> DemoInputResponse:
        descriptor = self._entries.get(reference)
        if descriptor is None:
            raise DemoInputNotFoundError(f"unknown demo input reference: {reference}")
        return descriptor

    def verify(self, reference: str, expected_sha256: str) -> DemoInputResponse:
        descriptor = self.descriptor(reference)
        if descriptor.sha256 != expected_sha256:
            raise DemoInputIntegrityError(
                "submitted input hash does not match the registered demo input"
            )
        path = self._path_for(descriptor)
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha256 != descriptor.sha256:
            raise DemoInputIntegrityError(
                f"demo input bytes do not match the manifest: {descriptor.filename}"
            )
        return descriptor

    def load(self, reference: str, expected_sha256: str) -> dict:
        descriptor = self.verify(reference, expected_sha256)
        path = self._path_for(descriptor)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DemoInputIntegrityError(
                f"demo input could not be parsed: {descriptor.filename}"
            ) from exc
        if not isinstance(payload, dict):
            raise DemoInputIntegrityError("demo input payload must be a JSON object")
        return payload

    def _path_for(self, descriptor: DemoInputResponse) -> Path:
        path = (self.root / descriptor.filename).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise DemoInputIntegrityError("demo input path escapes the registry root")
        if not path.is_file():
            raise DemoInputIntegrityError(
                f"registered demo input file is missing: {descriptor.filename}"
            )
        return path
