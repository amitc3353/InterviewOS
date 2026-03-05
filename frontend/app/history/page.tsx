/**
 * Session history page listing all past interview sessions.
 *
 * Fetches GET /api/sessions and renders a list of SessionCards.
 * Clicking a card navigates to /feedback/[sessionId].
 */

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { SessionSummary } from "@/lib/types";
import { api } from "@/lib/api";
import SessionCard from "@/components/SessionCard";

export default function HistoryPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSessions()
      .then(setSessions)
      .catch(() => setError("Failed to load session history."))
      .finally(() => setLoading(false));
  }, []);

  function handleSessionClick(sessionId: string) {
    router.push(`/feedback/${sessionId}`);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-6 py-16">
      <div className="mb-8">
        <button
          onClick={() => router.push("/")}
          className="mb-4 text-sm text-gray-500 hover:text-gray-300"
          data-testid="back-to-home"
        >
          &larr; Back to Home
        </button>
        <h1 className="text-3xl font-bold text-gray-100">Session History</h1>
        <p className="mt-2 text-gray-400">
          Review your past interview sessions and scores.
        </p>
      </div>

      {error && (
        <p className="mb-6 text-center text-red-400" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-center text-gray-500" data-testid="loading">
          Loading sessions...
        </p>
      ) : sessions.length === 0 ? (
        <div className="text-center" data-testid="empty-state">
          <p className="text-gray-500">No sessions yet.</p>
          <button
            onClick={() => router.push("/")}
            className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500"
          >
            Start Your First Interview
          </button>
        </div>
      ) : (
        <div className="space-y-3" data-testid="session-list">
          {sessions.map((session) => (
            <SessionCard
              key={session.session_id}
              session={session}
              onClick={handleSessionClick}
            />
          ))}
        </div>
      )}
    </main>
  );
}
