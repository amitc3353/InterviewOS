/**
 * Voice controls — mic toggle and end interview button.
 */

"use client";

import { ConnectionState } from "livekit-client";

export interface VoiceControlsProps {
  /** Whether the microphone is currently enabled. */
  isMicEnabled: boolean;
  /** Toggle microphone on/off. */
  onToggleMic: () => void;
  /** End the interview and disconnect. */
  onEndInterview: () => void;
  /** Current LiveKit connection state. */
  connectionState: ConnectionState;
}

export default function VoiceControls({
  isMicEnabled,
  onToggleMic,
  onEndInterview,
  connectionState,
}: VoiceControlsProps) {
  const isConnected = connectionState === ConnectionState.Connected;
  const isConnecting = connectionState === ConnectionState.Connecting;

  return (
    <div
      className="flex flex-col gap-3 rounded-lg border border-gray-800 bg-gray-900/50 p-4"
      data-testid="voice-controls"
    >
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            isConnected
              ? "bg-green-500"
              : isConnecting
                ? "bg-yellow-500 animate-pulse"
                : "bg-red-500"
          }`}
          data-testid="connection-dot"
        />
        <span className="text-xs text-gray-400" data-testid="connection-label">
          {isConnected
            ? "Connected"
            : isConnecting
              ? "Connecting..."
              : "Disconnected"}
        </span>
      </div>

      <button
        onClick={onToggleMic}
        disabled={!isConnected}
        className={`flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-medium transition-colors ${
          isMicEnabled
            ? "bg-blue-600 text-white hover:bg-blue-500"
            : "bg-red-600 text-white hover:bg-red-500"
        } disabled:cursor-not-allowed disabled:opacity-50`}
        data-testid="mic-toggle"
      >
        {isMicEnabled ? "Mute" : "Unmute"}
      </button>

      <button
        onClick={onEndInterview}
        disabled={!isConnected}
        className="rounded-md border border-red-700 bg-red-900/30 px-4 py-2.5 text-sm font-medium text-red-400 transition-colors hover:bg-red-900/60 disabled:cursor-not-allowed disabled:opacity-50"
        data-testid="end-interview"
      >
        End Interview
      </button>
    </div>
  );
}
