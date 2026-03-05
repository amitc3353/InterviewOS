/**
 * Displays the current interview phase as a styled badge.
 */

"use client";

import { InterviewPhase } from "@/lib/types";

export interface PhaseIndicatorProps {
  /** Current interview phase. */
  phase: InterviewPhase;
}

const PHASE_LABELS: Record<InterviewPhase, string> = {
  [InterviewPhase.INTRO]: "Intro",
  [InterviewPhase.SCOPE]: "Scope",
  [InterviewPhase.ARCHITECTURE]: "Architecture",
  [InterviewPhase.DEEP_DIVE]: "Deep Dive",
  [InterviewPhase.FAILURE]: "Failure",
  [InterviewPhase.TRADEOFFS]: "Tradeoffs",
  [InterviewPhase.WRAP]: "Wrap",
};

const PHASE_STYLES: Record<InterviewPhase, string> = {
  [InterviewPhase.INTRO]: "bg-blue-900/40 text-blue-400 border-blue-700",
  [InterviewPhase.SCOPE]: "bg-cyan-900/40 text-cyan-400 border-cyan-700",
  [InterviewPhase.ARCHITECTURE]:
    "bg-purple-900/40 text-purple-400 border-purple-700",
  [InterviewPhase.DEEP_DIVE]:
    "bg-orange-900/40 text-orange-400 border-orange-700",
  [InterviewPhase.FAILURE]: "bg-red-900/40 text-red-400 border-red-700",
  [InterviewPhase.TRADEOFFS]:
    "bg-yellow-900/40 text-yellow-400 border-yellow-700",
  [InterviewPhase.WRAP]: "bg-green-900/40 text-green-400 border-green-700",
};

export default function PhaseIndicator({ phase }: PhaseIndicatorProps) {
  return (
    <div
      className="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/50 px-4 py-3"
      data-testid="phase-indicator"
    >
      <span className="text-sm text-gray-400">Phase</span>
      <span
        className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${PHASE_STYLES[phase]}`}
        data-testid="phase-badge"
      >
        {PHASE_LABELS[phase]}
      </span>
    </div>
  );
}
