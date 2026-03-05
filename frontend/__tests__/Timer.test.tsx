/**
 * Tests for Timer component — elapsed time formatting and display.
 */

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import Timer, { formatElapsed } from "@/components/Timer";

// ---------------------------------------------------------------------------
// Tests — formatElapsed utility
// ---------------------------------------------------------------------------

describe("formatElapsed", () => {
  it("formats 0 seconds as 00:00", () => {
    expect(formatElapsed(0)).toBe("00:00");
  });

  it("formats 65 seconds as 01:05", () => {
    expect(formatElapsed(65)).toBe("01:05");
  });

  it("formats 3600 seconds as 01:00:00", () => {
    expect(formatElapsed(3600)).toBe("01:00:00");
  });

  it("formats 3661 seconds as 01:01:01", () => {
    expect(formatElapsed(3661)).toBe("01:01:01");
  });

  it("treats negative values as 00:00", () => {
    expect(formatElapsed(-5)).toBe("00:00");
  });

  it("floors fractional seconds", () => {
    expect(formatElapsed(90.9)).toBe("01:30");
  });
});

// ---------------------------------------------------------------------------
// Tests — Timer rendering
// ---------------------------------------------------------------------------

describe("Timer", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("renders timer container", () => {
    const now = new Date().toISOString();
    render(<Timer startedAt={now} />);

    expect(screen.getByTestId("timer")).toBeInTheDocument();
  });

  it("shows 'Elapsed' label", () => {
    const now = new Date().toISOString();
    render(<Timer startedAt={now} />);

    expect(screen.getByText("Elapsed")).toBeInTheDocument();
  });

  it("displays elapsed time from startedAt", () => {
    // Start 5 minutes ago
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    render(<Timer startedAt={fiveMinutesAgo} />);

    expect(screen.getByTestId("timer")).toHaveTextContent("05:00");
  });

  it("shows 00:00 when startedAt is now", () => {
    const now = new Date().toISOString();
    render(<Timer startedAt={now} />);

    expect(screen.getByTestId("timer")).toHaveTextContent("00:00");
  });
});
