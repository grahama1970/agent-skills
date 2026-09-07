#!/usr/bin/env python3
"""Exercise the real intake/emission CLI against an independently produced deck ZIP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import stat
import uuid
import zipfile

SKILL = Path(__file__).resolve().parents[1]
ROOT = Path('/mnt/storage12tb/skills/pitchdeck/outputs/package-intake')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    package = Path(os.environ['PITCHDECK_INTAKE_PACKAGE']).resolve()
    work = ROOT / str(uuid.uuid4())
    work.mkdir(parents=True)
    with zipfile.ZipFile(package) as archive:
        files = {n: archive.read(n) for n in archive.namelist() if not n.endswith('/')}
    canonical = json.loads(files['deck.document.json'])
    calls = []

    def call(*argv):
        result = subprocess.run([str(SKILL / 'run.sh'), *map(str, argv)], cwd=SKILL,
                                capture_output=True, text=True, timeout=120)
        calls.append({'argv': list(map(str, argv)), 'exit_code': result.returncode,
                      'stdout': result.stdout, 'stderr': result.stderr})
        return result

    if not args.negative:
        destination = work / 'imported'
        check = call('ingest-package', '--package', package, '--output-dir', destination)
        assert check.returncode == 0, check.stdout + check.stderr
        assert not destination.exists(), 'Validation-only wrote a destination'
        applied = call('ingest-package', '--package', package, '--output-dir', destination, '--execute')
        assert applied.returncode == 0, applied.stdout + applied.stderr
        for name, content in files.items():
            assert (destination / name).read_bytes() == content, name
        receipt = json.loads((destination / 'intake-receipt.json').read_text())
        assert receipt['applied'] is True and receipt['publication_verified'] is False
        for name, expected in receipt['file_sha256'].items():
            assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected
        emitted = work / 'emitted'
        result = call('emit-document-ui', '--document', destination / 'deck.document.json',
                      '--output-dir', emitted, '--asset-base', destination)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads((emitted / 'deck.data.json').read_text())
        actual = {s['id']: s for s in payload['slides']}
        assert set(actual) == {s['id'] for s in canonical['slides'] if not s.get('hidden')}
        for slide in canonical['slides']:
            if slide.get('hidden'): continue
            assert actual[slide['id']]['notes'] == slide.get('notes', '')
            assert [a['targets'] for a in actual[slide['id']].get('animations', [])] == [a['targets'] for a in slide.get('animations', [])]
        for asset in canonical['assets']:
            if asset.get('local_path'):
                assert (emitted / 'assets' / Path(asset['local_path']).name).read_bytes() == files[asset['local_path']]
        before = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in destination.rglob('*') if p.is_file()}
        refused = call('ingest-package', '--package', package, '--output-dir', destination, '--execute')
        assert refused.returncode == 1 and 'already exists' in refused.stdout
        after = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in destination.rglob('*') if p.is_file()}
        assert before == after
        themed = work / 'with-theme.zip'
        theme_bytes = json.dumps(canonical['deck']['theme_tokens']).encode()
        with zipfile.ZipFile(themed, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                if name != 'theme.json': archive.writestr(name, content)
            archive.writestr('theme.json', theme_bytes)
        themed_destination = work / 'with-theme'
        result = call('ingest-package', '--package', themed, '--output-dir', themed_destination, '--execute')
        assert result.returncode == 0, result.stdout + result.stderr
        assert (themed_destination / 'theme.json').read_bytes() == theme_bytes
        assert (themed_destination / 'deck.document.json').read_bytes() == files['deck.document.json']
    else:
        for case in ['missing-asset', 'traversal', 'theme-drift', 'stale-debugger', 'unknown-animation',
                     'environment-path', 'duplicate-json', 'symlink', 'asset-collision']:
            changed = dict(files)
            changed.pop('deck.authoring.json', None)
            data = json.loads(files['deck.document.json'])
            if case == 'missing-asset':
                del changed[next(a['local_path'] for a in data['assets'] if a.get('local_path'))]
                error = 'Missing package resources'
            elif case == 'traversal':
                changed['../escape'] = b'not allowed'
                error = 'Unsafe package path'
            elif case == 'theme-drift':
                tokens = dict(data['deck']['theme_tokens']); tokens['header'] = '#123456'
                changed['theme.json'] = json.dumps(tokens).encode()
                error = 'theme.json disagrees'
            elif case == 'stale-debugger':
                changed['debugger.json'] = json.dumps({'schema':'pitchdeck.debugger_map.v1',
                    'slides':{'absent-slide':{'file':'not-executed.py','line':1}}}).encode()
                error = 'unknown slide'
            elif case == 'environment-path':
                data['assets'][0]['local_path'] = '${HOME}/outside.png'
                changed['deck.document.json'] = json.dumps(data).encode()
                error = 'Unsafe package path'
            elif case == 'duplicate-json':
                changed['deck.document.json'] = b'{"schema":"duplicate",' + files['deck.document.json'].lstrip()[1:]
                error = 'Duplicate JSON key'
            elif case == 'symlink':
                changed['assets/package-link'] = b'../../outside'
                error = 'Links and special files'
            elif case == 'asset-collision':
                item = dict(next(a for a in data['assets'] if a.get('local_path')))
                original = item['local_path']
                item.update(id='intake-collision', local_path='assets/another/' + Path(original).name)
                data['assets'].append(item)
                changed[item['local_path']] = files[original] + b'\n'
                changed['deck.document.json'] = json.dumps(data).encode()
                error = 'Asset filename collision'
            else:
                slide = next(s for s in data['slides'] if s.get('animations'))
                slide['animations'][0]['targets'] = ['absent-element']
                changed['deck.document.json'] = json.dumps(data).encode()
                error = 'Unknown or static animation target'
            mutated = work / f'{case}.zip'
            with zipfile.ZipFile(mutated, 'w', zipfile.ZIP_DEFLATED) as archive:
                for name, content in changed.items():
                    if case == 'symlink' and name == 'assets/package-link':
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(info, content)
                    else:
                        archive.writestr(name, content)
            destination = work / case
            result = call('ingest-package', '--package', mutated, '--output-dir', destination, '--execute')
            assert result.returncode == 1 and error in result.stdout, result.stdout + result.stderr
            assert not destination.exists() and not (work / 'escape').exists()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'status':'PASS', 'package':str(package),
        'package_sha256':hashlib.sha256(package.read_bytes()).hexdigest(), 'work':str(work),
        'proof_boundary':'Live intake and existing UI emission, file readback; negative cases inject corruptions. No browser or Office playback.',
        'calls':calls}, indent=2) + '\n')


if __name__ == '__main__':
    main()
