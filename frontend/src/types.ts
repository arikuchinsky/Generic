export interface ToolUse {
  id: string;
  name: string;
  input: Record<string, unknown>;
  output?: string;
  status: "running" | "done" | "error";
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolUses: ToolUse[];
  timestamp: number;
}

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  messageCount: number;
  workingDirectory?: string;
}

export interface Settings {
  model: string;
  workingDirectory: string;
  autoApprove: boolean;
}

// ── Skill types ────────────────────────────────────────────

export interface Skill {
  id: string;
  name: string;
  icon: string;
  description: string;
  stages: string[];
}

export interface SkillResponse {
  type: "question" | "info" | "action" | "complete" | "revision_approval" | "error";
  content: string;
  confidence: number; // 1-4
  options: string[];
  stage: string;
  metadata: Record<string, unknown>;
}

export interface SkillSessionState {
  id: string;
  skillId: string;
  currentStage: string;
  stages: string[];
  messages: SkillMessage[];
  isProcessing: boolean;
  context: {
    approvedCount: number;
    pendingCount: number;
    revisionIndex: number;
  };
}

export interface SkillMessage {
  id: string;
  role: "user" | "skill";
  content: string;
  confidence?: number;
  type?: string;
  options?: string[];
  metadata?: Record<string, unknown>;
  timestamp: number;
}
