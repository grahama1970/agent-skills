#!/usr/bin/env python3
"""Bind one slide to approved workspace code; optionally install an export launch.

This writes configuration only. Starting/continuing a debuggee is a separate UI action.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deck-data', type=Path, required=True)
    parser.add_argument('--slide-id', required=True)
    parser.add_argument('--file', required=True, help='Workspace-relative source file')
    parser.add_argument('--line', type=int, required=True)
    parser.add_argument('--local', action='append', default=[])
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--launch-name', default='Pitchdeck: canonical export')
    parser.add_argument('--create-export-launch', action='store_true')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    source = (workspace / args.file).resolve()
    if Path(args.file).is_absolute() or not source.is_relative_to(workspace):
        parser.error('source must be workspace-relative and contained')
    if not 1 <= args.line <= len(source.read_text().splitlines()):
        parser.error('line is outside source file')
    deck = json.loads(args.deck_data.read_text())
    if not any(s['id'] == args.slide_id and not s.get('hidden') for s in deck['slides']):
        parser.error('slide not found or hidden')
    root = Path(__file__).resolve().parents[3]
    if args.create_export_launch:
        receipt = json.loads(args.deck_data.with_name('emit_ui_receipt.json').read_text())
        if receipt['operation'] != 'emit-document-ui':
            parser.error('export walkthrough requires a canonical document')
        output = Path('/mnt/storage12tb/skills/pitchdeck/outputs/debugger')
        output.mkdir(parents=True, exist_ok=True)
        cmd = ['uv', 'run', '--project', str(root / 'skills/debugger'), 'python', str(root / 'skills/debugger/scripts/write_vscode_launch.py'), '--workspace', str(workspace), '--name', args.launch_name, '--python', '/mnt/storage12tb/skills/pitchdeck/.venv/bin/python', '--module', 'pitchdeck.cli', '--env', f'PYTHONPATH={root / "skills/pitchdeck/src"}']
        for key in ['SPARTA_PUBLIC_ROOT', 'SPARTA_CANONICAL_ROOT', 'SPARTA_ROOT']:
            if os.environ.get(key):
                cmd += ['--env', f'{key}={os.environ[key]}']
        for value in ['emit-document-pptx', '--document', receipt['outputs']['document_path'], '--asset-base', receipt['outputs']['asset_base'], '--output', str(output / 'walkthrough.pptx')]:
            cmd.append('--arg=' + value)
        subprocess.run(cmd, check=True, env={**os.environ, 'UV_PROJECT_ENVIRONMENT': '/mnt/storage12tb/skills/debugger/.venv'})
    launch = json.loads((workspace / '.vscode/launch.json').read_text())
    if not any(c['name'] == args.launch_name for c in launch['configurations']):
        parser.error('named launch configuration does not exist')
    path = args.deck_data.with_name('debugger.json')
    config = json.loads(path.read_text()) if path.exists() else {'schema': 'pitchdeck.debugger_map.v1', 'slides': {}}
    config['slides'][args.slide_id] = {'file': args.file, 'line': args.line, 'launch': args.launch_name, 'locals': args.local}
    path.write_text(json.dumps(config, indent=2) + '\n')
    print(json.dumps({'mapping': str(path), 'slide_id': args.slide_id, 'launch': args.launch_name, 'executed_debuggee': False}))


if __name__ == '__main__':
    main()
