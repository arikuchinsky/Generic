import ReactMarkdown from "react-markdown";
import { Message } from "../types";
import { ToolUseBlock } from "./ToolUseBlock";
import { CodeBlock } from "./CodeBlock";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  if (message.role === "user") {
    return (
      <div className="message message-user">
        <div className="message-content">{message.content}</div>
      </div>
    );
  }

  return (
    <div className="message message-assistant">
      {message.toolUses.length > 0 && (
        <div className="tool-uses">
          {message.toolUses.map((toolUse) => (
            <ToolUseBlock key={toolUse.id} toolUse={toolUse} />
          ))}
        </div>
      )}
      {message.content && (
        <div className="message-content">
          <ReactMarkdown
            components={{
              code({ className, children, ...props }) {
                const match = /language-(\w+)/.exec(className || "");
                const codeString = String(children).replace(/\n$/, "");

                // Check if this is an inline code or block code
                const isBlock = codeString.includes("\n") || match;

                if (isBlock) {
                  return (
                    <CodeBlock language={match?.[1]}>
                      {codeString}
                    </CodeBlock>
                  );
                }

                return (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
          {isStreaming && (
            <span className="streaming-indicator">
              <span className="streaming-dot" />
              <span className="streaming-dot" />
              <span className="streaming-dot" />
            </span>
          )}
        </div>
      )}
      {!message.content && isStreaming && (
        <div className="message-content">
          <span className="streaming-indicator">
            <span className="streaming-dot" />
            <span className="streaming-dot" />
            <span className="streaming-dot" />
          </span>
        </div>
      )}
    </div>
  );
}
