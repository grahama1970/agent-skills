'use client';

import { useState } from 'react';

const AGENT_REPOSITORY_PROMPT = `Inspect https://github.com/grahama1970/agent-skills for work relevant to:

[Describe my question or problem]

Answer from repository evidence, not general assumptions.

Cite the exact file paths and commit you inspected. Separate:

- documented claims;
- executable checks;
- retained run receipts;
- private-runtime dependencies;
- unresolved or untested gaps.

Explain what appears reusable, what would require adaptation, and what
cannot be verified from the public repository.

Do not treat README prose, an agent-generated summary, or your own
interpretation as execution proof.`;

export function CopyAgentPrompt() {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle');

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(AGENT_REPOSITORY_PROMPT);
      setStatus('copied');
    } catch {
      setStatus('failed');
    }
  }

  return (
    <div className="hero-agent-prompt">
      <button
        type="button"
        className="hero-agent-prompt__button"
        onClick={copyPrompt}
        data-qid="hero:action:copy-agent-prompt"
        data-qs-action="HERO_COPY_AGENT_PROMPT"
        title="Copy a source-grounded repository prompt"
      >
        {status === 'copied' ? 'Source prompt copied' : 'Ask your agent about the work'}{' '}
        <span aria-hidden="true">→</span>
      </button>
      <p>Copies a source-grounded prompt. Use it with any repository-capable agent.</p>
      {status === 'failed' ? (
        <p className="hero-agent-prompt__status" role="status">
          Clipboard access was unavailable in this browser.
        </p>
      ) : null}
    </div>
  );
}
