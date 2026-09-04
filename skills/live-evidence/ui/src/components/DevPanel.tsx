import { Background, Controls, MarkerType, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Check, ClipboardCopy, Copy, FileText, GitBranch, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useRegisterAction } from "@/hooks/useRegisterAction";

interface DevPrompt {
  id: string;
  name: string;
  description: string;
  model_env: string;
  text: string;
}

const NODE_STYLE = {
  background: "#0e101a",
  color: "#f1f5f9",
  border: "2px solid #334155",
  borderRadius: 12,
  fontSize: 13,
  fontWeight: 600,
  padding: 10,
  width: 190,
};
const AGENT_STYLE = { ...NODE_STYLE, border: "2px solid #6366f1", background: "#141731" };
const STATE_STYLE = { ...NODE_STYLE, border: "2px solid #10b981", background: "#0c1f18", width: 150 };

const PIPELINE_NODES = [
  { id: "audio", position: { x: 0, y: 140 }, data: { label: "🎙 PipeWire audio" }, style: NODE_STYLE },
  { id: "stt", position: { x: 230, y: 140 }, data: { label: "RealtimeSTT (Docker)" }, style: NODE_STYLE },
  { id: "scanner", position: { x: 460, y: 140 }, data: { label: "🔍 SCANNER agent — pause / 300 chars / wake word" }, style: AGENT_STYLE },
  { id: "queue", position: { x: 700, y: 60 }, data: { label: "Ready queue (complete questions)" }, style: NODE_STYLE },
  { id: "w1", position: { x: 930, y: 0 }, data: { label: "⚡ ANSWER worker 1 (exclusive lease)" }, style: AGENT_STYLE },
  { id: "w2", position: { x: 930, y: 120 }, data: { label: "⚡ ANSWER worker 2 (exclusive lease)" }, style: AGENT_STYLE },
  { id: "retrieval", position: { x: 700, y: 250 }, data: { label: "Retrieval: memory · code · ripgrep (+ authority envelopes)" }, style: NODE_STYLE },
  { id: "card", position: { x: 1170, y: 60 }, data: { label: "🃏 Flashcard published (deck + answer)" }, style: NODE_STYLE },
  { id: "reviewer", position: { x: 1170, y: 220 }, data: { label: "🧐 REVIEWER agent — correctness · scannability · staleness" }, style: AGENT_STYLE },
  { id: "amend", position: { x: 930, y: 320 }, data: { label: "✏️ Amendment (Memory re-grounded, streams into same card)" }, style: NODE_STYLE },
];

