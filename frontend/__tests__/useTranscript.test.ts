/**
 * Tests for useTranscript hook — WebSocket connection, event accumulation, reconnection.
 */

import { renderHook, act, waitFor } from "@testing-library/react";

import type { TranscriptEvent } from "@/lib/types";

// ---------------------------------------------------------------------------
// Mock WebSocket
// ---------------------------------------------------------------------------

type WSHandler = (event: unknown) => void;

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  onopen: WSHandler | null = null;
  onmessage: WSHandler | null = null;
  onerror: WSHandler | null = null;
  onclose: WSHandler | null = null;
  closeCalled = false;
  closeCode?: number;
  closeReason?: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close(code?: number, reason?: string) {
    this.closeCalled = true;
    this.closeCode = code;
    this.closeReason = reason;
  }

  /** Simulate server sending a message. */
  simulateMessage(data: TranscriptEvent) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  /** Simulate the connection opening. */
  simulateOpen() {
    if (this.onopen) this.onopen({});
  }

  /** Simulate an error. */
  simulateError() {
    if (this.onerror) this.onerror({});
  }

  /** Simulate the connection closing. */
  simulateClose(code: number = 1000) {
    if (this.onclose) this.onclose({ code } as CloseEvent);
  }

  static reset() {
    MockWebSocket.instances = [];
  }
}

// Replace global WebSocket
const OriginalWebSocket = global.WebSocket;
beforeAll(() => {
  (global as unknown as Record<string, unknown>).WebSocket = MockWebSocket;
});
afterAll(() => {
  (global as unknown as Record<string, unknown>).WebSocket = OriginalWebSocket;
});
beforeEach(() => {
  MockWebSocket.reset();
  jest.useFakeTimers();
});
afterEach(() => {
  jest.useRealTimers();
});

// Import after mock is set up
import { useTranscript } from "@/hooks/useTranscript";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getLatestWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1];
}

