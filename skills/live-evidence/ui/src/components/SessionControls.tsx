import { CirclePause, CirclePlay, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useRegisterAction } from "@/hooks/useRegisterAction";
import type { SessionStatus } from "@/types";

interface SessionControlsProps {
  status: SessionStatus;
  busy: boolean;
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
}

export function SessionControls({ status, busy, onStart, onPause, onStop }: SessionControlsProps) {
  useRegisterAction({
    element_id: "live-evidence:session:start",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SESSION_START",
    label: "Start or resume session",
    description: "Start a new local session or resume paused evidence retrieval",
  });
  useRegisterAction({
    element_id: "live-evidence:session:pause",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SESSION_PAUSE",
    label: "Pause retrieval",
    description: "Pause automatic evidence retrieval while preserving the transcript",
  });
  useRegisterAction({
    element_id: "live-evidence:session:stop",
    app: "live-evidence",
    action: "LIVE_EVIDENCE_SESSION_STOP",
    label: "Stop session",
    description: "Stop the session and preserve the final local state",
  });

  return (
    <div className="flex items-center gap-2" aria-label="Session controls">
      <Button
        data-qid="live-evidence:session:start"
        data-qs-action="LIVE_EVIDENCE_SESSION_START"
        title={status === "paused" ? "Resume automatic evidence retrieval" : "Start the local evidence session"}
        size="sm"
        variant={status === "listening" ? "secondary" : "default"}
        disabled={busy || status === "listening"}
        onClick={onStart}
      >
        <CirclePlay aria-hidden="true" className="size-3.5" />
        {status === "paused" ? "Resume" : "Start"}
      </Button>
      <Button
        data-qid="live-evidence:session:pause"
        data-qs-action="LIVE_EVIDENCE_SESSION_PAUSE"
        title="Pause automatic evidence retrieval"
        size="sm"
        variant="secondary"
        disabled={busy || status !== "listening"}
        onClick={onPause}
      >
        <CirclePause aria-hidden="true" className="size-3.5" />
        Pause
      </Button>
      <Button
        data-qid="live-evidence:session:stop"
        data-qs-action="LIVE_EVIDENCE_SESSION_STOP"
        title="Stop and preserve this evidence session"
        size="sm"
        variant="ghost"
        disabled={busy || status === "idle" || status === "stopped"}
        onClick={onStop}
      >
        <Square aria-hidden="true" className="size-3" />
        Stop
      </Button>
    </div>
  );
}
