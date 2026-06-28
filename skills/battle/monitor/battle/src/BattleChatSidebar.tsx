import { FormEvent, useMemo, useState } from "react";
import { ArrowUp, Bot, MessageSquare, Pause, Route, Sparkles, UserRound } from "lucide-react";

import type { LoadedBattleArtifacts } from "./artifacts";

type ChatRole = "user" | "assistant";

interface BattleChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
  receipt?: BattleHumanInterjection;
}

interface BattleHumanInterjection {
  schema: "battle.human_interjection.v1";
  battle_id: string;
  action: "pause" | "course_correct" | "persona_redirect" | "annotate";
  message: string;
  target: string;
  created_at: string;
  status: "LOCAL_PREVIEW";
}

interface StarterChip {
  label: string;
  prompt: string;
  action: BattleHumanInterjection["action"];
  qid: string;
}

const STARTER_CHIPS: StarterChip[] = [
  {
    label: "Pause battle",
    prompt: "Pause after this round and wait for human review.",
    action: "pause",
    qid: "battle:chat:chip:pause"
  },
  {
    label: "Redirect Red",
    prompt: "Redirect Red toward high/low-level exploit combinations against the current target.",
    action: "persona_redirect",
    qid: "battle:chat:chip:red"
  },
  {
    label: "Ask Scorekeeper",
    prompt: "Explain which evidence decided the current scorekeeper verdict.",
    action: "annotate",
    qid: "battle:chat:chip:scorekeeper"
  }
];

function makeId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function inferAction(text: string): BattleHumanInterjection["action"] {
  const lowered = text.toLowerCase();
  if (lowered.includes("pause") || lowered.includes("stop")) return "pause";
  if (lowered.includes("persona") || lowered.includes("red") || lowered.includes("blue")) return "persona_redirect";
  if (lowered.includes("why") || lowered.includes("explain") || lowered.includes("evidence")) return "annotate";
  return "course_correct";
}

function actionLabel(action: BattleHumanInterjection["action"]): string {
  if (action === "pause") return "Pause";
  if (action === "persona_redirect") return "Persona redirect";
  if (action === "annotate") return "Annotation";
  return "Course correction";
}

function createReceipt(data: LoadedBattleArtifacts, text: string): BattleHumanInterjection {
  const now = new Date().toISOString();
  return {
    schema: "battle.human_interjection.v1",
    battle_id: data.monitorIndex.battle_id,
    action: inferAction(text),
    message: text,
    target: data.monitorIndex.scoreboard,
    created_at: now,
    status: "LOCAL_PREVIEW"
  };
}

function MessageBubble({ message }: { message: BattleChatMessage }) {
  const isUser = message.role === "user";

  return (
    <article className={`chatMessage ${isUser ? "user" : "assistant"}`} data-qid={`battle:chat:message:${message.role}`}>
      <div className="chatAvatar" aria-hidden="true">
        {isUser ? <UserRound size={15} /> : <Bot size={15} />}
      </div>
      <div className="chatBubble">
        <div className="chatMeta">
          <span>{isUser ? "Human" : "Battle Agent"}</span>
          <time>{new Date(message.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
        </div>
        <p>{message.content}</p>
        {message.receipt ? (
          <div className="receiptPreview" data-qid="battle:chat:receipt-preview">
            <span>{actionLabel(message.receipt.action)}</span>
            <code>{message.receipt.schema}</code>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function BattleChatSidebar({ data }: { data: LoadedBattleArtifacts }) {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<BattleChatMessage[]>([
    {
      id: "assistant-initial",
      role: "assistant",
      content:
        "Human interjections are captured here as local Battle handoff previews. They do not mutate Tau or the orchestrator until a schema-valid backend exists.",
      createdAt: new Date().toISOString()
    }
  ]);

  const latestReceipt = useMemo(() => {
    return [...messages].reverse().find((message) => message.receipt)?.receipt;
  }, [messages]);

  function submit(text: string): void {
    const trimmed = text.trim();
    if (!trimmed) return;

    const receipt = createReceipt(data, trimmed);
    const userMessage: BattleChatMessage = {
      id: makeId("human"),
      role: "user",
      content: trimmed,
      createdAt: receipt.created_at,
      receipt
    };
    const assistantMessage: BattleChatMessage = {
      id: makeId("assistant"),
      role: "assistant",
      content: `Captured as ${actionLabel(receipt.action).toLowerCase()} preview for ${receipt.battle_id}. Backend Tau dispatch is intentionally blocked in this v1 UI slice.`,
      createdAt: new Date().toISOString()
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setDraft("");
  }

  function submitForm(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    submit(draft);
  }

  return (
    <aside className="chatSidebar" data-qid="battle:chat:shell" data-surface="battle-monitor">
      <header className="chatHeader" data-qid="battle:chat:header">
        <div className="chatIcon">
          <MessageSquare size={18} />
        </div>
        <div>
          <div className="eyebrow">Human Interjection</div>
          <h2>Battle Chat</h2>
        </div>
      </header>

      <div className="chatStatus" data-qid="battle:chat:status">
        <Sparkles size={14} />
        <span>Shared Watch-style chat UX</span>
      </div>

      <div className="chatChips" data-qid="battle:chat:starter-chips">
        {STARTER_CHIPS.map((chip) => (
          <button
            key={chip.qid}
            type="button"
            data-qid={chip.qid}
            data-qs-action={`BATTLE_CHAT_${chip.action.toUpperCase()}`}
            title={chip.prompt}
            onClick={() => submit(chip.prompt)}
          >
            {chip.action === "pause" ? <Pause size={13} /> : <Route size={13} />}
            <span>{chip.label}</span>
          </button>
        ))}
      </div>

      <div className="chatMessages" data-qid="battle:chat:messages">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </div>

      {latestReceipt ? (
        <section className="latestReceipt" data-qid="battle:chat:latest-receipt">
          <div className="eyebrow">Latest preview receipt</div>
          <pre>{JSON.stringify(latestReceipt, null, 2)}</pre>
        </section>
      ) : null}

      <form className="chatComposer" data-qid="battle:chat:composer" onSubmit={submitForm}>
        <textarea
          data-qid="battle:chat:input"
          value={draft}
          rows={1}
          placeholder="Interject, pause, redirect personas, or ask about evidence..."
          onChange={(event) => setDraft(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit(draft);
            }
          }}
        />
        <button
          type="submit"
          data-qid="battle:chat:send"
          data-qs-action="BATTLE_CHAT_SEND_INTERJECTION"
          title="Send human interjection"
          disabled={!draft.trim()}
        >
          <ArrowUp size={16} />
        </button>
      </form>
    </aside>
  );
}
