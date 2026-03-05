/**
 * Tests for PhaseIndicator — correct label and styling for each phase.
 */

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { InterviewPhase } from "@/lib/types";
import PhaseIndicator from "@/components/PhaseIndicator";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PhaseIndicator", () => {
  it("renders the phase indicator container", () => {
    render(<PhaseIndicator phase={InterviewPhase.INTRO} />);

    expect(screen.getByTestId("phase-indicator")).toBeInTheDocument();
  });

  it.each([
    [InterviewPhase.INTRO, "Intro", "blue"],
    [InterviewPhase.SCOPE, "Scope", "cyan"],
    [InterviewPhase.ARCHITECTURE, "Architecture", "purple"],
    [InterviewPhase.DEEP_DIVE, "Deep Dive", "orange"],
    [InterviewPhase.FAILURE, "Failure", "red"],
    [InterviewPhase.TRADEOFFS, "Tradeoffs", "yellow"],
    [InterviewPhase.WRAP, "Wrap", "green"],
  ])(
    "renders %s phase with label '%s' and %s styling",
    (phase, expectedLabel, expectedColor) => {
      render(<PhaseIndicator phase={phase} />);

      const badge = screen.getByTestId("phase-badge");
      expect(badge).toHaveTextContent(expectedLabel);
      expect(badge.className).toContain(expectedColor);
    }
  );

  it("shows 'Phase' label", () => {
    render(<PhaseIndicator phase={InterviewPhase.INTRO} />);

    expect(screen.getByText("Phase")).toBeInTheDocument();
  });
});
