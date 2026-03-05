/**
 * Real-time transcript panel displaying messages from the interview session.
 *
 * Features:
 * - Chat-like UI with alternating message alignments (interviewer left, user right)
 * - Phase transition dividers when the interview phase changes
 * - Highlighted locked constraints in monospace font
 * - Auto-scroll to latest message
 */

"use client";

import { useEffect, useRef } from "react";

import type { TranscriptEvent } from "@/lib/types";
import { InterviewPhase } from "@/lib/types";

export interface TranscriptPanelProps {
  /** Transcript events to display. */
  events: TranscriptEvent[];
  /** Whether the WebSocket connection is active. */
  isConnected: boolean;
  /** Locked constraints to highlight when mentioned. */
  lockedConstraints?: Record<string, string>;
}

/** Human-readable phase labels for dividers. */
const PHASE_LABELS: Record<InterviewPhase, string> = {
  [InterviewPhase.INTRO]: "Intro",
  [InterviewPhase.SCOPE]: "Scope",
  [InterviewPhase.ARCHITECTURE]: "Architecture",
  [InterviewPhase.DEEP_DIVE]: "Deep Dive",
  [InterviewPhase.FAILURE]: "Failure",
  [InterviewPhase.TRADEOFFS]: "Tradeoffs",
  [InterviewPhase.WRAP]: "Wrap",
};

/** Phase-specific divider colors. */
const PHASE_DIVIDER_STYLES: Record<InterviewPhase, string> = {
  [InterviewPhase.INTRO]: "border-blue-700 text-blue-400",
  [InterviewPhase.SCOPE]: "border-cyan-700 text-cyan-400",
  [InterviewPhase.ARCHITECTURE]: "border-purple-700 text-purple-400",
  [InterviewPhase.DEEP_DIVE]: "border-orange-700 text-orange-400",
  [InterviewPhase.FAILURE]: "border-red-700 text-red-400",
  [InterviewPhase.TRADEOFFS]: "border-yellow-700 text-yellow-400",
  [InterviewPhase.WRAP]: "border-green-700 text-green-400",
};

/**
 * Highlight locked constraint keys within message text.
 * Wraps matching constraint keys in a monospace-styled span.
 */
function highlightConstraints(
  text: string,
  constraints: Record<string, string>
): (string | JSX.Element)[] {
  const keys = Object.keys(constraints);
  if (keys.length === 0) return [text];

  // Escape special regex chars in keys and join with |
  const escaped = keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");

  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const isConstraint = keys.some(
      (k) => k.toLowerCase() === part.toLowerCase()
    );
    if (isConstraint) {
      return (
        <span
          key={i}
          className="rounded bg-amber-900/40 px-1 font-mono text-amber-300"
          data-testid="constraint-highlight"
        >
          {part}
        </span>
      );
    }
    return part;
  });
}

/** Format a Unix timestamp (seconds) to HH:MM:SS or MM:SS. */
function formatTimestamp(ts: number): string {
  const date = new Date(ts * 1000);
  const hours = date.getHours();
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const seconds = date.getSeconds().toString().padStart(2, "0");
  if (hours > 0) return `${hours}:${minutes}:${seconds}`;
  return `${minutes}:${seconds}`;
}

export default function TranscriptPanel({
  events,
  isConnected,
  lockedConstraints = {},
}: TranscriptPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events]);

  // Track phase changes to render dividers
  let lastPhase: InterviewPhase | undefined;

  return (
    <section className="flex flex-1 flex-col" data-testid="transcript-panel">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium uppercase tracking-wider text-gray-500">
          Transcript
        </h3>
        <span
          className={`h-2 w-2 rounded-full ${
            isConnected ? "bg-green-500" : "bg-gray-600"
          }`}
          data-testid="connection-dot"
          title={isConnected ? "Connected" : "Disconnected"}
        />
      </div>

      <div
        ref={scrollRef}
        className="flex flex-1 flex-col gap-2 overflow-y-auto rounded-lg border border-gray-800 bg-gray-900/30 p-4"
        data-testid="transcript-messages"
      >
        {events.length === 0 && (
          <p className="text-center text-gray-600" data-testid="transcript-empty">
            Transcript will appear here during the interview.
          </p>
        )}

        {events.map((event, idx) => {
          const showPhaseDivider =
            event.phase !== undefined && event.phase !== lastPhase;
          if (event.phase !== undefined) {
            lastPhase = event.phase;
          }

          const isInterviewer = event.speaker === "interviewer";

          return (
            <div key={idx}>
              {/* Phase transition divider */}
              {showPhaseDivider && event.phase && (
                <div
                  className={`my-3 flex items-center gap-2 border-t pt-3 ${PHASE_DIVIDER_STYLES[event.phase]}`}
                  data-testid="phase-divider"
                >
                  <span className="text-xs font-semibold uppercase tracking-wide">
                    {PHASE_LABELS[event.phase]}
                  </span>
                  <span className="flex-1 border-t border-current opacity-30" />
                </div>
              )}

              {/* Message bubble */}
              <div
                className={`flex ${isInterviewer ? "justify-start" : "justify-end"}`}
                data-testid="transcript-message"
              >
                <div
                  className={`max-w-[75%] rounded-lg px-3 py-2 ${
                    isInterviewer
                      ? "bg-gray-800 text-gray-200"
                      : "bg-indigo-900/60 text-indigo-100"
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span
                      className={`text-xs font-semibold ${
                        isInterviewer ? "text-gray-400" : "text-indigo-400"
                      }`}
                      data-testid="speaker-label"
                    >
                      {isInterviewer ? "Interviewer" : "You"}
                    </span>
                    <span className="text-xs text-gray-500">
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed">
                    {highlightConstraints(event.text, lockedConstraints)}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
