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
    parser.add_argument('--end-line', type=int)
    parser.add_argument('--end-column', type=int)
    parser.add_argument('--break-line', type=int)
    parser.add_argument('--concept-id', help='Existing slide element ID')
    parser.add_argument('--reveal-only', action='store_true')
    parser.add_argument('--local', action='append', default=[])
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--launch-name', default='Pitchdeck: canonical export')
    parser.add_argument('--create-export-launch', action='store_true')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    source = (workspace / args.file).resolve()
    if Path(args.file).is_absolute() or not source.is_relative_to(workspace):
        parser.error('source must be workspace-relative and contained')
    lines = source.read_text().splitlines()
    end_line = args.end_line if args.end_line is not None else args.line
    if not 1 <= args.line <= end_line <= len(lines):
        parser.error('range is outside source file')
    end_column = args.end_column if args.end_column is not None else len(lines[end_line - 1]) + 1
    if not 1 <= end_column <= len(lines[end_line - 1]) + 1 or (end_line == args.line and end_column == 1):
        parser.error('selection must be nonempty and contained')
    if args.break_line is not None and not args.line <= args.break_line <= end_line:
        parser.error('breakpoint must be inside source range')
    if args.reveal_only and args.create_export_launch:
        parser.error('reveal-only cannot create a launch')
    deck = json.loads(args.deck_data.read_text())
    slide = next((s for s in deck['slides'] if s['id'] == args.slide_id and not s.get('hidden')), None)
    if slide is None:
        parser.error('slide not found or hidden')
    if args.concept_id and not any(e['id'] == args.concept_id for e in slide.get('elements', [])):
        parser.error('concept ID must identify an existing slide element')
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
    if not args.reveal_only:
        launch = json.loads((workspace / '.vscode/launch.json').read_text())
        if not any(c['name'] == args.launch_name for c in launch['configurations']):
            parser.error('named launch configuration does not exist')
    path = args.deck_data.with_name('debugger.json')
    config = json.loads(path.read_text()) if path.exists() else {'schema': 'pitchdeck.debugger_map.v1', 'slides': {}}
    target = {'file': args.file, 'line': args.line, 'endLine': end_line, 'endColumn': end_column}
    if not args.reveal_only:
        target.update(launch=args.launch_name, locals=args.local)
        if args.break_line is not None:
            target['breakLine'] = args.break_line
    previous = config['slides'].get(args.slide_id, {})
    if args.concept_id:
        if not previous:
            parser.error('configure the slide overview before its concepts')
        previous.setdefault('concepts', {})[args.concept_id] = target
    else:
        if 'concepts' in previous:
            target['concepts'] = previous['concepts']
        config['slides'][args.slide_id] = target
    path.write_text(json.dumps(config, indent=2) + '\n')
    print(json.dumps({'mapping': str(path), 'slide_id': args.slide_id, 'launch': args.launch_name, 'executed_debuggee': False}))


if __name__ == '__main__':
    main()
