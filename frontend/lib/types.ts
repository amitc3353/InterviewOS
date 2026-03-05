/**
 * TypeScript interfaces mirroring backend Python models.
 * Mirrors: backend/models/session.py and backend/models/scorecard.py
 */

/** Interview phases — matches InterviewPhase enum in backend/models/session.py */
export enum InterviewPhase {
  INTRO = "intro",
  SCOPE = "scope",
  ARCHITECTURE = "architecture",
  DEEP_DIVE = "deep_dive",
  FAILURE = "failure",
  TRADEOFFS = "tradeoffs",
  WRAP = "wrap",
}

/** Conversation message — mirrors Message dataclass */
export interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string; // ISO 8601
}

/** Current session state — mirrors SessionState dataclass */
export interface SessionState {
  session_id: string;
  phase: InterviewPhase;
  locked_constraints: Record<string, string>;
  conversation_history: Message[];
  phase_turn_count: number;
  total_turn_count: number;
  elapsed_seconds: number;
}

/** Complete interview session — mirrors InterviewSession dataclass */
export interface InterviewSession {
  session_id: string;
  scenario: string;
  phase: InterviewPhase;
  locked_constraints: Record<string, string>;
  conversation_history: Message[];
  transcript: Record<string, unknown>[];
  metadata: Record<string, unknown>;
  scorecard: ScoringResult | null;
  session_start_time: string; // ISO 8601
  elapsed_seconds: number;
  total_turns: number;
}

/** Score for a single evaluation dimension — mirrors DimensionScore */
export interface DimensionScore {
  dimension: string;
  score: number; // 1-5
  label: string;
  rationale: string;
  strengths: string[];
  gaps: string[];
}

/** Complete scoring result — mirrors InterviewScorecard */
export interface ScoringResult {
  session_id: string;
  scenario: string;
  dimensions: Record<string, DimensionScore>;
  overall_score: number;
  hire_signal: "Strong Yes" | "Lean Yes" | "Lean No" | "No";
  narrative: string;
  locked_constraints: Record<string, string>;
  total_turns: number;
  elapsed_minutes: number;
  generated_at: string; // ISO 8601
}

/** Difficulty level for interview scenarios */
export type ScenarioDifficulty = "easy" | "medium" | "hard";

/** Scenario summary for landing page display */
export interface Scenario {
  id: string;
  name: string;
  description: string;
  archetype: string;
  difficulty: ScenarioDifficulty;
}

/** LiveKit connection token response from GET /api/sessions/:id/token */
export interface LiveKitTokenResponse {
  token: string;
  url: string;
}

/** API error response */
export interface ApiError {
  error: string;
  detail?: string;
}
