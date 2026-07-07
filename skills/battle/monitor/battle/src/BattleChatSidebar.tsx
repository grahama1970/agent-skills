import { useState } from "react";

import { SharedChatShell, type ChatMessage } from "../../../../ux-lab/ui";

import type { LoadedBattleArtifacts } from "./types";

function makeMessageId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function BattleChatSidebar({ data }: { data: LoadedBattleArtifacts }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "assistant-initial",
      role: "assistant",
      title: "Battle Agent",
      content:
        "Human interjections are captured here as local Battle handoff previews. They do not mutate Tau or the orchestrator until a schema-valid backend exists.",
      createdAt: new Date().toISOString(),
      footer: data.run.battle_id,
      metadata: {
        surface: "battle-monitor",
        branch: "compliance"
      }
    }
  ]);

  async function handleSend(text: string): Promise<void> {
    const now = new Date().toISOString();
    const receipt = {
      schema: "battle.human_interjection.v1",
      battle_id: data.run.battle_id,
      action: text.toLowerCase().includes("pause") ? "pause" : "annotate",
      message: text,
      target: data.run.artifacts.scoreboard,
      created_at: now,
      status: "LOCAL_PREVIEW"
    };

    setMessages((current) => [
      ...current,
      {
        id: makeMessageId("human"),
        role: "user",
        content: text,
        createdAt: now,
        metadata: { receipt }
      },
      {
        id: makeMessageId("assistant"),
        role: "assistant",
        title: "Battle Agent",
        content: `Captured a local ${receipt.action} preview for ${data.run.battle_id}.\n\n${JSON.stringify(receipt, null, 2)}`,
        createdAt: new Date().toISOString(),
        footer: "LOCAL_PREVIEW",
        metadata: {
          branch: "compliance",
          receipt
        }
      }
    ]);
  }

  return (
    <aside className="chatSidebar" data-qid="battle:chat:shell">
      <SharedChatShell
        projectLabel="Battle Chat"
        surface="shared-chat"
        shellQid="battle:shared-chat:shell"
        qid="battle:shared-chat:well"
        showModeToggle={false}
        messages={messages}
        onMessagesChange={setMessages}
        onSend={handleSend}
        placeholder="Interject, pause, redirect personas, or ask about evidence..."
        emptyTitle="Battle Chat"
        emptyDescription="Ask about the Arena challenge, Judge replay, or scoreboard evidence."
        starterChips={[
          {
            label: "Pause battle",
            prompt: "Pause after this round and wait for human review.",
            dataQid: "battle:chat:chip:pause"
          },
          {
            label: "Redirect Red",
            prompt: "Redirect Red toward high/low-level exploit combinations against the current target.",
            dataQid: "battle:chat:chip:red"
          },
          {
            label: "Ask Scorekeeper",
            prompt: "Explain which evidence decided the current scorekeeper verdict.",
            dataQid: "battle:chat:chip:scorekeeper"
          }
        ]}
      />
    </aside>
  );
}
