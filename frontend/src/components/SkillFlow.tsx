import { useCallback, useEffect, useRef, useState } from "react";
import { SkillSessionState } from "../types";
import { StageProgress } from "./StageProgress";
import { SkillMessage } from "./SkillMessage";
import { FileUpload } from "./FileUpload";

interface SkillFlowProps {
  session: SkillSessionState;
  onSendMessage: (content: string, uploadedFilePath?: string) => void;
  onUploadFile: (file: File) => Promise<string | null>;
  onClose: () => void;
  onDownload: (fileKey: string) => void;
}

export function SkillFlow({
  session,
  onSendMessage,
  onUploadFile,
  onClose,
  onDownload,
}: SkillFlowProps) {
  const [input, setInput] = useState("");
  const [pendingFilePath, setPendingFilePath] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session.messages]);

  const lastMessage = session.messages[session.messages.length - 1];
  const needsFileUpload = Boolean(
    lastMessage?.role === "skill" &&
    lastMessage.metadata?.input_type &&
    (lastMessage.metadata.input_type === "file" ||
      lastMessage.metadata.input_type === "file_or_choice")
  );

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed && !pendingFilePath) return;
    if (session.isProcessing) return;

    onSendMessage(trimmed, pendingFilePath || undefined);
    setInput("");
    setPendingFilePath(null);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, pendingFilePath, session.isProcessing, onSendMessage]);

  const handleFileUpload = useCallback(
    async (file: File) => {
      const path = await onUploadFile(file);
      if (path) {
        setPendingFilePath(path);
        // Auto-send with file
        onSendMessage(file.name, path);
      }
    },
    [onUploadFile, onSendMessage]
  );

  const handleOptionSelect = useCallback(
    (option: string) => {
      if (session.isProcessing) return;
      onSendMessage(option);
    },
    [session.isProcessing, onSendMessage]
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  const isComplete = lastMessage?.type === "complete";

  return (
    <div className="main-area skill-flow">
      {/* Header with stage progress */}
      <div className="skill-flow-header">
        <div className="skill-flow-title">
          <h2>Contract Review & Revise</h2>
          <button className="skill-flow-close" onClick={onClose} title="Close skill">
            ×
          </button>
        </div>
        <StageProgress
          stages={session.stages}
          currentStage={session.currentStage}
        />
        {(session.context.approvedCount > 0 || session.context.pendingCount > 0) && (
          <div className="skill-flow-stats">
            <span className="stat-badge approved">
              ✓ {session.context.approvedCount} approved
            </span>
            <span className="stat-badge pending">
              {session.context.pendingCount - session.context.revisionIndex} remaining
            </span>
          </div>
        )}
      </div>

      {/* Message thread */}
      <div className="chat-area">
        <div className="chat-messages">
          {session.messages.map((msg) => (
            <SkillMessage
              key={msg.id}
              message={msg}
              onOptionSelect={handleOptionSelect}
              onDownload={onDownload}
            />
          ))}
          {session.isProcessing && (
            <div className="message message-assistant">
              <div className="message-content">
                <span className="streaming-indicator">
                  <span className="streaming-dot" />
                  <span className="streaming-dot" />
                  <span className="streaming-dot" />
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input area */}
      {!isComplete && (
        <div className="input-area">
          <div className="input-container">
            {needsFileUpload && lastMessage && (
              <FileUpload
                accept={String(lastMessage.metadata?.accept ?? ".docx")}
                onUpload={handleFileUpload}
              />
            )}
            <div className="input-wrapper">
              <textarea
                ref={textareaRef}
                className="input-textarea"
                placeholder={
                  session.isProcessing
                    ? "Processing..."
                    : needsFileUpload
                      ? "Upload a file above, or type a response..."
                      : "Type your response..."
                }
                value={input}
                onChange={handleInput}
                onKeyDown={handleKeyDown}
                disabled={session.isProcessing}
                rows={1}
              />
              <button
                className="send-btn"
                onClick={handleSend}
                disabled={
                  session.isProcessing || (!input.trim() && !pendingFilePath)
                }
                title="Send"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M14 2L2 8.5L7 9.5L8.5 14.5L14 2Z" />
                </svg>
              </button>
            </div>
            {session.currentStage === "qa_session" && (
              <div className="input-controls">
                <span className="input-hint">
                  approve · reject · modify: &lt;text&gt; · alt 1/2 · done
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
