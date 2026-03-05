/**
 * Full transcript replay with phase markers and timestamps.
 *
 * Used on the feedback page to review the entire conversation
 * after the interview is complete.
 */

"use client";

import type { Message } from "@/lib/types";
import { InterviewPhase } from "@/lib/types";

export interface TranscriptReplayProps {
  /** Conversation history from the session. */
  messages: Message[];
  /** Session start time (ISO 8601) for relative timestamps. */
  sessionStartTime: string;
}

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

/** Human-readable phase labels. */
const PHASE_LABELS: Record<InterviewPhase, string> = {
  [InterviewPhase.INTRO]: "Intro",
  [InterviewPhase.SCOPE]: "Scope",
  [InterviewPhase.ARCHITECTURE]: "Architecture",
  [InterviewPhase.DEEP_DIVE]: "Deep Dive",
  [InterviewPhase.FAILURE]: "Failure",
  [InterviewPhase.TRADEOFFS]: "Tradeoffs",
  [InterviewPhase.WRAP]: "Wrap",
};

/** Format relative time from session start to message timestamp. */
export function formatRelativeTime(
  messageTimestamp: string,
  sessionStartTime: string
): string {
  const start = new Date(sessionStartTime).getTime();
  const msg = new Date(messageTimestamp).getTime();
  const diffSeconds = Math.max(0, Math.floor((msg - start) / 1000));
  const minutes = Math.floor(diffSeconds / 60);
  const seconds = diffSeconds % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Extract phase from message content if it contains a phase marker.
 * Looks for [PHASE:phase_name] pattern in assistant messages.
 */
export function extractPhase(content: string): InterviewPhase | null {
  const match = content.match(/\[PHASE:(\w+)\]/i);
  if (!match) return null;
  const phaseStr = match[1].toLowerCase();
  const phaseValues = Object.values(InterviewPhase) as string[];
  if (phaseValues.includes(phaseStr)) {
    return phaseStr as InterviewPhase;
  }
  return null;
}

export default function TranscriptReplay({
  messages,
  sessionStartTime,
}: TranscriptReplayProps) {
  let currentPhase: InterviewPhase | null = null;

  return (
    <section data-testid="transcript-replay" className="space-y-2">
      <h3 className="mb-3 text-sm font-medium uppercase tracking-wider text-gray-500">
        Transcript Replay
      </h3>

      <div className="rounded-lg border border-gray-800 bg-gray-900/30 p-4">
        {messages.length === 0 && (
          <p className="text-center text-gray-600" data-testid="transcript-empty">
            No transcript available.
          </p>
        )}

        {messages.map((message, idx) => {
          const detectedPhase = extractPhase(message.content);
          const showDivider = detectedPhase !== null && detectedPhase !== currentPhase;
          if (detectedPhase !== null) {
            currentPhase = detectedPhase;
          }

          const isAssistant = message.role === "assistant";

          return (
            <div key={idx} className="mb-2">
              {showDivider && currentPhase && (
                <div
                  className={`my-3 flex items-center gap-2 border-t pt-3 ${PHASE_DIVIDER_STYLES[currentPhase]}`}
                  data-testid="phase-divider"
                >
                  <span className="text-xs font-semibold uppercase tracking-wide">
                    {PHASE_LABELS[currentPhase]}
                  </span>
                  <span className="flex-1 border-t border-current opacity-30" />
                </div>
              )}

              <div
                className={`flex ${isAssistant ? "justify-start" : "justify-end"}`}
                data-testid="replay-message"
              >
                <div
                  className={`max-w-[75%] rounded-lg px-3 py-2 ${
                    isAssistant
                      ? "bg-gray-800 text-gray-200"
                      : "bg-indigo-900/60 text-indigo-100"
                  }`}
                >
                  <div className="mb-1 flex items-center gap-2">
                    <span
                      className={`text-xs font-semibold ${
                        isAssistant ? "text-gray-400" : "text-indigo-400"
                      }`}
                      data-testid="speaker-label"
                    >
                      {isAssistant ? "Interviewer" : "You"}
                    </span>
                    <span className="text-xs text-gray-500" data-testid="message-timestamp">
                      {formatRelativeTime(message.timestamp, sessionStartTime)}
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed">{message.content}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
