"use client";

import type { Scenario, ScenarioDifficulty } from "@/lib/types";

const DIFFICULTY_STYLES: Record<ScenarioDifficulty, string> = {
  easy: "bg-green-900/40 text-green-400 border-green-700",
  medium: "bg-yellow-900/40 text-yellow-400 border-yellow-700",
  hard: "bg-red-900/40 text-red-400 border-red-700",
};

const DIFFICULTY_LABELS: Record<ScenarioDifficulty, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

export interface ScenarioCardProps {
  scenario: Scenario;
  onStart: (scenarioId: string) => void;
  disabled?: boolean;
}

export default function ScenarioCard({
  scenario,
  onStart,
  disabled = false,
}: ScenarioCardProps) {
  return (
    <div className="group flex flex-col rounded-lg border border-gray-800 bg-gray-900/50 p-6 transition-all hover:border-gray-600 hover:bg-gray-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-100">
          {scenario.name}
        </h3>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${DIFFICULTY_STYLES[scenario.difficulty]}`}
          data-testid="difficulty-badge"
        >
          {DIFFICULTY_LABELS[scenario.difficulty]}
        </span>
      </div>

      <p className="mb-4 flex-1 text-sm leading-relaxed text-gray-400">
        {scenario.description}
      </p>

      <button
        onClick={() => onStart(scenario.id)}
        disabled={disabled}
        className="mt-auto w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Start Interview
      </button>
    </div>
  );
}
