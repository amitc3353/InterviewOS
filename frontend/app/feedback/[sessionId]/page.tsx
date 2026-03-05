/**
 * Post-interview feedback page displaying scoring results and transcript replay.
 *
 * Fetches scoring data via GET /api/sessions/[id]/feedback and displays:
 * - Overall assessment with hire signal
 * - 5-dimension scoring rubric with progress bars
 * - Narrative summary
 * - Full transcript replay with phase markers
 */

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import type { ScoringResult, InterviewSession } from "@/lib/types";
import { api } from "@/lib/api";
import ScoringRubric from "@/components/ScoringRubric";
import TranscriptReplay from "@/components/TranscriptReplay";

export default function FeedbackPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.sessionId as string;

  const [feedback, setFeedback] = useState<ScoringResult | null>(null);
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    Promise.all([
      api.getSessionFeedback(sessionId),
      api.getSession(sessionId),
    ])
      .then(([feedbackData, sessionData]) => {
        setFeedback(feedbackData);
        setSession(sessionData);
      })
      .catch(() => {
        setError("Failed to load feedback. Please try again.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, [sessionId]);

  if (loading) {
    return (
      <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-16">
        <p className="text-center text-gray-500" data-testid="loading">
          Loading feedback...
        </p>
      </main>
    );
  }

  if (error || !feedback) {
    return (
      <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-16">
        <p className="text-center text-red-400" role="alert">
          {error ?? "Feedback not available."}
        </p>
        <button
          onClick={() => router.push("/history")}
          className="mx-auto mt-4 rounded-md bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
        >
          Back to History
        </button>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-16">
      {/* Header */}
      <div className="mb-8">
        <button
          onClick={() => router.push("/history")}
          className="mb-4 text-sm text-gray-500 hover:text-gray-300"
          data-testid="back-to-history"
        >
          &larr; Back to History
        </button>
        <h1 className="text-3xl font-bold text-gray-100" data-testid="feedback-title">
          Interview Feedback
        </h1>
        <p className="mt-2 text-gray-400" data-testid="feedback-scenario">
          {feedback.scenario}
        </p>
        <div className="mt-1 flex items-center gap-4 text-sm text-gray-500">
          <span>{feedback.elapsed_minutes} minutes</span>
          <span>{feedback.total_turns} turns</span>
        </div>
      </div>

      {/* Narrative summary */}
      <div className="mb-8 rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wider text-gray-500">
          Assessment
        </h2>
        <p className="text-gray-300 leading-relaxed" data-testid="feedback-narrative">
          {feedback.narrative}
        </p>
      </div>

      {/* Scoring rubric */}
      <div className="mb-8">
        <h2 className="mb-4 text-sm font-medium uppercase tracking-wider text-gray-500">
          Dimension Scores
        </h2>
        <ScoringRubric
          dimensions={feedback.dimensions}
          overallScore={feedback.overall_score}
          hireSignal={feedback.hire_signal}
        />
      </div>

      {/* Transcript replay */}
      {session && session.conversation_history.length > 0 && (
        <div className="mb-8">
          <TranscriptReplay
            messages={session.conversation_history}
            sessionStartTime={session.session_start_time}
          />
        </div>
      )}
    </main>
  );
}
