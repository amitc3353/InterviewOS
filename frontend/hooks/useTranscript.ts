/**
 * Custom hook for managing a WebSocket connection to the backend transcript stream.
 *
 * Connects to ws://backend/api/sessions/[id]/transcript and accumulates
 * TranscriptEvent messages for real-time display.
 */

import { useEffect, useRef, useState, useCallback } from "react";

import type { TranscriptEvent } from "@/lib/types";

/** Options for the useTranscript hook. */
export interface UseTranscriptOptions {
  /** Interview session ID. */
  sessionId: string;
  /** Base URL for the WebSocket server. Defaults to window.location based URL. */
  wsBaseUrl?: string;
}

/** Return value of the useTranscript hook. */
export interface UseTranscriptReturn {
  /** Accumulated transcript events in chronological order. */
  events: TranscriptEvent[];
  /** Whether the WebSocket connection is currently open. */
  isConnected: boolean;
  /** Error message if the connection failed. */
  error: string | null;
  /** Manually clear all transcript events. */
  clearEvents: () => void;
}

/**
 * Derive a WebSocket base URL from the current window location.
 * Converts http(s) to ws(s) and strips trailing slashes.
 */
function getDefaultWsBaseUrl(): string {
  if (typeof window === "undefined") return "ws://localhost:3000";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

/**
 * Connect to a real-time transcript WebSocket for the given session.
 *
 * 1. Opens a WebSocket to /api/sessions/:id/transcript
 * 2. Parses incoming JSON messages as TranscriptEvent
 * 3. Appends events to an ordered list
 * 4. Reconnects on unexpected close (with exponential backoff, max 3 retries)
 */
export function useTranscript({
  sessionId,
  wsBaseUrl,
}: UseTranscriptOptions): UseTranscriptReturn {
  const [events, setEvents] = useState<TranscriptEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef(false);

  const MAX_RETRIES = 3;

  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  useEffect(() => {
    unmountedRef.current = false;
    retryCountRef.current = 0;

    function connect() {
      if (unmountedRef.current) return;

      const base = wsBaseUrl ?? getDefaultWsBaseUrl();
      const url = `${base}/api/sessions/${sessionId}/transcript`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (unmountedRef.current) return;
        setIsConnected(true);
        setError(null);
        retryCountRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        if (unmountedRef.current) return;
        try {
          const data = JSON.parse(event.data) as TranscriptEvent;
          setEvents((prev) => [...prev, data]);
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        if (unmountedRef.current) return;
        setError("WebSocket connection error");
      };

      ws.onclose = (event: CloseEvent) => {
        if (unmountedRef.current) return;
        setIsConnected(false);
        wsRef.current = null;

        // Normal closure (code 1000) — do not reconnect
        if (event.code === 1000) return;

        // Retry with exponential backoff
        if (retryCountRef.current < MAX_RETRIES) {
          const delay = Math.min(1000 * 2 ** retryCountRef.current, 8000);
          retryCountRef.current += 1;
          retryTimerRef.current = setTimeout(connect, delay);
        } else {
          setError("Unable to connect to transcript stream");
        }
      };
    }

    connect();

    return () => {
      unmountedRef.current = true;
      if (retryTimerRef.current) {
        clearTimeout(retryTimerRef.current);
        retryTimerRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close(1000, "Component unmounted");
        wsRef.current = null;
      }
    };
  }, [sessionId, wsBaseUrl]);

  return { events, isConnected, error, clearEvents };
}
