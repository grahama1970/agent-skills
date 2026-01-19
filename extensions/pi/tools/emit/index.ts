/**
 * Emit Tool - Inter-Agent Communication via Switchboard
 *
 * Allows agents to send messages to other agents through the Switchboard service.
 *
 * Actions:
 *   emit   - Send a message to another agent
 *   inbox  - View your pending messages (notifications)
 *   ack    - Acknowledge/delete a received message
 *   clear  - Clear all messages from your inbox
 *   list   - List agents connected to the switchboard
 *   status - Check switchboard health
 */

import { Type } from "@sinclair/typebox";
import type { CustomToolFactory } from "@mariozechner/pi-coding-agent";
import * as path from "node:path";

const SWITCHBOARD_URL = process.env.SWITCHBOARD_URL || "http://127.0.0.1:7890";
const TIMEOUT_MS = 5000;

interface SwitchboardMessage {
  id: string;
  from: string;
  to: string;
  type: string;
  priority: string;
  subject?: string;
  message: string;
  timestamp: string;
}

interface InboxResponse {
  agent: string;
  count: number;
  messages: SwitchboardMessage[];
  hasMore: boolean;
}

interface AgentInfo {
  name: string;
  cwd: string;
  registeredAt: string;
  lastSeen: string;
  connected: boolean;
  inboxCount: number;
}

async function fetchWithTimeout(url: string, options: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    return response;
  } catch (e) {
    clearTimeout(timeoutId);
    throw e;
  }
}

