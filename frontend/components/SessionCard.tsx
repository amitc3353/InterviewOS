/**
 * History list item displaying session date, scenario, and overall score.
 */

"use client";

import type { SessionSummary } from "@/lib/types";

export interface SessionCardProps {
  /** Session summary data. */
  session: SessionSummary;
  /** Click handler to navigate to feedback. */
  onClick: (sessionId: string) => void;
}

/** Color for hire signal badge. */
const HIRE_SIGNAL_STYLES: Record<string, string> = {
  "Strong Yes": "bg-green-900/40 text-green-400 border-green-700",
  "Lean Yes": "bg-cyan-900/40 text-cyan-400 border-cyan-700",
  "Lean No": "bg-orange-900/40 text-orange-400 border-orange-700",
  No: "bg-red-900/40 text-red-400 border-red-700",
};

/** Format ISO date string to human-readable format. */
export function formatSessionDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function SessionCard({ session, onClick }: SessionCardProps) {
  return (
    <button
      onClick={() => onClick(session.session_id)}
      className="flex w-full items-center justify-between rounded-lg border border-gray-800 bg-gray-900/50 p-4 text-left transition-all hover:border-gray-600 hover:bg-gray-900"
      data-testid="session-card"
    >
      <div className="flex-1">
        <h3 className="text-base font-semibold text-gray-100" data-testid="session-scenario">
          {session.scenario}
        </h3>
        <p className="mt-1 text-sm text-gray-500" data-testid="session-date">
          {formatSessionDate(session.session_start_time)}
        </p>
        <p className="mt-0.5 text-xs text-gray-600">
          {session.elapsed_minutes} min
        </p>
      </div>

      <div className="flex items-center gap-3">
        {session.overall_score !== null && (
          <span className="text-2xl font-bold text-gray-100" data-testid="session-score">
            {session.overall_score.toFixed(1)}
          </span>
        )}
        {session.hire_signal && (
          <span
            className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${HIRE_SIGNAL_STYLES[session.hire_signal] ?? ""}`}
            data-testid="session-hire-signal"
          >
            {session.hire_signal}
          </span>
        )}
        {session.overall_score === null && (
          <span className="text-sm text-gray-600" data-testid="session-in-progress">
            In Progress
          </span>
        )}
      </div>
    </button>
  );
}
