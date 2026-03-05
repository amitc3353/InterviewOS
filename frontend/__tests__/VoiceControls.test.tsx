/**
 * Tests for VoiceControls — rendering, interaction, and connection state display.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";

// ---------------------------------------------------------------------------
// Mock livekit-client to avoid TextEncoder dependency in jsdom
// ---------------------------------------------------------------------------

jest.mock("livekit-client", () => ({
  ConnectionState: {
    Disconnected: "disconnected",
    Connected: "connected",
    Connecting: "connecting",
    Reconnecting: "reconnecting",
  },
}));

import { ConnectionState } from "livekit-client";
import VoiceControls from "@/components/VoiceControls";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderControls(
  overrides: Partial<Parameters<typeof VoiceControls>[0]> = {}
) {
  const props = {
    isMicEnabled: true,
    onToggleMic: jest.fn(),
    onEndInterview: jest.fn(),
    connectionState: ConnectionState.Connected,
    ...overrides,
  };
  render(<VoiceControls {...props} />);
  return props;
}

// ---------------------------------------------------------------------------
// Tests — Rendering
// ---------------------------------------------------------------------------

describe("VoiceControls", () => {
  it("renders mic toggle and end interview buttons", () => {
    renderControls();

    expect(screen.getByTestId("mic-toggle")).toBeInTheDocument();
    expect(screen.getByTestId("end-interview")).toBeInTheDocument();
  });

  it("shows 'Mute' label when mic is enabled", () => {
    renderControls({ isMicEnabled: true });

    expect(screen.getByTestId("mic-toggle")).toHaveTextContent("Mute");
  });

  it("shows 'Unmute' label when mic is disabled", () => {
    renderControls({ isMicEnabled: false });

    expect(screen.getByTestId("mic-toggle")).toHaveTextContent("Unmute");
  });

  // ---------------------------------------------------------------------------
  // Tests — Connection state indicator
  // ---------------------------------------------------------------------------

  it("shows green dot and 'Connected' when connected", () => {
    renderControls({ connectionState: ConnectionState.Connected });

    const dot = screen.getByTestId("connection-dot");
    expect(dot.className).toContain("green");
    expect(screen.getByTestId("connection-label")).toHaveTextContent(
      "Connected"
    );
  });

  it("shows yellow dot and 'Connecting...' when connecting", () => {
    renderControls({ connectionState: ConnectionState.Connecting });

    const dot = screen.getByTestId("connection-dot");
    expect(dot.className).toContain("yellow");
    expect(screen.getByTestId("connection-label")).toHaveTextContent(
      "Connecting..."
    );
  });

  it("shows red dot and 'Disconnected' when disconnected", () => {
    renderControls({ connectionState: ConnectionState.Disconnected });

    const dot = screen.getByTestId("connection-dot");
    expect(dot.className).toContain("red");
    expect(screen.getByTestId("connection-label")).toHaveTextContent(
      "Disconnected"
    );
  });

  // ---------------------------------------------------------------------------
  // Tests — Click handling
  // ---------------------------------------------------------------------------

  it("calls onToggleMic when mic button is clicked", () => {
    const props = renderControls();

    fireEvent.click(screen.getByTestId("mic-toggle"));
    expect(props.onToggleMic).toHaveBeenCalledTimes(1);
  });

  it("calls onEndInterview when end button is clicked", () => {
    const props = renderControls();

    fireEvent.click(screen.getByTestId("end-interview"));
    expect(props.onEndInterview).toHaveBeenCalledTimes(1);
  });

  // ---------------------------------------------------------------------------
  // Tests — Disabled state
  // ---------------------------------------------------------------------------

  it("disables buttons when not connected", () => {
    renderControls({ connectionState: ConnectionState.Disconnected });

    expect(screen.getByTestId("mic-toggle")).toBeDisabled();
    expect(screen.getByTestId("end-interview")).toBeDisabled();
  });

  it("enables buttons when connected", () => {
    renderControls({ connectionState: ConnectionState.Connected });

    expect(screen.getByTestId("mic-toggle")).not.toBeDisabled();
    expect(screen.getByTestId("end-interview")).not.toBeDisabled();
  });
});
