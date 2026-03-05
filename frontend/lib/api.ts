/**
 * Typed fetch client for the InterviewOS backend REST API.
 */

import type {
  InterviewSession,
  SessionState,
  ScoringResult,
  Scenario,
  LiveKitTokenResponse,
  ApiError,
} from "./types";
import { STATIC_SCENARIOS } from "./scenarios";

const DEFAULT_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Options for creating the API client. */
export interface ApiClientOptions {
  baseUrl?: string;
  headers?: Record<string, string>;
}

/** Typed error thrown by the API client. */
export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body?: ApiError
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

/**
 * Create a typed API client for the InterviewOS backend.
 *
 * Usage:
 *   const api = createApiClient({ baseUrl: "http://localhost:8000" });
 *   const session = await api.getSession("abc-123");
 */
export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
  const defaultHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  async function request<T>(
    method: string,
    path: string,
    body?: unknown
  ): Promise<T> {
    const url = `${baseUrl}${path}`;

    const init: RequestInit = {
      method,
      headers: { ...defaultHeaders },
    };

    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }

    const response = await fetch(url, init);

    if (!response.ok) {
      let errorBody: ApiError | undefined;
      try {
        errorBody = (await response.json()) as ApiError;
      } catch {
        // Response body was not JSON
      }
      throw new ApiClientError(
        errorBody?.error ?? `Request failed with status ${response.status}`,
        response.status,
        errorBody
      );
    }

    return (await response.json()) as T;
  }

  return {
    /** Create a new interview session. */
    createSession(scenario: string): Promise<InterviewSession> {
      return request<InterviewSession>("POST", "/api/sessions", { scenario });
    },

    /** Get an existing session by ID. */
    getSession(sessionId: string): Promise<InterviewSession> {
      return request<InterviewSession>("GET", `/api/sessions/${sessionId}`);
    },

    /** Get current session state. */
    getSessionState(sessionId: string): Promise<SessionState> {
      return request<SessionState>("GET", `/api/sessions/${sessionId}/state`);
    },

    /** Get scoring results for a completed session. */
    getScore(sessionId: string): Promise<ScoringResult> {
      return request<ScoringResult>("GET", `/api/sessions/${sessionId}/score`);
    },

    /** Fetch LiveKit room token for a session. */
    getSessionToken(sessionId: string): Promise<LiveKitTokenResponse> {
      return request<LiveKitTokenResponse>(
        "GET",
        `/api/sessions/${sessionId}/token`
      );
    },

    /** Health check endpoint. */
    healthCheck(): Promise<{ status: string }> {
      return request<{ status: string }>("GET", "/api/health");
    },

    /** Fetch available scenarios, falling back to static data. */
    async getScenarios(): Promise<Scenario[]> {
      try {
        return await request<Scenario[]>("GET", "/api/scenarios");
      } catch {
        return STATIC_SCENARIOS;
      }
    },
  };
}

/** Default API client instance. */
export const api = createApiClient();
