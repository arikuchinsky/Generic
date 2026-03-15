import ReactMarkdown from "react-markdown";
import { SkillMessage as SkillMessageType } from "../types";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { CodeBlock } from "./CodeBlock";

interface SkillMessageProps {
  message: SkillMessageType;
  onOptionSelect?: (option: string) => void;
  onDownload?: (fileKey: string) => void;
}

export function SkillMessage({ message, onOptionSelect, onDownload }: SkillMessageProps) {
  if (message.role === "user") {
    return (
      <div className="message message-user">
        <div className="message-content">{message.content}</div>
      </div>
    );
  }

  const isRevision = message.type === "revision_approval";
  const isComplete = message.type === "complete";
  const downloads = message.metadata?.downloads as Record<string, string> | undefined;

  return (
    <div className={`message message-assistant skill-message ${isRevision ? "revision-message" : ""}`}>
      {message.confidence !== undefined && message.confidence > 0 && (
        <div className="skill-message-header">
          <ConfidenceBadge level={message.confidence} />
        </div>
      )}

      <div className="message-content">
        <ReactMarkdown
          components={{
            code({ className, children, ...props }) {
              const match = /language-(\w+)/.exec(className || "");
              const codeString = String(children).replace(/\n$/, "");
              const isBlock = codeString.includes("\n") || match;
              if (isBlock) {
                return <CodeBlock language={match?.[1]}>{codeString}</CodeBlock>;
              }
              return <code className={className} {...props}>{children}</code>;
            },
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>

      {message.options && message.options.length > 0 && (
        <div className="skill-options">
          {message.options.map((option) => (
            <button
              key={option}
              className="skill-option-btn"
              onClick={() => onOptionSelect?.(option)}
            >
              {option}
            </button>
          ))}
        </div>
      )}

      {isComplete && downloads && (
        <div className="skill-downloads">
          {Object.entries(downloads).map(([key]) => (
            <button
              key={key}
              className="skill-download-btn"
              onClick={() => onDownload?.(key)}
            >
              ⬇ Download {key}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
