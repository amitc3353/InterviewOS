"use client";

import type { Scenario } from "@/lib/types";
import ScenarioCard from "./ScenarioCard";

export interface ScenarioGridProps {
  scenarios: Scenario[];
  onStart: (scenarioId: string) => void;
  disabled?: boolean;
}

export default function ScenarioGrid({
  scenarios,
  onStart,
  disabled = false,
}: ScenarioGridProps) {
  if (scenarios.length === 0) {
    return (
      <p className="text-center text-gray-500" data-testid="empty-state">
        No scenarios available.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {scenarios.map((scenario) => (
        <ScenarioCard
          key={scenario.id}
          scenario={scenario}
          onStart={onStart}
          disabled={disabled}
        />
      ))}
    </div>
  );
}
