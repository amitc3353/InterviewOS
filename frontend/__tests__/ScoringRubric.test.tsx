/**
 * Tests for ScoringRubric — rendering, progress bars, hire signal, edge cases.
 */

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import ScoringRubric from "@/components/ScoringRubric";
import type { DimensionScore } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeDimension(overrides: Partial<DimensionScore> = {}): DimensionScore {
  return {
    dimension: "system_architecture",
    score: 4,
    label: "Strong",
    rationale: "Good architecture design.",
    strengths: ["Clean separation of concerns"],
    gaps: ["Could improve caching strategy"],
    ...overrides,
  };
}

function makeFullDimensions(): Record<string, DimensionScore> {
  return {
    requirements_gathering: makeDimension({
      dimension: "requirements_gathering",
      score: 3,
      label: "Solid",
      rationale: "Good requirements analysis.",
      strengths: ["Clarified constraints"],
      gaps: ["Missed edge cases"],
    }),
    system_architecture: makeDimension({
      dimension: "system_architecture",
      score: 4,
      label: "Strong",
      rationale: "Strong architecture.",
      strengths: ["Clean design"],
      gaps: [],
    }),
    technical_depth: makeDimension({
      dimension: "technical_depth",
      score: 5,
      label: "Exceptional",
      rationale: "Deep technical knowledge.",
      strengths: ["Expert-level understanding"],
      gaps: [],
    }),
    scalability_reliability: makeDimension({
      dimension: "scalability_reliability",
      score: 2,
      label: "Developing",
      rationale: "Needs improvement.",
      strengths: [],
      gaps: ["Missing failover strategy"],
    }),
    communication: makeDimension({
      dimension: "communication",
      score: 4,
      label: "Strong",
      rationale: "Clear communication.",
      strengths: ["Well-structured explanations"],
      gaps: [],
    }),
  };
}

// ---------------------------------------------------------------------------
// Tests — Overall Score
// ---------------------------------------------------------------------------

describe("ScoringRubric", () => {
  it("renders overall score with one decimal place", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.8}
        hireSignal="Lean Yes"
      />
    );

    expect(screen.getByTestId("overall-score")).toHaveTextContent("3.8");
  });

  it("renders hire signal badge", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={4.2}
        hireSignal="Strong Yes"
      />
    );

    const badge = screen.getByTestId("hire-signal");
    expect(badge).toHaveTextContent("Strong Yes");
    expect(badge.className).toContain("green");
  });

  it("renders Lean No hire signal with orange styling", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={2.8}
        hireSignal="Lean No"
      />
    );

    const badge = screen.getByTestId("hire-signal");
    expect(badge).toHaveTextContent("Lean No");
    expect(badge.className).toContain("orange");
  });

  it("renders No hire signal with red styling", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={1.5}
        hireSignal="No"
      />
    );

    const badge = screen.getByTestId("hire-signal");
    expect(badge).toHaveTextContent("No");
    expect(badge.className).toContain("red");
  });

  // ---------------------------------------------------------------------------
  // Tests — Dimension Cards
  // ---------------------------------------------------------------------------

  it("renders all 5 dimension cards", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    const cards = screen.getAllByTestId("dimension-card");
    expect(cards).toHaveLength(5);
  });

  it("displays dimension scores as integers", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    const scores = screen.getAllByTestId("dimension-score");
    const scoreTexts = scores.map((el) => el.textContent);
    expect(scoreTexts).toEqual(["3", "4", "5", "2", "4"]);
  });

  // ---------------------------------------------------------------------------
  // Tests — Progress Bars
  // ---------------------------------------------------------------------------

  it("renders progress bars with correct width percentages", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    const fills = screen.getAllByTestId("progress-bar-fill");
    // Score 3 → 60%, Score 4 → 80%, Score 5 → 100%, Score 2 → 40%, Score 4 → 80%
    expect(fills[0]).toHaveStyle({ width: "60%" });
    expect(fills[1]).toHaveStyle({ width: "80%" });
    expect(fills[2]).toHaveStyle({ width: "100%" });
    expect(fills[3]).toHaveStyle({ width: "40%" });
    expect(fills[4]).toHaveStyle({ width: "80%" });
  });

  it("applies green color for scores >= 4", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    const fills = screen.getAllByTestId("progress-bar-fill");
    // Score 4 (index 1) should be green
    expect(fills[1].className).toContain("green");
    // Score 5 (index 2) should be green
    expect(fills[2].className).toContain("green");
  });

  it("applies orange color for scores of 2", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    const fills = screen.getAllByTestId("progress-bar-fill");
    // Score 2 (index 3) should be orange
    expect(fills[3].className).toContain("orange");
  });

  // ---------------------------------------------------------------------------
  // Tests — Strengths and Gaps
  // ---------------------------------------------------------------------------

  it("renders strengths bullets", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    expect(screen.getByText("Clarified constraints")).toBeInTheDocument();
    expect(screen.getByText("Expert-level understanding")).toBeInTheDocument();
  });

  it("renders gap bullets", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    expect(screen.getByText("Missed edge cases")).toBeInTheDocument();
    expect(screen.getByText("Missing failover strategy")).toBeInTheDocument();
  });

  it("does not render strengths section when empty", () => {
    const dims = {
      scalability_reliability: makeDimension({
        dimension: "scalability_reliability",
        score: 2,
        label: "Developing",
        rationale: "Needs work.",
        strengths: [],
        gaps: ["Missing failover"],
      }),
    };

    render(
      <ScoringRubric dimensions={dims} overallScore={2.0} hireSignal="No" />
    );

    // Should have gaps but not strengths heading within this card
    expect(screen.getByText("Areas for Improvement")).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Tests — Edge cases
  // ---------------------------------------------------------------------------

  it("handles a subset of dimensions gracefully", () => {
    const dims = {
      system_architecture: makeDimension(),
    };

    render(
      <ScoringRubric dimensions={dims} overallScore={4.0} hireSignal="Strong Yes" />
    );

    const cards = screen.getAllByTestId("dimension-card");
    expect(cards).toHaveLength(1);
  });

  it("renders rationale text for each dimension", () => {
    render(
      <ScoringRubric
        dimensions={makeFullDimensions()}
        overallScore={3.6}
        hireSignal="Lean Yes"
      />
    );

    expect(screen.getByText("Good requirements analysis.")).toBeInTheDocument();
    expect(screen.getByText("Strong architecture.")).toBeInTheDocument();
  });
});
