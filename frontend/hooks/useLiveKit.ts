/**
 * Custom hook for managing LiveKit room connection and audio track state.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import {
  Room,
  RoomEvent,
  ConnectionState,
} from "livekit-client";
import { api } from "@/lib/api";

/** Options for the useLiveKit hook. */
export interface UseLiveKitOptions {
  /** Interview session ID used to fetch the LiveKit room token. */
  sessionId: string;
}

/** Return value of the useLiveKit hook. */
export interface UseLiveKitReturn {
  /** Current WebRTC connection state. */
  connectionState: ConnectionState;
  /** Whether the local microphone is currently enabled. */
  isMicEnabled: boolean;
  /** Toggle the local microphone on/off. */
  toggleMic: () => Promise<void>;
  /** Disconnect from the LiveKit room. */
  disconnect: () => void;
  /** Error message if connection or token fetch failed. */
  error: string | null;
}

/**
 * Connect to a LiveKit room for the given interview session.
 *
 * 1. Fetches a room token from GET /api/sessions/:id/token
 * 2. Connects to the LiveKit room
 * 3. Enables the local microphone
 * 4. Exposes controls for mute toggle and disconnect
 */
export function useLiveKit({ sessionId }: UseLiveKitOptions): UseLiveKitReturn {
  const roomRef = useRef<Room | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    ConnectionState.Disconnected
  );
  const [isMicEnabled, setIsMicEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const room = new Room();
    roomRef.current = room;

    room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
      setConnectionState(state);
    });

    async function connect() {
      try {
        setConnectionState(ConnectionState.Connecting);
        const { token, url } = await api.getSessionToken(sessionId);
        await room.connect(url, token);
        await room.localParticipant.setMicrophoneEnabled(true);
        setIsMicEnabled(true);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to connect to room"
        );
        setConnectionState(ConnectionState.Disconnected);
      }
    }

    connect();

    return () => {
      room.disconnect();
      roomRef.current = null;
    };
  }, [sessionId]);

  const toggleMic = useCallback(async () => {
    const room = roomRef.current;
    if (!room?.localParticipant) return;
    const next = !isMicEnabled;
    await room.localParticipant.setMicrophoneEnabled(next);
    setIsMicEnabled(next);
  }, [isMicEnabled]);

  const disconnect = useCallback(() => {
    roomRef.current?.disconnect();
  }, []);

  return { connectionState, isMicEnabled, toggleMic, disconnect, error };
}
