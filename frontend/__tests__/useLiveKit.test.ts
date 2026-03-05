/**
 * Tests for useLiveKit hook — token fetch, connection, mic toggle, disconnect.
 */

import { renderHook, act, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// Mock livekit-client
// ---------------------------------------------------------------------------

const mockConnect = jest.fn().mockResolvedValue(undefined);
const mockDisconnect = jest.fn();
const mockSetMicrophoneEnabled = jest.fn().mockResolvedValue(undefined);
const mockOn = jest.fn();

jest.mock("livekit-client", () => ({
  Room: jest.fn().mockImplementation(() => ({
    connect: mockConnect,
    disconnect: mockDisconnect,
    on: mockOn,
    localParticipant: {
      setMicrophoneEnabled: mockSetMicrophoneEnabled,
    },
  })),
  RoomEvent: {
    ConnectionStateChanged: "connectionStateChanged",
  },
  ConnectionState: {
    Disconnected: "disconnected",
    Connected: "connected",
    Connecting: "connecting",
    Reconnecting: "reconnecting",
  },
}));

// ---------------------------------------------------------------------------
// Mock API client
// ---------------------------------------------------------------------------

const mockGetSessionToken = jest.fn();

jest.mock("@/lib/api", () => ({
  api: {
    getSessionToken: (...args: unknown[]) => mockGetSessionToken(...args),
  },
}));

// Import after mocks
import { useLiveKit } from "@/hooks/useLiveKit";
import { ConnectionState } from "livekit-client";

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockConnect.mockReset().mockResolvedValue(undefined);
  mockDisconnect.mockReset();
  mockSetMicrophoneEnabled.mockReset().mockResolvedValue(undefined);
  mockOn.mockReset();
  mockGetSessionToken.mockReset();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useLiveKit", () => {
  it("starts in connecting state and fetches token", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "test-token",
      url: "wss://livekit.example.com",
    });

    const { result } = renderHook(() =>
      useLiveKit({ sessionId: "session-123" })
    );

    // Initially connecting
    expect(result.current.connectionState).toBe(ConnectionState.Connecting);
    expect(result.current.error).toBeNull();

    await waitFor(() => {
      expect(mockGetSessionToken).toHaveBeenCalledWith("session-123");
    });
  });

  it("connects to LiveKit room with fetched token and url", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "my-token",
      url: "wss://lk.test.io",
    });

    renderHook(() => useLiveKit({ sessionId: "s-1" }));

    await waitFor(() => {
      expect(mockConnect).toHaveBeenCalledWith("wss://lk.test.io", "my-token");
    });
  });

  it("enables microphone after connecting", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "t",
      url: "wss://lk.test.io",
    });

    const { result } = renderHook(() => useLiveKit({ sessionId: "s-2" }));

    await waitFor(() => {
      expect(mockSetMicrophoneEnabled).toHaveBeenCalledWith(true);
    });

    expect(result.current.isMicEnabled).toBe(true);
  });

  it("sets error when token fetch fails", async () => {
    mockGetSessionToken.mockRejectedValue(new Error("Token fetch failed"));

    const { result } = renderHook(() => useLiveKit({ sessionId: "bad-id" }));

    await waitFor(() => {
      expect(result.current.error).toBe("Token fetch failed");
    });

    expect(result.current.connectionState).toBe(ConnectionState.Disconnected);
  });

  it("sets error when room.connect fails", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "t",
      url: "wss://lk.test.io",
    });
    mockConnect.mockRejectedValue(new Error("WebSocket error"));

    const { result } = renderHook(() => useLiveKit({ sessionId: "s-3" }));

    await waitFor(() => {
      expect(result.current.error).toBe("WebSocket error");
    });
  });

  it("toggleMic flips mic state and calls setMicrophoneEnabled", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "t",
      url: "wss://lk.test.io",
    });

    const { result } = renderHook(() => useLiveKit({ sessionId: "s-4" }));

    // Wait for initial connection
    await waitFor(() => {
      expect(result.current.isMicEnabled).toBe(true);
    });

    mockSetMicrophoneEnabled.mockClear();

    await act(async () => {
      await result.current.toggleMic();
    });

    expect(mockSetMicrophoneEnabled).toHaveBeenCalledWith(false);
    expect(result.current.isMicEnabled).toBe(false);
  });

  it("disconnect calls room.disconnect", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "t",
      url: "wss://lk.test.io",
    });

    const { result } = renderHook(() => useLiveKit({ sessionId: "s-5" }));

    await waitFor(() => {
      expect(mockConnect).toHaveBeenCalled();
    });

    act(() => {
      result.current.disconnect();
    });

    expect(mockDisconnect).toHaveBeenCalled();
  });

  it("disconnects on unmount", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "t",
      url: "wss://lk.test.io",
    });

    const { unmount } = renderHook(() => useLiveKit({ sessionId: "s-6" }));

    await waitFor(() => {
      expect(mockConnect).toHaveBeenCalled();
    });

    unmount();

    expect(mockDisconnect).toHaveBeenCalled();
  });

  it("registers ConnectionStateChanged event listener", async () => {
    mockGetSessionToken.mockResolvedValue({
      token: "t",
      url: "wss://lk.test.io",
    });

    renderHook(() => useLiveKit({ sessionId: "s-7" }));

    expect(mockOn).toHaveBeenCalledWith(
      "connectionStateChanged",
      expect.any(Function)
    );
  });
});
