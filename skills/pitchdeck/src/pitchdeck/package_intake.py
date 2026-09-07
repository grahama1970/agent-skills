"""Validate a portable canonical deck ZIP before importing into a new directory.

No rendering, network downloads, code execution, approval changes or overwrites.
The canonical JSON and supplied resources are retained byte-for-byte.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

from .animation_edit import validate_sequence
from .document import DeckDocument, iter_tree
from .document_ui import project_document_to_ui
from .models import ThemeTokens

MAX_FILES = 2048
MAX_TOTAL = 256 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
RECEIPT = 'intake-receipt.json'


def load_json(content: bytes):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=unique_keys)


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name
            or any(c in name for c in ':$%') or name.startswith('~') or any(ord(c) < 32 for c in name)
            or path.as_posix() != name or '.git' in path.parts):
        raise ValueError(f'Unsafe package path: {name!r}')
    return name


def read_package(package: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_TOTAL:
            raise ValueError('Package exceeds 2048 members or 256 MiB expanded size')
        for member in members:
            name = safe_name(member.filename.rstrip('/') if member.is_dir() else member.filename)
            if name.casefold() in seen:
                raise ValueError(f'Duplicate or case-colliding package path: {name}')
            seen.add(name.casefold())
            mode = member.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError(f'Links and special files are not accepted: {name}')
            if member.flag_bits & 1 or member.file_size > MAX_FILE:
                raise ValueError(f'Encrypted or oversized member: {name}')
            if member.is_dir():
                continue
            with archive.open(member) as stream:
                content = stream.read(MAX_FILE + 1)
            if len(content) > MAX_FILE:
                raise ValueError(f'Oversized member: {name}')
            files[name] = content
    for name in files:
        if any(str(parent) in files for parent in PurePosixPath(name).parents):
            raise ValueError(f'File/directory collision: {name}')
    if RECEIPT in files:
        raise ValueError(f'{RECEIPT} is reserved for the intake result')
    return files


def validate_debugger(raw: dict, document: DeckDocument) -> int:
    if not isinstance(raw, dict) or raw.get('schema') != 'pitchdeck.debugger_map.v1' or not isinstance(raw.get('slides'), dict):
        raise ValueError('Invalid debugger.json schema or slides map')
    slides = {s.id: s for s in document.slides}
    def mapping(value: dict) -> None:
        if not isinstance(value, dict) or not isinstance(value.get('file'), str):
            raise ValueError('Debugger mapping needs a relative workspace file')
        safe_name(value['file'])
        line = value.get('line')
        end = value.get('endLine', line)
        if type(line) is not int or type(end) is not int or line < 1 or end < line:
            raise ValueError('Invalid debugger line range')
        if 'endColumn' in value and (type(value['endColumn']) is not int or value['endColumn'] < 1):
            raise ValueError('Invalid debugger endColumn')
        if 'breakLine' in value and (type(value['breakLine']) is not int or not line <= value['breakLine'] <= end):
            raise ValueError('Debugger breakLine is outside its range')
        if 'launch' in value and not isinstance(value['launch'], str):
            raise ValueError('Debugger launch must name an existing workspace launch')
    for slide_id, value in raw['slides'].items():
        if slide_id not in slides:
            raise ValueError(f'Debugger references unknown slide: {slide_id}')
        mapping(value)
        ids = {e.id for e in iter_tree(slides[slide_id].elements)}
        concepts = value.get('concepts', {})
        if not isinstance(concepts, dict):
            raise ValueError('Debugger concepts must be an object keyed by element IDs')
        for element_id, item in concepts.items():
            if element_id not in ids:
                raise ValueError(f'Debugger references unknown concept: {slide_id}/{element_id}')
            mapping(item)
    return len(raw['slides'])


def ingest_package(package: Path, output_dir: Path, *, execute: bool = False) -> dict:
    files = read_package(package)
    if 'deck.document.json' not in files:
        raise ValueError('Root deck.document.json is required; deck.authoring.json is not a direct-ingest format')
    raw = load_json(files['deck.document.json'])
    document = DeckDocument.model_validate(raw)
    for label, records in [('slides', document.slides), ('assets', document.assets),
                           ('sources', document.sources), ('claims', document.claims)]:
        if len({item.id for item in records}) != len(records):
            raise ValueError(f'Duplicate IDs in {label}')
    tokens = raw.get('deck', {}).get('theme_tokens')
    if not isinstance(tokens, dict) or not set(ThemeTokens.model_fields).issubset(tokens):
        raise ValueError('Include the complete resolved deck.theme_tokens snapshot, not only a preset name')
    if 'theme.json' in files:
        if ThemeTokens.model_validate(load_json(files['theme.json'])) != document.deck.theme_tokens:
            raise ValueError('theme.json disagrees with deck.theme_tokens')
    warnings = []
    if 'deck.authoring.json' in files:
        review = load_json(files['deck.authoring.json'])
        if not isinstance(review, dict) or review.get('canonical_source_sha256') != hashlib.sha256(files['deck.document.json']).hexdigest():
            raise ValueError('Authoring review copy references a different canonical document')
        warnings.append('deck.authoring.json is retained as review material only; its edits are not imported or merged')
    missing = []
    used_assets = {e.asset_id for s in document.slides for e in iter_tree(s.elements) if e.asset_id}
    for asset in document.assets:
        if asset.local_path:
            path = safe_name(asset.local_path)
            if path not in files: missing.append(path)
        elif asset.required or asset.id in used_assets:
            missing.append(f'asset:{asset.id} (no local_path)')
    for source in document.sources:
        path = safe_name(source.path)
        if path not in files:
            if source.required: missing.append(path)
            else: warnings.append(f'Optional source not bundled: {path}')
        elif source.content_sha:
            expected = source.content_sha.removeprefix('sha256:')
            if len(expected) == 64 and hashlib.sha256(files[path]).hexdigest() != expected:
                raise ValueError(f'Source content hash mismatch: {source.id}')
    if missing:
        raise ValueError('Missing package resources: ' + ', '.join(sorted(set(missing))))
    emitted_names = {}
    for asset in document.assets:
        if asset.local_path:
            name = PurePosixPath(asset.local_path).name
            digest = hashlib.sha256(files[asset.local_path]).hexdigest()
            if name in emitted_names and emitted_names[name] != digest:
                raise ValueError(f'Asset filename collision in browser export: {name}')
            emitted_names[name] = digest
    projected = project_document_to_ui(document)
    for slide in projected['slides']:
        validate_sequence(slide.get('animations', []), slide)
    mapped = validate_debugger(load_json(files['debugger.json']), document) if 'debugger.json' in files else 0
    if 'slide-map.json' in files:
        load_json(files['slide-map.json'])
    if not mapped:
        warnings.append('No debugger mappings supplied; code navigation is not established')
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    receipt = {'schema': 'pitchdeck.package_intake.v1', 'status': 'PASS', 'applied': execute,
               'deck_id': document.deck.id, 'slides': len(document.slides), 'assets': len(document.assets),
               'mapped_slides': mapped, 'file_sha256': hashes, 'warnings': warnings,
               'publication_verified': False, 'code_executed': False,
               'workspace_binding_required': bool(mapped),
               'document_path': str(output_dir.resolve() / 'deck.document.json')}
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError('Destination already exists; intake never overwrites a working deck')
    if not execute:
        return receipt
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir()  # Exclusive creation; the importer owns only this new directory.
    try:
        for name, data in files.items():
            target = output_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name, digest in hashes.items():
            if hashlib.sha256((output_dir / name).read_bytes()).hexdigest() != digest:
                raise OSError(f'Imported bytes differ: {name}')
        (output_dir / RECEIPT).write_text(json.dumps(receipt, indent=2) + '\n')
    except BaseException:
        shutil.rmtree(output_dir)
        raise
    return receipt
