#!/usr/bin/env python3
"""Live two-page teleprompter checks on an existing source tab; no test windows.

The single named companion is the user-requested reader and is retained on success.
Only companions created by a failed check are closed. Source navigation is restored.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[3]
SURF = ROOT / 'skills/surf/run.sh'


def call(*args):
    return subprocess.check_output([str(SURF), *map(str, args)], text=True, timeout=60)


def js(tab, code):
    return json.loads(call('js', 'return (async()=>{' + code + '})()', '--tab-id', tab, '--no-activate', '--no-screenshot'))


def wait(tab, code):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            value = js(tab, code)
            if value:
                return value
        except subprocess.CalledProcessError as error:
            if 'context' not in str(error.output).lower():
                raise
        time.sleep(.15)
    raise RuntimeError('UI did not settle: ' + code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-tab', default=os.environ.get('PITCHDECK_SOURCE_TAB'))
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not args.source_tab:
        parser.error('Set PITCHDECK_SOURCE_TAB to the existing pitchdeck tab; this check never creates a source window.')
    source = int(args.source_tab)
    tabs_before = json.loads(call('tab.list', '--json'))
    original = next(t for t in tabs_before if t['id'] == source)
    assert urlsplit(original['url']).path == '/', 'source tab is not the pitchdeck interface'
    original_hash = js(source, 'return location.hash')
    last_source_hash = original_hash
    companion = None
    presenter_opened = False
    restore_rehearsal = False
    result = {'live': True, 'source_tab': source, 'checks': []}
    try:
        wait(source, 'return !!document.querySelector(`[data-qid="deck:teleprompter:open"]`)')
        snapshot = js(source, 'const d=await fetch(new URL(new URLSearchParams(location.search).get("deck")||"./deck.data.json",location.href)).then(r=>r.json());return {deck:{slides:d.slides.filter(s=>!s.hidden).slice(0,2).map(s=>({id:s.id,notes:s.notes}))},source:sessionStorage.getItem("pitchdeck:teleprompter-source"),slide:document.querySelector(".slide-viewport").dataset.slideId}')
        connection = snapshot['source']
        assert connection
        for _ in range(2):
            call('click', '[data-qid="deck:teleprompter:open"]', '--tab-id', source, '--no-activate', '--no-screenshot')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            matches = [t for t in json.loads(call('tab.list', '--json')) if urlsplit(t.get('url', '')).path == '/teleprompter' and parse_qs(urlsplit(t['url']).query).get('source') == [connection]]
            if matches:
                break
            time.sleep(.15)
        assert len(matches) == 1, matches
        companion = matches[0]
        assert companion['windowId'] != original['windowId'], 'reader is not a separate window'
        reader = companion['id']
        wait(reader, 'return document.querySelector(`[data-qid="teleprompter:page"]`)?.dataset.connected==="true"')
        assert js(source, 'return !!document.querySelector(".slide-viewport") && !document.querySelector(`[data-qid="teleprompter:page"]`)')
        result['checks'].append('separate route/window; repeated Open reused one companion; audience view retained')
        if args.negative:
            js(reader, 'window.__poisonSeen=false;window.__probeReceived=0;window.__probeBus=new BroadcastChannel("pitchdeck:teleprompter:"+' + json.dumps(connection) + ');window.__probeBus.onmessage=e=>{if(e.data?.title==="TELEPROMPTER_POISON")window.__probeReceived++};new MutationObserver(()=>{if(document.body.textContent.includes("TELEPROMPTER_POISON"))window.__poisonSeen=true}).observe(document.body,{subtree:true,childList:true,characterData:true});return true')
            js(source, 'const source=' + json.dumps(connection) + ';const c=new BroadcastChannel(`pitchdeck:teleprompter:${source}`);const base={type:"slide",source,deckTitle:"test",slideId:"bad",title:"TELEPROMPTER_POISON",notes:"TELEPROMPTER_POISON",position:1,total:1};c.postMessage({...base,notes:{invalid:true}});c.postMessage({...base,source:source+"-other"});c.close();return true')
            wait(reader, 'return window.__probeReceived===2')
            assert not js(reader, 'return window.__poisonSeen')
            js(reader, 'window.__probeBus.close();return true')
            result['checks'].append('malformed and cross-source snapshots did not enter the rendered page')
            wrong = companion['url'].split('?')[0] + '?source=unbound-test'
            call('go', wrong, '--tab-id', reader, '--no-activate', '--no-screenshot')
            wait(reader, 'return document.querySelector(`[data-qid="teleprompter:page"]`)?.dataset.slideId===""')
            assert js(reader, 'return document.querySelector(`[data-qid="teleprompter:page"]`).dataset.connected') == 'false'
            result['checks'].append('an unbound source shows waiting, not stale notes')
        else:
            slides = [s for s in snapshot['deck']['slides'] if not s.get('hidden')]
            assert len(slides) >= 2
            for slide in slides[:2]:
                last_source_hash = '#/slide/' + slide['id']
                js(source, 'location.hash=' + json.dumps(last_source_hash) + ';return true')
                wait(reader, 'return document.querySelector(`[data-qid="teleprompter:page"]`)?.dataset.slideId===' + json.dumps(slide['id']))
                points = js(reader, 'return [...document.querySelectorAll(`[data-qid="teleprompter:bullets"] li`)].map(e=>e.textContent)')
                assert points and len(points) == len([line for line in slide['notes'].splitlines() if line.strip()]) and all(point in slide['notes'] for point in points), (slide['id'], points)
                result['checks'].append({'slide': slide['id'], 'rendered_points': points})
            call('tab.reload', '--tab-id', reader)
            wait(reader, 'return document.querySelector(`[data-qid="teleprompter:page"]`)?.dataset.slideId===' + json.dumps(slides[1]['id']))
            before_size = js(reader, 'return parseFloat(getComputedStyle(document.querySelector(".teleprompter-text")).fontSize)')
            assert before_size >= 48
            call('click', '[data-qid="teleprompter:larger"]', '--tab-id', reader, '--no-activate', '--no-screenshot')
            wait(reader, 'return parseFloat(getComputedStyle(document.querySelector(".teleprompter-text")).fontSize)>' + str(before_size))
            call('click', '[data-qid="teleprompter:smaller"]', '--tab-id', reader, '--no-activate', '--no-screenshot')
            wait(reader, 'return parseFloat(getComputedStyle(document.querySelector(".teleprompter-text")).fontSize)===' + str(before_size))
            result['checks'].append('oversized type, font adjustment and reload reconnection verified')
            assert not js(source, 'return !!document.querySelector(`[data-qid="deck:record:stop"]`)'), 'do not disturb a recording'
            restore_rehearsal = js(source, 'return new URLSearchParams(location.search).get("rehearse")==="1"')
            if restore_rehearsal:
                call('click', '[data-qid="deck:rehearse"]', '--tab-id', source, '--no-activate', '--no-screenshot')
            js(source, 'document.activeElement?.blur();document.body.tabIndex=-1;document.body.focus();return true')
            call('key', 'Ctrl+Enter', '--tab-id', source, '--no-activate', '--no-screenshot')
            wait(source, 'return !!document.querySelector(".presenter-shell")')
            presenter_opened = True
            current = js(source, 'return document.querySelector(".presenter-shell .slide-viewport").dataset.slideId')
            for _ in range(20):
                call('click', '[data-qid="deck:presenter:next"]', '--tab-id', source, '--no-activate', '--no-screenshot')
                time.sleep(.2)
                selected = js(source, 'return document.querySelector(".presenter-shell .slide-viewport").dataset.slideId')
                if selected != current:
                    break
            assert selected != current, 'presenter did not advance to another slide'
            wait(reader, 'return document.querySelector(`[data-qid="teleprompter:page"]`)?.dataset.slideId===' + json.dumps(selected))
            last_source_hash = '#/slide/' + selected
            result['checks'].append({'presenter_selection_synced': selected})
            call('click', '[data-qid="deck:presenter:exit"]', '--tab-id', source, '--no-activate', '--no-screenshot')
            presenter_opened = False
            image = args.out.with_suffix('.png')
            call('snap', '--tab-id', reader, '--no-activate', '--output', image)
            result['screenshot'] = str(image)
        result['status'] = 'PASS'
    except Exception as error:
        result.update(status='FAIL', error=str(error))
        raise
    finally:
        active_error = sys.exc_info()[0] is not None
        cleanup_error = None
        try:
            if presenter_opened:
                call('click', '[data-qid="deck:presenter:exit"]', '--tab-id', source, '--no-activate', '--no-screenshot')
            if restore_rehearsal and not js(source, 'return new URLSearchParams(location.search).get("rehearse")==="1"'):
                call('click', '[data-qid="deck:rehearse"]', '--tab-id', source, '--no-activate', '--no-screenshot')
            if js(source, 'return location.hash') == last_source_hash:
                js(source, 'location.hash=' + json.dumps(original_hash) + ';return true')
            else:
                result['external_source_navigation_preserved'] = True
        except Exception as error:
            cleanup_error = error
            result['source_restore_error'] = str(error)
        try:
            if companion:
                if args.negative:
                    call('go', companion['url'], '--tab-id', companion['id'], '--no-activate', '--no-screenshot')
                if result.get('status') != 'PASS' and companion['id'] not in {t['id'] for t in tabs_before}:
                    call('tab.close', '--tab-id', companion['id'])
                else:
                    result['companion_retained_for_user'] = companion
        except Exception as error:
            cleanup_error = error
            result['companion_restore_error'] = str(error)
        finally:
            if cleanup_error: result['status'] = 'FAIL'
            args.out.write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
        if cleanup_error and not active_error:
            raise cleanup_error


if __name__ == '__main__':
    main()