const factory: CustomToolFactory = (pi) => ({
  name: "emit_message",
  label: "Emit Message",
  description: `Send or manage inter-agent messages via the Switchboard.

Actions:
- emit: Send a message to another agent (requires: to, message; optional: type, priority, subject)
- inbox: View your pending messages/notifications
- ack: Acknowledge/delete a received message (requires: message_id)
- clear: Clear all messages from your inbox
- list: List all connected agents (shows their inbox counts)
- status: Check Switchboard health

Types: task, info, question, response, alert
Priorities: low, normal, high, urgent`,

  parameters: Type.Object({
    action: Type.Union(
      [
        Type.Literal("emit"),
        Type.Literal("inbox"),
        Type.Literal("ack"),
        Type.Literal("clear"),
        Type.Literal("list"),
        Type.Literal("status")
      ],
      { description: "Action to perform: emit, inbox, ack, clear, list, or status" }
    ),
    to: Type.Optional(Type.String({ description: "Target agent name (for emit action)" })),
    message: Type.Optional(Type.String({ description: "Message content (for emit action)" })),
    type: Type.Optional(
      Type.Union(
        [
          Type.Literal("task"),
          Type.Literal("info"),
          Type.Literal("question"),
          Type.Literal("response"),
          Type.Literal("alert")
        ],
        { description: "Message type (default: info)" }
      )
    ),
    priority: Type.Optional(
      Type.Union(
        [Type.Literal("low"), Type.Literal("normal"), Type.Literal("high"), Type.Literal("urgent")],
        { description: "Message priority (default: normal)" }
      )
    ),
    subject: Type.Optional(Type.String({ description: "Message subject line (optional)" })),
    message_id: Type.Optional(Type.String({ description: "Message ID to acknowledge (for ack action)" }))
  }),

  async execute(toolCallId, params) {
    const agentName = process.env.PI_AGENT_NAME || path.basename(pi.cwd);

    try {
      switch (params.action) {
        case "emit": {
          if (!params.to || !params.message) {
            return {
              content: [{ type: "text", text: "Error: 'to' and 'message' are required for emit action" }],
              isError: true
            };
          }

          const response = await fetchWithTimeout(`${SWITCHBOARD_URL}/emit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              from: agentName,
              to: params.to,
              type: params.type || "info",
              priority: params.priority || "normal",
              subject: params.subject,
              message: params.message
            })
          });

          if (!response.ok) {
            const error = await response.text();
            return {
              content: [{ type: "text", text: `Failed to send message: ${error}` }],
              isError: true
            };
          }

          const result = await response.json();
          return {
            content: [
              {
                type: "text",
                text: `Message sent successfully!\nID: ${result.id}\nTo: ${params.to}\nType: ${params.type || "info"}\nPriority: ${params.priority || "normal"}`
              }
            ],
            details: result
          };
        }

        case "inbox": {
          const response = await fetchWithTimeout(
            `${SWITCHBOARD_URL}/inbox/${encodeURIComponent(agentName)}`
          );

          if (!response.ok) {
            return {
              content: [{ type: "text", text: "Failed to fetch inbox. Is Switchboard running?" }],
              isError: true
            };
          }

          const data: InboxResponse = await response.json();

          if (data.count === 0) {
            return {
              content: [{ type: "text", text: `Inbox is empty. No pending messages for "${agentName}".` }],
              details: { count: 0, messages: [] }
            };
          }

          const priorityOrder: Record<string, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
          const sorted = data.messages.sort(
            (a, b) => (priorityOrder[a.priority] || 2) - (priorityOrder[b.priority] || 2)
          );

          let output = `Inbox for "${agentName}" (${data.count} message${data.count > 1 ? "s" : ""}):\n\n`;

          for (const msg of sorted) {
            const time = new Date(msg.timestamp).toLocaleString();
            const priority = msg.priority !== "normal" ? `[${msg.priority.toUpperCase()}] ` : "";
            output += `${priority}[${msg.type.toUpperCase()}] From: ${msg.from}\n`;
            if (msg.subject) output += `Subject: ${msg.subject}\n`;
            output += `Message: ${msg.message}\n`;
            output += `ID: ${msg.id} | Time: ${time}\n`;
            output += `---\n`;
          }

          output += `\nTo acknowledge: emit_message(action="ack", message_id="<id>")`;
          output += `\nTo clear all: emit_message(action="clear")`;

          return {
            content: [{ type: "text", text: output }],
            details: data
          };
        }

        case "ack": {
          if (!params.message_id) {
            return {
              content: [{ type: "text", text: "Error: 'message_id' is required for ack action" }],
              isError: true
            };
          }

          const response = await fetchWithTimeout(
            `${SWITCHBOARD_URL}/inbox/${encodeURIComponent(agentName)}/${encodeURIComponent(params.message_id)}`,
            { method: "DELETE" }
          );

          if (!response.ok) {
            const error = await response.text();
            return {
              content: [{ type: "text", text: `Failed to acknowledge message: ${error}` }],
              isError: true
            };
          }

          const result = await response.json();
          return {
            content: [
              {
                type: "text",
                text: `Message acknowledged and removed from inbox.\nID: ${params.message_id}\nFrom: ${result.acknowledged?.from || "unknown"}`
              }
            ],
            details: result
          };
        }

        case "clear": {
          const response = await fetchWithTimeout(
            `${SWITCHBOARD_URL}/inbox/${encodeURIComponent(agentName)}`,
            { method: "DELETE" }
          );

          if (!response.ok) {
            const error = await response.text();
            return {
              content: [{ type: "text", text: `Failed to clear inbox: ${error}` }],
              isError: true
            };
          }

          const result = await response.json();
          return {
            content: [
              {
                type: "text",
                text: `Inbox cleared. Removed ${result.cleared} message${result.cleared !== 1 ? "s" : ""}.`
              }
            ],
            details: result
          };
        }

        case "list": {
          const response = await fetchWithTimeout(`${SWITCHBOARD_URL}/agents`);

          if (!response.ok) {
            return {
              content: [{ type: "text", text: "Failed to list agents. Is Switchboard running?" }],
              isError: true
            };
          }

          const data: { agents: AgentInfo[] } = await response.json();

          if (data.agents.length === 0) {
            return {
              content: [{ type: "text", text: "No agents currently registered with Switchboard." }],
              details: { agents: [] }
            };
          }

          const agentList = data.agents
            .map((a) => {
              const lastSeen = new Date(a.lastSeen);
              const ago = Math.round((Date.now() - lastSeen.getTime()) / 1000);
              const agoStr =
                ago < 60
                  ? `${ago}s ago`
                  : ago < 3600
                    ? `${Math.round(ago / 60)}m ago`
                    : `${Math.round(ago / 3600)}h ago`;
              const status = a.connected ? "CONNECTED" : "offline";
              const self = a.name === agentName ? " (you)" : "";
              return `- ${a.name}${self} [${status}]\n  Path: ${a.cwd}\n  Last seen: ${agoStr} | Inbox: ${a.inboxCount} messages`;
            })
            .join("\n\n");

          return {
            content: [{ type: "text", text: `Registered Agents:\n\n${agentList}` }],
            details: data
          };
        }

        case "status": {
          const response = await fetchWithTimeout(`${SWITCHBOARD_URL}/health`);

          if (!response.ok) {
            return {
              content: [
                {
                  type: "text",
                  text: "Switchboard is not responding.\n\nStart it with:\n  ~/.pi/agent/services/switchboard/switchboard.sh start"
                }
              ],
              isError: true
            };
          }

          const health = await response.json();
          const uptime = Math.round(health.uptime);
          const uptimeStr =
            uptime < 60
              ? `${uptime}s`
              : uptime < 3600
                ? `${Math.round(uptime / 60)}m`
                : `${Math.round(uptime / 3600)}h`;

          return {
            content: [
              {
                type: "text",
                text: `Switchboard Status: OK
Uptime: ${uptimeStr}
Registered Agents: ${health.agents}
Connected (WebSocket): ${health.connectedAgents || 0}
Total Messages Queued: ${health.totalMessages}`
              }
            ],
            details: health
          };
        }

        default:
          return {
            content: [{ type: "text", text: `Unknown action: ${params.action}` }],
            isError: true
          };
      }
    } catch (e) {
      const isConnectionError =
        e instanceof Error && (e.name === "AbortError" || e.message.includes("ECONNREFUSED"));

      if (isConnectionError) {
        return {
          content: [
            {
              type: "text",
              text: `Switchboard is not running.\n\nTo start it, run:\n  ~/.pi/agent/services/switchboard/switchboard.sh start`
            }
          ],
          isError: true
        };
      }

      return {
        content: [{ type: "text", text: `Error: ${String(e)}` }],
        isError: true
      };
    }
  }
});

export default factory;
