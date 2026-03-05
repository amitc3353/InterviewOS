/**
 * Interview room page — main screen for conducting a voice interview session.
 *
 * Layout: CSS Grid with left sidebar (voice controls, phase, timer)
 * and right panel (transcript placeholder).
 */

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import type { InterviewSession } from "@/lib/types";
import { InterviewPhase } from "@/lib/types";
import { api } from "@/lib/api";
import { useLiveKit } from "@/hooks/useLiveKit";
import VoiceControls from "@/components/VoiceControls";
import PhaseIndicator from "@/components/PhaseIndicator";
import Timer from "@/components/Timer";

export default function InterviewRoom() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const sessionId = params.id;

  const [session, setSession] = useState<InterviewSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { connectionState, isMicEnabled, toggleMic, disconnect, error: lkError } =
    useLiveKit({ sessionId });

  useEffect(() => {
    api
      .getSession(sessionId)
      .then(setSession)
      .catch(() => setError("Failed to load interview session."))
      .finally(() => setLoading(false));
  }, [sessionId]);

  function handleEndInterview() {
    disconnect();
    router.push("/");
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-gray-500" data-testid="loading">
          Loading interview...
        </p>
      </main>
    );
  }

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-red-400" role="alert">
          {error}
        </p>
      </main>
    );
  }

  const phase = session?.phase ?? InterviewPhase.INTRO;
  const startedAt = session?.session_start_time ?? new Date().toISOString();

  return (
    <main className="grid min-h-screen grid-cols-[280px_1fr]" data-testid="interview-room">
      {/* Left sidebar */}
      <aside className="flex flex-col gap-4 border-r border-gray-800 p-6">
        <h2 className="text-lg font-semibold text-gray-100" data-testid="scenario-title">
          {session?.scenario ?? "Interview"}
        </h2>

        <PhaseIndicator phase={phase} />
        <Timer startedAt={startedAt} />
        <VoiceControls
          isMicEnabled={isMicEnabled}
          onToggleMic={toggleMic}
          onEndInterview={handleEndInterview}
          connectionState={connectionState}
        />

        {lkError && (
          <p className="text-sm text-red-400" role="alert" data-testid="lk-error">
            {lkError}
          </p>
        )}
      </aside>

      {/* Right panel — transcript placeholder */}
      <section className="flex flex-col p-6">
        <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-gray-500">
          Transcript
        </h3>
        <div
          className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-gray-800 bg-gray-900/30"
          data-testid="transcript-panel"
        >
          <p className="text-gray-600">
            Transcript will appear here during the interview.
          </p>
        </div>
      </section>
    </main>
  );
}
