"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Scenario } from "@/lib/types";
import { api } from "@/lib/api";
import ScenarioGrid from "@/components/ScenarioGrid";

export default function Home() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getScenarios()
      .then(setScenarios)
      .catch(() => setError("Failed to load scenarios."))
      .finally(() => setLoading(false));
  }, []);

  async function handleStart(scenarioId: string) {
    setStarting(true);
    setError(null);
    try {
      const session = await api.createSession(scenarioId);
      router.push(`/interview/${session.session_id}`);
    } catch {
      setError("Failed to create session. Please try again.");
      setStarting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-16">
      <div className="mb-12 text-center">
        <h1 className="text-4xl font-bold">InterviewOS</h1>
        <p className="mt-4 text-lg text-gray-400">
          AI-powered Staff-level system design interview simulator
        </p>
      </div>

      {error && (
        <p className="mb-6 text-center text-red-400" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-center text-gray-500" data-testid="loading">
          Loading scenarios...
        </p>
      ) : (
        <ScenarioGrid
          scenarios={scenarios}
          onStart={handleStart}
          disabled={starting}
        />
      )}
    </main>
  );
}
