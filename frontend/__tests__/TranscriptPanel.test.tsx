/**
 * Tests for TranscriptPanel component — message rendering, phase dividers,
 * constraint highlighting, auto-scroll, connection status.
 */

import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { InterviewPhase } from "@/lib/types";
import type { TranscriptEvent } from "@/lib/types";
import TranscriptPanel from "@/components/TranscriptPanel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEvent(overrides: Partial<TranscriptEvent> = {}): TranscriptEvent {
  return {
    speaker: "interviewer",
    text: "Welcome to the interview.",
    timestamp: 1700000000,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TranscriptPanel", () => {
  it("renders the transcript panel container", () => {
    render(<TranscriptPanel events={[]} isConnected={false} />);
    expect(screen.getByTestId("transcript-panel")).toBeInTheDocument();
  });

  it("shows empty state when no events", () => {
    render(<TranscriptPanel events={[]} isConnected={false} />);
    expect(screen.getByTestId("transcript-empty")).toHaveTextContent(
      "Transcript will appear here during the interview."
    );
  });

  it("does not show empty state when events exist", () => {
    render(
      <TranscriptPanel events={[makeEvent()]} isConnected={true} />
    );
    expect(screen.queryByTestId("transcript-empty")).not.toBeInTheDocument();
  });

  it("renders messages with correct speaker labels", () => {
    const events: TranscriptEvent[] = [
      makeEvent({ speaker: "interviewer", text: "Hello" }),
      makeEvent({ speaker: "user", text: "Hi there", timestamp: 1700000005 }),
    ];

    render(<TranscriptPanel events={events} isConnected={true} />);

    const labels = screen.getAllByTestId("speaker-label");
    expect(labels[0]).toHaveTextContent("Interviewer");
    expect(labels[1]).toHaveTextContent("You");
  });

  it("renders message text", () => {
    const events: TranscriptEvent[] = [
      makeEvent({ text: "Tell me about your system design." }),
    ];

    render(<TranscriptPanel events={events} isConnected={true} />);

    expect(
      screen.getByText("Tell me about your system design.")
    ).toBeInTheDocument();
  });

  it("shows interviewer messages aligned left and user messages aligned right", () => {
    const events: TranscriptEvent[] = [
      makeEvent({ speaker: "interviewer", text: "Question" }),
      makeEvent({ speaker: "user", text: "Answer", timestamp: 1700000005 }),
    ];

    render(<TranscriptPanel events={events} isConnected={true} />);

    const messages = screen.getAllByTestId("transcript-message");
    expect(messages[0].className).toContain("justify-start");
    expect(messages[1].className).toContain("justify-end");
  });

  it("renders phase transition dividers", () => {
    const events: TranscriptEvent[] = [
      makeEvent({ phase: InterviewPhase.INTRO }),
      makeEvent({
        speaker: "user",
        text: "Hi",
        timestamp: 1700000005,
        phase: InterviewPhase.SCOPE,
      }),
    ];

    render(<TranscriptPanel events={events} isConnected={true} />);

    const dividers = screen.getAllByTestId("phase-divider");
    expect(dividers).toHaveLength(2);
    expect(dividers[0]).toHaveTextContent("Intro");
    expect(dividers[1]).toHaveTextContent("Scope");
  });

  it("does not render divider when phase stays the same", () => {
    const events: TranscriptEvent[] = [
      makeEvent({ phase: InterviewPhase.INTRO }),
      makeEvent({
        text: "Still in intro",
        timestamp: 1700000005,
        phase: InterviewPhase.INTRO,
      }),
    ];

    render(<TranscriptPanel events={events} isConnected={true} />);

    const dividers = screen.getAllByTestId("phase-divider");
    // Only 1 divider for the initial phase, not 2
    expect(dividers).toHaveLength(1);
  });

  it("highlights locked constraints in monospace", () => {
    const constraints = { "write-through cache": "selected by candidate" };
    const events: TranscriptEvent[] = [
      makeEvent({
        text: "You mentioned a write-through cache earlier.",
      }),
    ];

    render(
      <TranscriptPanel
        events={events}
        isConnected={true}
        lockedConstraints={constraints}
      />
    );

    const highlights = screen.getAllByTestId("constraint-highlight");
    expect(highlights).toHaveLength(1);
    expect(highlights[0]).toHaveTextContent("write-through cache");
    expect(highlights[0].className).toContain("font-mono");
  });

  it("shows green connection dot when connected", () => {
    render(<TranscriptPanel events={[]} isConnected={true} />);

    const dot = screen.getByTestId("connection-dot");
    expect(dot.className).toContain("bg-green-500");
  });

  it("shows gray connection dot when disconnected", () => {
    render(<TranscriptPanel events={[]} isConnected={false} />);

    const dot = screen.getByTestId("connection-dot");
    expect(dot.className).toContain("bg-gray-600");
  });

  it("renders the Transcript heading", () => {
    render(<TranscriptPanel events={[]} isConnected={false} />);
    expect(screen.getByText("Transcript")).toBeInTheDocument();
  });

  it("renders multiple messages in order", () => {
    const events: TranscriptEvent[] = [
      makeEvent({ speaker: "interviewer", text: "First message" }),
      makeEvent({ speaker: "user", text: "Second message", timestamp: 1700000005 }),
      makeEvent({ speaker: "interviewer", text: "Third message", timestamp: 1700000010 }),
    ];

    render(<TranscriptPanel events={events} isConnected={true} />);

    const messages = screen.getAllByTestId("transcript-message");
    expect(messages).toHaveLength(3);
  });

  it("does not crash with empty locked constraints", () => {
    const events: TranscriptEvent[] = [
      makeEvent({ text: "Some message without constraints" }),
    ];

    render(
      <TranscriptPanel
        events={events}
        isConnected={true}
        lockedConstraints={{}}
      />
    );

    expect(screen.queryAllByTestId("constraint-highlight")).toHaveLength(0);
    expect(
      screen.getByText("Some message without constraints")
    ).toBeInTheDocument();
  });

  it("auto-scrolls container when events update", () => {
    const scrollTopSetter = jest.fn();
    const mockScrollHeight = 500;

    // Mock scrollRef via Element.prototype
    const originalScrollTo = Element.prototype.scrollTo;
    Object.defineProperty(HTMLDivElement.prototype, "scrollHeight", {
      configurable: true,
      get() {
        return mockScrollHeight;
      },
    });
    Object.defineProperty(HTMLDivElement.prototype, "scrollTop", {
      configurable: true,
      set(val: number) {
        scrollTopSetter(val);
      },
      get() {
        return 0;
      },
    });

    const events1 = [makeEvent({ text: "First" })];
    const { rerender } = render(
      <TranscriptPanel events={events1} isConnected={true} />
    );

    const events2 = [
      ...events1,
      makeEvent({ text: "Second", timestamp: 1700000005 }),
    ];
    rerender(<TranscriptPanel events={events2} isConnected={true} />);

    // scrollTop should have been set to scrollHeight
    expect(scrollTopSetter).toHaveBeenCalledWith(mockScrollHeight);

    // Cleanup
    Element.prototype.scrollTo = originalScrollTo;
  });
});