function makeEvent(overrides: Partial<TranscriptEvent> = {}): TranscriptEvent {
  return {
    speaker: "interviewer",
    text: "Hello, welcome to the interview.",
    timestamp: 1700000000,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useTranscript", () => {
  it("connects to the correct WebSocket URL", () => {
    renderHook(() =>
      useTranscript({ sessionId: "sess-123", wsBaseUrl: "ws://localhost:3000" })
    );

    expect(getLatestWs().url).toBe(
      "ws://localhost:3000/api/sessions/sess-123/transcript"
    );
  });

  it("starts with empty events, not connected, no error", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-1", wsBaseUrl: "ws://localhost:3000" })
    );

    expect(result.current.events).toEqual([]);
    expect(result.current.isConnected).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("sets isConnected to true when WebSocket opens", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-2", wsBaseUrl: "ws://localhost:3000" })
    );

    act(() => {
      getLatestWs().simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("accumulates transcript events from WebSocket messages", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-3", wsBaseUrl: "ws://localhost:3000" })
    );

    act(() => {
      getLatestWs().simulateOpen();
    });

    const event1 = makeEvent({ speaker: "interviewer", text: "Hello" });
    const event2 = makeEvent({ speaker: "user", text: "Hi there", timestamp: 1700000005 });

    act(() => {
      getLatestWs().simulateMessage(event1);
    });
    act(() => {
      getLatestWs().simulateMessage(event2);
    });

    expect(result.current.events).toHaveLength(2);
    expect(result.current.events[0]).toEqual(event1);
    expect(result.current.events[1]).toEqual(event2);
  });

  it("ignores malformed messages", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-4", wsBaseUrl: "ws://localhost:3000" })
    );

    act(() => {
      getLatestWs().simulateOpen();
    });

    // Send invalid JSON
    act(() => {
      if (getLatestWs().onmessage) {
        getLatestWs().onmessage!({ data: "not valid json{{{" } as MessageEvent);
      }
    });

    expect(result.current.events).toHaveLength(0);
  });

  it("sets error on WebSocket error event", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-5", wsBaseUrl: "ws://localhost:3000" })
    );

    act(() => {
      getLatestWs().simulateError();
    });

    expect(result.current.error).toBe("WebSocket connection error");
  });

  it("sets isConnected to false on close", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-6", wsBaseUrl: "ws://localhost:3000" })
    );

    act(() => {
      getLatestWs().simulateOpen();
    });
    expect(result.current.isConnected).toBe(true);

    act(() => {
      getLatestWs().simulateClose(1000);
    });
    expect(result.current.isConnected).toBe(false);
  });

  it("does not reconnect on normal close (code 1000)", () => {
    renderHook(() =>
      useTranscript({ sessionId: "sess-7", wsBaseUrl: "ws://localhost:3000" })
    );

    const initialCount = MockWebSocket.instances.length;

    act(() => {
      getLatestWs().simulateClose(1000);
    });

    act(() => {
      jest.advanceTimersByTime(10000);
    });

    expect(MockWebSocket.instances.length).toBe(initialCount);
  });

  it("retries connection on abnormal close with backoff", () => {
    renderHook(() =>
      useTranscript({ sessionId: "sess-8", wsBaseUrl: "ws://localhost:3000" })
    );

    const initialCount = MockWebSocket.instances.length;

    // Abnormal close (e.g., code 1006)
    act(() => {
      getLatestWs().simulateClose(1006);
    });

    // First retry after 1000ms
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    expect(MockWebSocket.instances.length).toBe(initialCount + 1);
  });

  it("sets error after max retries exhausted", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-9", wsBaseUrl: "ws://localhost:3000" })
    );

    // 3 retries with exponential backoff: 1s, 2s, 4s
    for (let i = 0; i < 3; i++) {
      act(() => {
        getLatestWs().simulateClose(1006);
      });
      act(() => {
        jest.advanceTimersByTime(Math.min(1000 * 2 ** i, 8000));
      });
    }

    // 4th close — no more retries
    act(() => {
      getLatestWs().simulateClose(1006);
    });
    act(() => {
      jest.advanceTimersByTime(10000);
    });

    expect(result.current.error).toBe("Unable to connect to transcript stream");
  });

  it("clearEvents empties the event list", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-10", wsBaseUrl: "ws://localhost:3000" })
    );

    act(() => {
      getLatestWs().simulateOpen();
      getLatestWs().simulateMessage(makeEvent());
    });

    expect(result.current.events).toHaveLength(1);

    act(() => {
      result.current.clearEvents();
    });

    expect(result.current.events).toHaveLength(0);
  });

  it("closes WebSocket on unmount", () => {
    const { unmount } = renderHook(() =>
      useTranscript({ sessionId: "sess-11", wsBaseUrl: "ws://localhost:3000" })
    );

    const ws = getLatestWs();

    unmount();

    expect(ws.closeCalled).toBe(true);
    expect(ws.closeCode).toBe(1000);
  });

  it("resets retry count after successful reconnection", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-12", wsBaseUrl: "ws://localhost:3000" })
    );

    // Abnormal close
    act(() => {
      getLatestWs().simulateClose(1006);
    });

    // Retry after 1s
    act(() => {
      jest.advanceTimersByTime(1000);
    });

    // Reconnection succeeds
    act(() => {
      getLatestWs().simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.error).toBeNull();
  });

  it("includes phase data in accumulated events", () => {
    const { result } = renderHook(() =>
      useTranscript({ sessionId: "sess-13", wsBaseUrl: "ws://localhost:3000" })
    );

    act(() => {
      getLatestWs().simulateOpen();
    });

    const event = makeEvent({ phase: "scope" as unknown as undefined });

    act(() => {
      getLatestWs().simulateMessage(event as unknown as TranscriptEvent);
    });

    expect(result.current.events[0]).toEqual(event);
  });
});
