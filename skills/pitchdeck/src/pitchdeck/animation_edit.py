"""Animation-only compare-and-swap transaction, using the existing atomic writer."""
import json
from pathlib import Path
import yaml
from .models import AnimationEffect, DeckManifest
from .document import DeckDocument
from .selected_edit import digest, replace_pair
from .revisions import check_out_of_band, current_revision, _bundle_state, REVISION_FILE, REVISION_STATE_FILE, HISTORY_DIR


def validate_sequence(sequence, slide):
    effects = [AnimationEffect.model_validate(a) for a in sequence]
    if len(effects) > 200 or len({a.id for a in effects}) != len(effects):
        raise ValueError('At most 200 uniquely identified effects')
    targets = {}
    dependencies = {}
    def walk(elements):
        for e in elements:
            if e.get('role') in {'title', 'header', 'background', 'footer'}:
                continue
            targets[e['id']] = e
            walk(e.get('children', []))
            for node in e.get('diagram', {}).get('nodes', []):
                targets[f"{e['id']}/node/{node['id']}"] = node
            for edge in e.get('diagram', {}).get('edges', []):
                key = f"{e['id']}/edge/{edge['id']}"
                targets[key] = edge
                dependencies[key] = [f"{e['id']}/node/{edge[n]}" for n in ('source', 'target')]
    if slide['layout'] == 'freeform': walk(slide['elements'])
    else:
        targets.update({f'body:{i}': {'text': text} for i, text in enumerate(slide['body'])})
        targets.update({f'visual:{i}': {'text': text} for i, text in enumerate(slide['visual']['items'])})
        if slide['visual'].get('asset'): targets['visual'] = slide['visual']
    starts = {}; step = 0; start = end = 0
    for a in effects:
        if a.start == 'on-click': step += 1; start = a.delay_ms
        else: start = (end if a.start == 'after-previous' else start) + a.delay_ms
        end = start + a.duration_ms
        for target in a.targets:
            if target not in targets: raise ValueError(f'Unknown or static animation target: {target}')
            t = targets[target]
            if a.effect == 'font-color' and not any(k in t for k in ('text', 'label')): raise ValueError('Font color requires text')
            if a.effect == 'fill-color' and t.get('kind') != 'shape': raise ValueError('Fill color requires a shape')
            if a.effect == 'line-color' and not (t.get('kind') == 'shape' or '/edge/' in target): raise ValueError('Line color requires a shape or connector')
            if a.phase == 'entrance': starts.setdefault(target, (step, start))
    for edge, nodes in dependencies.items():
        if any(starts.get(n, (0, 0)) > starts.get(edge, (0, 0)) for n in nodes):
            raise ValueError('Connector must not precede its nodes; group it with the later node')
    # A separately laid-out required qualifier must appear with its claim.
    for claim in slide.get('claims', []):
        if not isinstance(claim, dict) or not claim.get('required_qualifier'): continue
        related = [key for key, t in targets.items() if any(text and text in str(t.get('text', t.get('label', ''))) for text in [claim.get('text'), claim['required_qualifier']])]
        if len({starts.get(t, (0, 0)) for t in related}) > 1:
            raise ValueError('Claim and required qualifier must share an entrance and delay')
    return [a.model_dump() for a in effects]


def run(source: Path, output: Path, request_file: Path, storage: Path):
    request = json.loads(request_file.read_text()); action = request['action']
    data = output / 'deck.data.json'; paths = [source, data]
    before = [p.read_bytes() for p in paths]
    raw = yaml.safe_load(before[0]); payload = json.loads(before[1])
    canonical = raw.get('schema') == 'pitchdeck.deck_document.v1'
    slide_id = request['slide_id']
    slide = next(s for s in raw['slides'] if s['id'] == slide_id)
    ui_slide = next(s for s in payload['slides'] if s['id'] == slide_id)
    hashes = [digest(b) for b in before]
    journal = storage / (digest((str(source.resolve()) + slide_id).encode()) + '.json')
    undo = json.loads(journal.read_text()) if journal.exists() else None
    if action == 'list': return {'animations': ui_slide.get('animations', []), 'hashes': hashes, 'revision': payload['revision'], 'can_undo': bool(undo and undo['hashes'] == hashes)}
    if type(request.get('revision')) is not int or request['revision'] != payload['revision'] or request.get('hashes') != hashes:
        raise ValueError('Stale source or revision; reload before changing animations')
    if not canonical:
        check_out_of_band(source.parent)
        if current_revision(source.parent) != payload['revision']: raise ValueError('Stale bundle revision')
    previous = {k: slide.get(k) for k in ('animations', 'reveal')}
    if action == 'undo':
        if not undo or undo['hashes'] != hashes: raise ValueError('Undo is stale; later work will not be overwritten')
        for key, value in undo['previous'].items():
            if value is None: slide.pop(key, None)
            else: slide[key] = value
    elif action == 'apply':
        slide['animations'] = validate_sequence(request['animations'], ui_slide)
        slide['reveal'] = 'step' if slide['animations'] else 'none'
    else: raise ValueError('Unknown animation action')
    (DeckDocument if canonical else DeckManifest).model_validate(raw)
    ui_slide.update(animations=slide.get('animations', []), reveal=slide.get('reveal', 'none'))
    payload['revision'] += 1
    after = [json.dumps(raw, ensure_ascii=False, indent=1).encode() if canonical else yaml.safe_dump(raw, sort_keys=False, allow_unicode=True).encode(), json.dumps(payload, ensure_ascii=False, indent=1).encode()]
    new_hashes = [digest(b) for b in after]
    if not canonical:
        projection = output / 'deck.document.json'; projected_before = projection.read_bytes(); projected = json.loads(projected_before)
        projected_slide = next(s for s in projected['slides'] if s['id'] == slide_id)
        projected_slide.update(animations=slide.get('animations', []), reveal=slide.get('reveal', 'none'))
        DeckDocument.model_validate(projected)
        paths.append(projection); before.append(projected_before); after.append(json.dumps(projected, ensure_ascii=False, indent=1).encode())
        state = _bundle_state(source.parent); state[source.name] = digest(after[0])
        archive = source.parent / HISTORY_DIR / str(payload['revision'] - 1) / source.name; archive.parent.mkdir(parents=True, exist_ok=True)
        for path, value in [(source.parent / REVISION_FILE, str(payload['revision']).encode()), (source.parent / REVISION_STATE_FILE, json.dumps(state, indent=1).encode()), (archive, before[0])]:
            paths.append(path); before.append(path.read_bytes() if path.exists() else None); after.append(value)
    storage.mkdir(parents=True, exist_ok=True)
    paths.append(journal); before.append(journal.read_bytes() if journal.exists() else None); after.append(json.dumps({'previous': previous, 'hashes': new_hashes}).encode())
    replace_pair(paths, before, after)
    return {'status': 'APPLIED' if action == 'apply' else 'UNDONE', 'revision': payload['revision']}
