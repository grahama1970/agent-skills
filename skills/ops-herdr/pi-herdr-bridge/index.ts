// pi-herdr-bridge: companion extension to pi-intercom.
// Adds cross-provider session messaging: the roster merges intercom-connected
// Pi sessions with Herdr-detected Codex/Claude/Pi panes, and sends route to
// the best inbound lane per provider (intercom broker, codex queue, herdr
// agent prompt). Inbound Pi delivery stays owned by pi-intercom.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { StringEnum } from "@earendil-works/pi-ai";
import { buildRoster, sendToTarget, pickLane } from "./route.mjs";

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "herdr_bridge",
    label: "Herdr Bridge",
    description:
      "List every reachable agent session on this machine (Pi via pi-intercom, "
      + "Codex and Claude Code via Herdr) and send a bounded text message to one "
      + "of them. Messages are notifications or questions; durable work orders "
      + "and receipts stay file-based.",
    promptSnippet: "Cross-provider session roster + targeted send (pi/codex/claude)",
    promptGuidelines: [
      "Use herdr_bridge with action=list to discover other live agent sessions before delegating or asking another session a question.",
      "Use herdr_bridge with action=send for bounded notifications, clarifying questions, and completion reports; put large payloads in files and send the path.",
    ],
    parameters: Type.Object({
      action: StringEnum(["list", "send"] as const),
      to: Type.Optional(Type.String({ description: "Target: intercom name, herdr terminal title, session-ref value, or pane id" })),
      text: Type.Optional(Type.String({ description: "Message text (required for send)" })),
      expectsReply: Type.Optional(Type.Boolean({ description: "Mark the message as expecting a reply (intercom lane only)" })),
    }),
    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const fromName = ctx?.sessionName ?? "pi-herdr-bridge";
      if (params.action === "list") {
        const { roster, errors } = await buildRoster({ fromName });
        const rows = roster.map((e) => ({ ...e, lane: pickLane(e) }));
        const summary = rows
          .map((r) => `${r.provider} ${r.name ?? "(unnamed)"} [${r.lane}] ${r.status ?? ""}`)
          .join("\n");
        return {
          content: [{ type: "text", text: summary || "no reachable sessions" }],
          details: { sessions: rows, errors },
        };
      }
      if (!params.to || !params.text) {
        return {
          content: [{ type: "text", text: "send requires `to` and `text`" }],
          isError: true,
        };
      }
      const result = await sendToTarget(params.to, params.text, {
        fromName,
        expectsReply: params.expectsReply,
      });
      return {
        content: [{
          type: "text",
          text: result.ok
            ? `sent via ${result.lane} to ${params.to}`
            : `send failed: ${result.error}`,
        }],
        details: result,
        ...(result.ok ? {} : { isError: true }),
      };
    },
  });
}
