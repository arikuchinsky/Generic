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
