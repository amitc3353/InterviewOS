/**
 * Visual scoring rubric displaying 5 dimension scores with progress bars.
 *
 * Dimensions: scope (requirements_gathering), architecture (system_architecture),
 * depth (technical_depth), failure_handling (scalability_reliability), tradeoffs (communication).
 */

"use client";

import type { DimensionScore } from "@/lib/types";

export interface ScoringRubricProps {
  /** Map of dimension key → DimensionScore. */
  dimensions: Record<string, DimensionScore>;
  /** Overall weighted score (1-5). */
  overallScore: number;
  /** Hire signal text. */
  hireSignal: "Strong Yes" | "Lean Yes" | "Lean No" | "No";
}

/** Human-readable labels for dimension keys. */
const DIMENSION_LABELS: Record<string, string> = {
  requirements_gathering: "Scope & Requirements",
  system_architecture: "System Architecture",
  technical_depth: "Technical Depth",
  scalability_reliability: "Failure Handling",
  communication: "Tradeoffs & Communication",
};

/** Display order for dimensions. */
const DIMENSION_ORDER = [
  "requirements_gathering",
  "system_architecture",
  "technical_depth",
  "scalability_reliability",
  "communication",
];

/** Color for score bar based on score value. */
function scoreColor(score: number): string {
  if (score >= 4) return "bg-green-500";
  if (score >= 3) return "bg-yellow-500";
  if (score >= 2) return "bg-orange-500";
  return "bg-red-500";
}

/** Color for hire signal badge. */
const HIRE_SIGNAL_STYLES: Record<string, string> = {
  "Strong Yes": "bg-green-900/40 text-green-400 border-green-700",
  "Lean Yes": "bg-cyan-900/40 text-cyan-400 border-cyan-700",
  "Lean No": "bg-orange-900/40 text-orange-400 border-orange-700",
  No: "bg-red-900/40 text-red-400 border-red-700",
};

export default function ScoringRubric({
  dimensions,
  overallScore,
  hireSignal,
}: ScoringRubricProps) {
  const orderedDimensions = DIMENSION_ORDER.filter((key) => dimensions[key]);

  return (
    <div data-testid="scoring-rubric" className="space-y-6">
      {/* Overall score and hire signal */}
      <div className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900/50 p-6">
        <div>
          <p className="text-sm text-gray-400">Overall Score</p>
          <p className="text-4xl font-bold text-gray-100" data-testid="overall-score">
            {overallScore.toFixed(1)}
          </p>
          <p className="text-sm text-gray-500">out of 5.0</p>
        </div>
        <span
          className={`rounded-full border px-4 py-1.5 text-sm font-semibold ${HIRE_SIGNAL_STYLES[hireSignal] ?? ""}`}
          data-testid="hire-signal"
        >
          {hireSignal}
        </span>
      </div>

      {/* Individual dimension scores */}
      <div className="space-y-4" data-testid="dimension-list">
        {orderedDimensions.map((key) => {
          const dim = dimensions[key];
          const widthPct = (dim.score / 5) * 100;

          return (
            <div
              key={key}
              className="rounded-lg border border-gray-800 bg-gray-900/50 p-4"
              data-testid="dimension-card"
            >
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-sm font-medium text-gray-200">
                  {DIMENSION_LABELS[key] ?? dim.dimension}
                </h4>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-gray-100" data-testid="dimension-score">
                    {dim.score}
                  </span>
                  <span className="text-xs text-gray-500">{dim.label}</span>
                </div>
              </div>

              {/* Progress bar */}
              <div
                className="mb-3 h-2 w-full rounded-full bg-gray-800"
                data-testid="progress-bar-track"
              >
                <div
                  className={`h-2 rounded-full transition-all ${scoreColor(dim.score)}`}
                  style={{ width: `${widthPct}%` }}
                  data-testid="progress-bar-fill"
                />
              </div>

              <p className="mb-2 text-sm text-gray-400">{dim.rationale}</p>

              {/* Strengths and gaps */}
              {dim.strengths.length > 0 && (
                <div className="mb-1">
                  <p className="text-xs font-semibold text-green-400">Strengths</p>
                  <ul className="list-inside list-disc text-sm text-gray-300">
                    {dim.strengths.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
              {dim.gaps.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-red-400">Areas for Improvement</p>
                  <ul className="list-inside list-disc text-sm text-gray-300">
                    {dim.gaps.map((g, i) => (
                      <li key={i}>{g}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
