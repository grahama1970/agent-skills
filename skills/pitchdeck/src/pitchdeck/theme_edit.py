"""Theme-only CAS writes. Raw slide/source objects are never reserialized by a model."""
import json
from pathlib import Path
import yaml
from .models import ThemeTokens, DeckManifest
from .document import DeckDocument
from .selected_edit import digest, replace_pair
from .revisions import check_out_of_band, current_revision, _bundle_state, REVISION_FILE, REVISION_STATE_FILE, HISTORY_DIR


def checked(theme):
    if not isinstance(theme, dict) or set(theme) != {'name', 'tokens'}:
        raise ValueError('Theme requires name and tokens only')
    name = theme['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 60:
        raise ValueError('Theme name must have 1–60 characters')
    tokens = ThemeTokens.model_validate(theme['tokens'])
    if tokens.heading_font not in {'Fraunces', 'Arial', 'Calibri', 'Georgia', 'system-ui'} or tokens.body_font not in {'Arial', 'Calibri', 'Georgia', 'system-ui'}:
        raise ValueError('Unsupported font')
    return {'name': name.strip(), 'tokens': tokens.model_dump()}


def run(source: Path, output: Path, request_file: Path, storage: Path):
    request = json.loads(request_file.read_text())
    action = request['action']
    data = output / 'deck.data.json'
    before = [source.read_bytes(), data.read_bytes()]
    raw = yaml.safe_load(before[0])
    payload = json.loads(before[1])
    canonical = raw.get('schema') == 'pitchdeck.deck_document.v1'
    key = digest(str(source.resolve()).encode())
    journal = storage / f'{key}.undo.json'
    catalog = storage / 'saved.json'
    presets = json.loads((Path(__file__).resolve().parents[2] / 'themes/presets.json').read_text())
    saved = json.loads(catalog.read_text()) if catalog.exists() else []
    current = {'name': raw['deck'].get('theme', 'Current appearance'), 'tokens': ThemeTokens.model_validate(raw['deck'].get('theme_tokens', {})).model_dump()}
    hashes = [digest(b) for b in before]
    if action == 'list':
        return {'current': current, 'presets': presets + saved, 'hashes': hashes, 'revision': payload['revision'], 'can_undo': journal.exists() and json.loads(journal.read_text())['hashes'] == hashes}
    if type(request.get('revision')) is not int or request.get('revision') < 0:
        raise ValueError('Revision must be a non-negative integer')
    if request.get('hashes') != hashes or request.get('revision') != payload['revision']:
        raise ValueError('Stale source or revision; reload before changing theme')
    if not canonical:
        check_out_of_band(source.parent)
        if current_revision(source.parent) != payload['revision']:
            raise ValueError('Stale bundle revision')
    if action == 'undo':
        undo = json.loads(journal.read_text())
        if undo['hashes'] != hashes:
            raise ValueError('Undo is stale; later work will not be overwritten')
        theme = undo['theme']
    else:
        theme = checked(request['theme'])
    if action == 'save':
        if theme['name'] in {p['name'] for p in presets}:
            raise ValueError('Choose a new name; built-in presets cannot be overwritten')
        storage.mkdir(parents=True, exist_ok=True)
        saved = [p for p in saved if p['name'] != theme['name']] + [theme]
        temp = catalog.with_suffix('.tmp')
        temp.write_text(json.dumps(saved, indent=1)); temp.replace(catalog)
        return {'status': 'SAVED', 'theme': theme}
    if action not in {'apply', 'undo'}:
        raise ValueError('Unknown theme action')
    previous = {'theme': raw['deck'].get('theme'), 'theme_tokens': raw['deck'].get('theme_tokens')}
    if action == 'undo':
        for k, v in theme.items():
            if v is None: raw['deck'].pop(k, None)
            else: raw['deck'][k] = v
    else:
        raw['deck'].update(theme=theme['name'], theme_tokens=theme['tokens'])
    (DeckDocument if canonical else DeckManifest).model_validate(raw)
    tokens = ThemeTokens.model_validate(raw['deck'].get('theme_tokens', {})).model_dump()
    payload.update(theme=raw['deck'].get('theme', 'Current appearance'), theme_tokens=tokens, revision=payload['revision'] + 1)
    # Only metadata changes; do not rematerialize elements, assets or claim bindings.
    after = [json.dumps(raw, ensure_ascii=False, indent=1).encode() if canonical else yaml.safe_dump(raw, sort_keys=False, allow_unicode=True).encode(), json.dumps(payload, ensure_ascii=False, indent=1).encode()]
    paths = [source, data]
    source_hashes_after = [digest(b) for b in after]
    if not canonical:
        # emit-ui also retains a canonical projection; keep its theme current
        # without rematerializing any slides or reaching unrelated assets.
        projection = output / 'deck.document.json'
        projected_before = projection.read_bytes()
        projected = json.loads(projected_before)
        projected['deck'].update(theme=payload['theme'], theme_tokens=tokens)
        DeckDocument.model_validate(projected)
        projected_after = json.dumps(projected, ensure_ascii=False, indent=1).encode()
        paths.append(projection); before.append(projected_before); after.append(projected_after)
        # Same revision/state/history formats as commit_bundle_write, but one
        # staged write set also includes the external projections and journal.
        state = _bundle_state(source.parent); state[source.name] = digest(after[0])
        archive = source.parent / HISTORY_DIR / str(payload['revision'] - 1) / source.name
        archive.parent.mkdir(parents=True, exist_ok=True)
        for path, value in [(source.parent / REVISION_FILE, str(payload['revision']).encode()),
                            (source.parent / REVISION_STATE_FILE, json.dumps(state, indent=1).encode()),
                            (archive, before[0])]:
            paths.append(path); before.append(path.read_bytes() if path.exists() else None); after.append(value)
    storage.mkdir(parents=True, exist_ok=True)
    paths.append(journal); before.append(journal.read_bytes() if journal.exists() else None)
    after.append(json.dumps({'theme': previous, 'hashes': source_hashes_after}).encode())
    replace_pair(paths, before, after)
    return {'status': 'APPLIED' if action == 'apply' else 'UNDONE', 'revision': payload['revision']}