const PIPELINE_EDGES = [
  { id: "e1", source: "audio", target: "stt", animated: true },
  { id: "e2", source: "stt", target: "scanner", animated: true },
  { id: "e3", source: "scanner", target: "queue", label: "complete / follow_up" },
  { id: "e4", source: "queue", target: "w1" },
  { id: "e5", source: "queue", target: "w2" },
  { id: "e6", source: "w1", target: "card" },
  { id: "e7", source: "w2", target: "card" },
  { id: "e8", source: "retrieval", target: "w1" },
  { id: "e9", source: "retrieval", target: "w2" },
  { id: "e10", source: "card", target: "reviewer", label: "first answer" },
  { id: "e11", source: "reviewer", target: "amend", label: "weak" },
  { id: "e12", source: "amend", target: "card", label: "promote on complete" },
].map((edge) => ({ ...edge, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#64748b" }, labelStyle: { fill: "#94a3b8", fontSize: 11 } }));

const LIFECYCLE_NODES = [
  { id: "forming", position: { x: 0, y: 80 }, data: { label: "forming (no dispatch)" }, style: STATE_STYLE },
  { id: "complete", position: { x: 220, y: 80 }, data: { label: "complete (terminal verdict)" }, style: STATE_STYLE },
  { id: "leased", position: { x: 440, y: 80 }, data: { label: "leased (one worker)" }, style: STATE_STYLE },
  { id: "answered", position: { x: 660, y: 80 }, data: { label: "answered (terminal)" }, style: STATE_STYLE },
  { id: "reviewed", position: { x: 880, y: 80 }, data: { label: "reviewed ok / weak→revised" }, style: STATE_STYLE },
  { id: "repeat", position: { x: 660, y: 220 }, data: { label: "repeat → already_answered (no card, receipt)" }, style: NODE_STYLE },
  { id: "followup", position: { x: 880, y: 220 }, data: { label: "extension → follow_up (new linked card in parent)" }, style: NODE_STYLE },
];

const LIFECYCLE_EDGES = [
  { id: "l1", source: "forming", target: "complete" },
  { id: "l2", source: "complete", target: "leased" },
  { id: "l3", source: "leased", target: "answered" },
  { id: "l4", source: "answered", target: "reviewed" },
  { id: "l5", source: "answered", target: "repeat", label: "asked again" },
  { id: "l6", source: "answered", target: "followup", label: "new constraint" },
].map((edge) => ({ ...edge, markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#64748b" }, labelStyle: { fill: "#94a3b8", fontSize: 11 } }));

function PromptCard({ prompt }: { prompt: DevPrompt }) {
  const [copied, setCopied] = useState(false);
  useRegisterAction({
    element_id: "dev-prompt-copy",
    app: "live-evidence",
    action: "copy_prompt",
    label: "Copy prompt",
    description: "Copy one developer prompt to the clipboard.",
  });
  const handleCopy = () => {
    void navigator.clipboard.writeText(prompt.text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-[#0e101a]">
      <div className="flex items-start justify-between gap-4 border-b border-slate-800/80 bg-[#121424] px-5 py-3">
        <div>
          <h4 className="text-base font-bold text-white">{prompt.name}</h4>
          <p className="mt-1 text-xs leading-relaxed text-slate-400">{prompt.description}</p>
          <p className="mt-1 font-mono text-[11px] text-indigo-400">{prompt.model_env}</p>
        </div>
        <button
          type="button"
          data-qid="dev-prompt-copy"
          data-qs-action="copy_prompt"
          onClick={handleCopy}
          className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg border border-slate-700/60 bg-[#161826] px-3 py-1.5 text-xs font-medium text-slate-200 transition-colors hover:bg-[#202336]"
          title="Copy full prompt"
        >
          {copied ? (
            <>
              <Check className="size-3.5 text-emerald-400" aria-hidden="true" />
              <span className="font-semibold text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="size-3.5" aria-hidden="true" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="max-h-[420px] overflow-y-auto whitespace-pre-wrap p-5 font-mono text-[13px] leading-relaxed text-slate-200">
        {prompt.text}
      </pre>
    </div>
  );
}

interface DevPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function DevPanel({ isOpen, onClose }: DevPanelProps) {
  const [prompts, setPrompts] = useState<DevPrompt[]>([]);
  const [context, setContext] = useState("");
  const [allCopied, setAllCopied] = useState(false);
  const [tab, setTab] = useState<"prompts" | "architecture">("prompts");
  useRegisterAction({
    element_id: "dev-panel-controls",
    app: "live-evidence",
    action: "open_dev_panel_control",
    label: "Use dev panel controls",
    description: "Navigate dev panel tabs, close the panel, or copy the review bundle.",
  });

  useEffect(() => {
    if (!isOpen || prompts.length > 0) return;
    void fetch("/api/dev/prompts")
      .then((response) => response.json())
      .then((body) => {
        setPrompts(body.prompts ?? []);
        setContext(body.context ?? "");
      })
      .catch(() => setPrompts([]));
  }, [isOpen, prompts.length]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#090a0f]/98 backdrop-blur-sm">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-800/80 bg-[#0d0e15] px-6 py-3">
        <div className="flex items-center gap-4">
          <h3 className="text-base font-bold text-white">Settings · agent prompts & system internals</h3>
          <nav className="flex items-center rounded border border-gray-800/80 bg-[#131520] p-0.5">
            <button
              type="button"
              data-qid="dev-panel-tab-prompts"
              data-qs-action="select_prompts_tab"
              title="Show prompt internals"
              onClick={() => setTab("prompts")}
              className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition-colors ${
                tab === "prompts" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <FileText className="size-3.5" aria-hidden="true" />
              Prompts
            </button>
            <button
              type="button"
              data-qid="dev-panel-tab-architecture"
              data-qs-action="select_architecture_tab"
              title="Show architecture diagram"
              onClick={() => setTab("architecture")}
              className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-medium transition-colors ${
                tab === "architecture" ? "bg-indigo-600 text-white" : "text-gray-400 hover:text-gray-200"
              }`}
            >
              <GitBranch className="size-3.5" aria-hidden="true" />
              Architecture
            </button>
          </nav>
        </div>
        <button
          type="button"
          data-qid="dev-panel-close"
          data-qs-action="close_dev_panel"
          onClick={onClose}
          className="cursor-pointer rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-slate-100"
          title="Close dev panel"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>

      {tab === "prompts" ? (
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          <div className="flex items-center justify-between rounded-2xl border border-indigo-800/50 bg-indigo-950/30 px-5 py-3">
            <div>
              <p className="text-sm font-semibold text-white">Copy everything for external review</p>
              <p className="mt-0.5 text-xs text-slate-400">
                One markdown document: system context ($live-evidence + $curate-client, four-agent architecture,
                what each prompt achieves) followed by all three prompts verbatim.
              </p>
            </div>
            <button
              type="button"
              data-qid="dev-panel-copy-all"
              data-qs-action="copy_all_prompts"
              onClick={() => {
                const doc = [
                  context,
                  ...prompts.map(
                    (prompt) =>
                      `\n\n---\n\n# PROMPT: ${prompt.name}\n\n${prompt.description}\n\nModel: ${prompt.model_env}\n\n\u0060\u0060\u0060text\n${prompt.text}\n\u0060\u0060\u0060`,
                  ),
                ].join("");
                void navigator.clipboard.writeText(doc);
                setAllCopied(true);
                window.setTimeout(() => setAllCopied(false), 2000);
              }}
              className="flex shrink-0 cursor-pointer items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-indigo-950/50 transition-all hover:bg-indigo-500"
              title="Copy context + all prompts as one markdown document"
            >
              {allCopied ? (
                <>
                  <Check className="size-4 text-emerald-300" aria-hidden="true" />
                  <span>Copied all</span>
                </>
              ) : (
                <>
                  <ClipboardCopy className="size-4" aria-hidden="true" />
                  <span>Copy all</span>
                </>
              )}
            </button>
          </div>
          {prompts.length === 0 ? (
            <p className="text-sm text-slate-500">Loading prompts from the running server…</p>
          ) : (
            prompts.map((prompt) => <PromptCard key={prompt.id} prompt={prompt} />)
          )}
        </div>
      ) : (
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
          <div className="h-[52%] min-h-[340px] overflow-hidden rounded-2xl border border-slate-800 bg-[#0b0c13]">
            <div className="border-b border-slate-800/80 px-4 py-2 text-xs font-bold uppercase tracking-wider text-indigo-400">
              4-agent pipeline
            </div>
            <ReactFlow nodes={PIPELINE_NODES} edges={PIPELINE_EDGES} fitView colorMode="dark" proOptions={{ hideAttribution: true }}>
              <Background color="#1e293b" gap={24} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
          <div className="h-[40%] min-h-[280px] overflow-hidden rounded-2xl border border-slate-800 bg-[#0b0c13]">
            <div className="border-b border-slate-800/80 px-4 py-2 text-xs font-bold uppercase tracking-wider text-indigo-400">
              Question lifecycle (one-way, terminal states)
            </div>
            <ReactFlow nodes={LIFECYCLE_NODES} edges={LIFECYCLE_EDGES} fitView colorMode="dark" proOptions={{ hideAttribution: true }}>
              <Background color="#1e293b" gap={24} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </div>
      )}
    </div>
  );
}
