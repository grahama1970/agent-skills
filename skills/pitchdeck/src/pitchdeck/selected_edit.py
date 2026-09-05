"""Validate, apply and undo one model-proposed element edit (#1599).

The model never chooses paths, IDs, approvals or write commands. Full-byte CAS
protects source and projection; staged writes roll back on ordinary I/O failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .document import DeckDocument, DocElement, DocElementKind
from .document_ui import _element_payload, project_document_to_ui
from .models import ClaimStatus


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def candidate(doc: DeckDocument, slide_id: str, element_id: str, changes: dict) -> tuple[DeckDocument, DocElement, bool]:
    if not isinstance(changes, dict) or set(changes) - {'text', 'style', 'bbox'} or not changes:
        raise ValueError('Proposal may change only text, style or bbox of the selected element')
    updated = doc.model_copy(deep=True)
    slide = next((s for s in updated.slides if s.id == slide_id and not s.hidden), None)
    if slide is None:
        raise ValueError('Selected slide is missing or hidden')
    el = next((e for e in slide.elements if e.id == element_id), None)
    if el is None:
        raise ValueError('Selected element is missing')
    if 'text' in changes and el.kind is not DocElementKind.TEXT:
        raise ValueError('Only text elements support text amendments')
    if 'style' in changes and (not isinstance(changes['style'], dict) or set(changes['style']) - {'size_pt', 'bold', 'align', 'color'}):
        raise ValueError('Unsupported text style field')
    raw = el.model_dump(mode='json')
    for key, value in changes.items():
        raw[key] = {**(raw[key] or {}), **value} if key in {'style', 'bbox'} and isinstance(value, dict) else value
    replacement = DocElement.model_validate(raw)
    text_changed = replacement.text != el.text
    if text_changed:
        if not replacement.text or not replacement.text.strip():
            raise ValueError('Text cannot be emptied by an agent proposal')
        # Keep any qualifier visible in this selected occurrence, regardless
        # of whether the older materializer bound it coarsely or per-element.
        for claim in updated.claims:
            qualifier = claim.required_qualifier
            if qualifier and qualifier in (el.text or '') and qualifier not in replacement.text:
                raise ValueError('Required visible qualifier cannot be removed')
        paths = set(el.binding_paths) | {f'element:{el.id}'}
        affected = {b.claim_id for b in slide.bindings if b.path in paths}
        for claim in updated.claims:
            if claim.id in affected:
                claim.status = ClaimStatus.CANDIDATE
        # Preview approval is not publication approval. Existing emitter gate
        # refuses this document until its renderings are reviewed again.
        updated.provenance['preview_unapproved_renderings'] = 'true'
    slide.elements[slide.elements.index(el)] = replacement
    checked = DeckDocument.model_validate_json(updated.model_dump_json(by_alias=True))
    return checked, replacement, text_changed


def replace_pair(paths: list[Path], before: list[bytes], after: list[bytes]) -> None:
    staged: list[Path] = []
    backups: list[Path] = []
    replaced = 0
    try:
        for path, old, new in zip(paths, before, after):
            for content, collection in [(old, backups), (new, staged)]:
                fd, name = tempfile.mkstemp(prefix='.selected-edit-', dir=path.parent)
                collection.append(Path(name))
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
        if [p.read_bytes() for p in paths] != before:
            raise ValueError('Source changed while staging; proposal refused')
        for src, dst in zip(staged, paths):
            os.replace(src, dst)
            replaced += 1
    except Exception:
        for i in range(replaced):
            os.replace(backups[i], paths[i])
        raise
    finally:
        for path in staged + backups:
            path.unlink(missing_ok=True)


def run(document: Path, output_dir: Path, operation: str, request_file: Path) -> dict:
    request = json.loads(request_file.read_text())
    data_path = output_dir / 'deck.data.json'
    before = [document.read_bytes(), data_path.read_bytes()]
    hashes = [digest(b) for b in before]
    expected = request['expected_hashes']
    if hashes != expected:
        raise ValueError('Stale source or revision; select the element and propose again')
    doc = DeckDocument.model_validate_json(before[0])
    existing = json.loads(before[1])
    journal = request_file.parent / 'undo.json'
    if operation == 'undo':
        saved = json.loads(journal.read_text())
        if saved['after_hashes'] != hashes or saved['document'] != str(document.resolve()):
            raise ValueError('Undo is stale; later work will not be overwritten')
        restored = json.loads(saved['before'][1])
        restored['revision'] = int(existing['revision']) + 1
        after = [saved['before'][0].encode(), json.dumps(restored, ensure_ascii=False, indent=1).encode()]
        DeckDocument.model_validate_json(after[0])
    else:
        updated, element, text_changed = candidate(doc, request['slide_id'], request['element_id'], request['changes'])
        assets = {a.id: a for a in updated.assets}
        preview = _element_payload(element, assets=assets)
        if operation == 'preview':
            return {'status': 'PREVIEW', 'element': preview, 'publication_review_required': text_changed}
        if operation != 'apply':
            raise ValueError('Unknown selected-edit operation')
        # Preserve untouched raw objects: serializing the whole model would
        # inject newer schema defaults (e.g. crop:null) into every element.
        raw_doc = json.loads(before[0])
        raw_slide = next(s for s in raw_doc['slides'] if s['id'] == request['slide_id'])
        i = next(i for i, e in enumerate(raw_slide['elements']) if e['id'] == request['element_id'])
        raw_slide['elements'][i] = element.model_dump(mode='json')
        raw_doc['revision'] = int(existing['revision']) + 1
        if text_changed:
            raw_doc['provenance'] = updated.provenance
            statuses = {c.id: c.status.value for c in updated.claims}
            for claim in raw_doc['claims']:
                claim['status'] = statuses[claim['id']]
        updated = DeckDocument.model_validate(raw_doc)
        payload = project_document_to_ui(updated)
        payload['assets_index'] = existing.get('assets_index', [])
        after = [json.dumps(raw_doc, ensure_ascii=False, indent=1).encode(), json.dumps(payload, ensure_ascii=False, indent=1).encode()]
        journal.write_text(json.dumps({'document': str(document.resolve()), 'before': [b.decode() for b in before], 'after_hashes': [digest(b) for b in after]}, indent=1))
    replace_pair([document, data_path], before, after)
    if [p.read_bytes() for p in [document, data_path]] != after:
        raise ValueError('Write readback mismatch')
    return {'status': 'APPLIED' if operation == 'apply' else 'UNDONE', 'revision': json.loads(after[1])['revision'], 'hashes': [digest(b) for b in after]}
