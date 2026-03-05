/**
 * Elapsed time display that ticks every second.
 */

"use client";

import { useEffect, useState } from "react";

export interface TimerProps {
  /** ISO 8601 timestamp when the interview started. */
  startedAt: string;
}

/** Format total seconds as MM:SS or HH:MM:SS. */
export function formatElapsed(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;

  const mm = String(minutes).padStart(2, "0");
  const ss = String(seconds).padStart(2, "0");

  if (hours > 0) {
    const hh = String(hours).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }
  return `${mm}:${ss}`;
}

export default function Timer({ startedAt }: TimerProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const origin = new Date(startedAt).getTime();

    function tick() {
      setElapsed(Math.floor((Date.now() - origin) / 1000));
    }

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  return (
    <div
      className="flex items-center gap-2 rounded-lg border border-gray-800 bg-gray-900/50 px-4 py-3"
      data-testid="timer"
    >
      <span className="text-sm text-gray-400">Elapsed</span>
      <span className="font-mono text-lg text-gray-100">
        {formatElapsed(elapsed)}
      </span>
    </div>
  );
}
