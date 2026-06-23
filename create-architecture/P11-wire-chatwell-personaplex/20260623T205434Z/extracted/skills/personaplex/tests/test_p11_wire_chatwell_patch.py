#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'skills/personaplex/scripts/apply_p11_wire_chatwell.py'
CLIENT = ROOT / 'pi-mono/packages/ux-lab/src/components/sparta/explorer/personaplexSpeechFinalClient.ts'


def load_patch_module():
    spec = importlib.util.spec_from_file_location('apply_p11_wire_chatwell', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def fixture_source() -> str:
    return """
import { usePiChat } from '@pi-chat-adapter/hook'
import { PersonaPlexVoiceTracePanel } from './PersonaPlexVoiceTracePanel'

export function ChatTab() {
  const piChat = usePiChat()
  const handleSend = (query: string, type: string) => {
    piChat.send(query, type)
  }
  return (
    <>
      <ChatWell onSend={handleSend} />
      <PersonaPlexVoiceTracePanel className="mt-4" />
    </>
  )
}
""".lstrip()


def test_patch_injects_import_and_ws_send() -> None:
    module = load_patch_module()
    patched = module.patch_source(fixture_source())
    assert "import { sendPersonaPlexSpeechFinalBestEffort } from './personaplexSpeechFinalClient'" in patched
    assert 'piChat.send(query, type)' in patched
    assert 'void sendPersonaPlexSpeechFinalBestEffort(query, {' in patched
    assert "wsUrl: 'ws://127.0.0.1:8788/ws'" in patched
    assert "personaId: 'embry'" in patched
    assert patched.index('piChat.send(query, type)') < patched.index('sendPersonaPlexSpeechFinalBestEffort(query')


def test_patch_is_idempotent() -> None:
    module = load_patch_module()
    once = module.patch_source(fixture_source())
    twice = module.patch_source(once)
    assert once == twice
    assert twice.count('personaplexSpeechFinalClient') == 1
    assert twice.count('sendPersonaPlexSpeechFinalBestEffort(query') == 1


def test_client_contains_required_protocol_contract() -> None:
    text = CLIENT.read_text(encoding='utf-8')
    assert "type: 'speech_final'" in text
    assert "ws://127.0.0.1:8788/ws" in text
    assert "persona_id" in text
    assert "session_id" in text
    assert "turn_id" in text
    assert "embry" in text
    assert "JSON.stringify(payload)" in text


def test_cli_applies_to_repo_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
      repo = Path(tmp)
      chat = repo / 'pi-mono/packages/ux-lab/src/components/sparta/explorer/ChatTab.tsx'
      chat.parent.mkdir(parents=True)
      chat.write_text(fixture_source(), encoding='utf-8')
      result = subprocess.run(
          [sys.executable, str(SCRIPT), '--repo-root', str(repo)],
          text=True,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          check=False,
      )
      assert result.returncode == 0, result.stderr
      patched = chat.read_text(encoding='utf-8')
      assert 'sendPersonaPlexSpeechFinalBestEffort(query' in patched
      result2 = subprocess.run(
          [sys.executable, str(SCRIPT), '--repo-root', str(repo)],
          text=True,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          check=False,
      )
      assert result2.returncode == 0, result2.stderr
      assert chat.read_text(encoding='utf-8') == patched


def main() -> int:
    test_patch_injects_import_and_ws_send()
    test_patch_is_idempotent()
    test_client_contains_required_protocol_contract()
    test_cli_applies_to_repo_fixture()
    print('PASS: P11 ChatWell speech_final patch tests')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
