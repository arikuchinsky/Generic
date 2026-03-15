import { useState } from "react";
import { ToolUse } from "../types";

interface ToolUseBlockProps {
  toolUse: ToolUse;
}

const TOOL_ICONS: Record<string, string> = {
  Read: "📄",
  Write: "✏️",
  Edit: "🔧",
  Bash: "⚡",
  Glob: "🔍",
  Grep: "🔎",
  WebSearch: "🌐",
  WebFetch: "🌐",
  Agent: "🤖",
  NotebookEdit: "📓",
  TodoWrite: "📋",
};

function getToolSummary(toolUse: ToolUse): string {
  const { name, input } = toolUse;
  switch (name) {
    case "Read":
      return input.file_path as string || "file";
    case "Write":
      return input.file_path as string || "file";
    case "Edit":
      return input.file_path as string || "file";
    case "Bash":
      return (input.command as string || "").slice(0, 60);
    case "Glob":
      return input.pattern as string || "pattern";
    case "Grep":
      return input.pattern as string || "pattern";
    case "WebSearch":
      return input.query as string || "search";
    case "WebFetch":
      return (input.url as string || "").slice(0, 60);
    case "Agent":
      return input.description as string || "task";
    default:
      return "";
  }
}

export function ToolUseBlock({ toolUse }: ToolUseBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const icon = TOOL_ICONS[toolUse.name] || "🔨";
  const summary = getToolSummary(toolUse);

  return (
    <div className="tool-use-block">
      <div className="tool-use-header" onClick={() => setExpanded(!expanded)}>
        <span className={`tool-use-chevron ${expanded ? "expanded" : ""}`}>
          ▶
        </span>
        <span className="tool-use-name">
          <span className="tool-label">
            {icon} {toolUse.name}
          </span>
          {summary && (
            <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>
              {summary}
            </span>
          )}
        </span>
        <span className={`tool-use-status ${toolUse.status}`}>
          {toolUse.status === "running"
            ? "Running..."
            : toolUse.status === "done"
              ? "Done"
              : "Error"}
        </span>
      </div>

      {expanded && (
        <div className="tool-use-body">
          <div className="tool-use-section">
            <div className="tool-use-section-label">Input</div>
            <div className="tool-use-content">
              {formatToolInput(toolUse)}
            </div>
          </div>
          {toolUse.output && (
            <div className="tool-use-section">
              <div className="tool-use-section-label">Output</div>
              <div className="tool-use-content">{toolUse.output}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function formatToolInput(toolUse: ToolUse): string {
  const { name, input } = toolUse;

  switch (name) {
    case "Bash":
      return `$ ${input.command || ""}`;
    case "Read":
      return `File: ${input.file_path || ""}`;
    case "Write":
      return `File: ${input.file_path || ""}\n\n${(input.content as string || "").slice(0, 500)}${(input.content as string || "").length > 500 ? "\n..." : ""}`;
    case "Edit":
      return `File: ${input.file_path || ""}\n\n- ${(input.old_string as string || "").slice(0, 200)}\n+ ${(input.new_string as string || "").slice(0, 200)}`;
    case "Grep":
      return `Pattern: ${input.pattern || ""}\nPath: ${input.path || "."}`;
    case "Glob":
      return `Pattern: ${input.pattern || ""}`;
    default:
      return JSON.stringify(input, null, 2);
  }
}
