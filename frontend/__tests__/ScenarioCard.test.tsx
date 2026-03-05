/**
 * Tests for ScenarioCard — rendering, difficulty badges, and click handling.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import ScenarioCard from "@/components/ScenarioCard";
import type { Scenario } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeScenario(overrides: Partial<Scenario> = {}): Scenario {
  return {
    id: "url-shortener",
    name: "Design a URL Shortener",
    description: "Design a URL shortening service like bit.ly.",
    archetype: "crud-metadata",
    difficulty: "easy",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests — Rendering
// ---------------------------------------------------------------------------

describe("ScenarioCard", () => {
  it("renders scenario name and description", () => {
    const scenario = makeScenario();
    render(<ScenarioCard scenario={scenario} onStart={jest.fn()} />);

    expect(screen.getByText("Design a URL Shortener")).toBeInTheDocument();
    expect(
      screen.getByText("Design a URL shortening service like bit.ly.")
    ).toBeInTheDocument();
  });

  it("renders Start Interview button", () => {
    render(<ScenarioCard scenario={makeScenario()} onStart={jest.fn()} />);

    const button = screen.getByRole("button", { name: /start interview/i });
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  // ---------------------------------------------------------------------------
  // Tests — Difficulty badge
  // ---------------------------------------------------------------------------

  it("renders easy difficulty badge with green styling", () => {
    render(
      <ScenarioCard
        scenario={makeScenario({ difficulty: "easy" })}
        onStart={jest.fn()}
      />
    );

    const badge = screen.getByTestId("difficulty-badge");
    expect(badge).toHaveTextContent("Easy");
    expect(badge.className).toContain("green");
  });

  it("renders medium difficulty badge with yellow styling", () => {
    render(
      <ScenarioCard
        scenario={makeScenario({ difficulty: "medium" })}
        onStart={jest.fn()}
      />
    );

    const badge = screen.getByTestId("difficulty-badge");
    expect(badge).toHaveTextContent("Medium");
    expect(badge.className).toContain("yellow");
  });

  it("renders hard difficulty badge with red styling", () => {
    render(
      <ScenarioCard
        scenario={makeScenario({ difficulty: "hard" })}
        onStart={jest.fn()}
      />
    );

    const badge = screen.getByTestId("difficulty-badge");
    expect(badge).toHaveTextContent("Hard");
    expect(badge.className).toContain("red");
  });

  // ---------------------------------------------------------------------------
  // Tests — Click handling
  // ---------------------------------------------------------------------------

  it("calls onStart with scenario id when button is clicked", () => {
    const onStart = jest.fn();
    render(
      <ScenarioCard
        scenario={makeScenario({ id: "payment-gateway" })}
        onStart={onStart}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /start interview/i }));
    expect(onStart).toHaveBeenCalledWith("payment-gateway");
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("disables button when disabled prop is true", () => {
    const onStart = jest.fn();
    render(
      <ScenarioCard
        scenario={makeScenario()}
        onStart={onStart}
        disabled={true}
      />
    );

    const button = screen.getByRole("button", { name: /start interview/i });
    expect(button).toBeDisabled();

    fireEvent.click(button);
    expect(onStart).not.toHaveBeenCalled();
  });
});
