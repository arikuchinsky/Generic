import { useCallback, useRef, useState } from "react";

interface InputAreaProps {
  onSend: (content: string) => void;
  onCancel: () => void;
  isStreaming: boolean;
  isConnected: boolean;
  model: string;
  onModelChange: (model: string) => void;
}

export function InputArea({
  onSend,
  onCancel,
  isStreaming,
  isConnected,
  model,
  onModelChange,
}: InputAreaProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [input, isStreaming, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-grow
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };

  return (
    <div className="input-area">
      <div className="input-container">
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            className="input-textarea"
            placeholder={
              isConnected
                ? "Ask Claude anything..."
                : "Connecting..."
            }
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            disabled={!isConnected}
            rows={1}
          />
          {isStreaming ? (
            <button className="send-btn stop" onClick={onCancel} title="Stop">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor">
                <rect x="2" y="2" width="10" height="10" rx="1" />
              </svg>
            </button>
          ) : (
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={!input.trim() || !isConnected}
              title="Send"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2L2 8.5L7 9.5L8.5 14.5L14 2Z" />
              </svg>
            </button>
          )}
        </div>
        <div className="input-controls">
          <select
            className="model-selector"
            value={model}
            onChange={(e) => onModelChange(e.target.value)}
          >
            <option value="sonnet">Sonnet</option>
            <option value="opus">Opus</option>
            <option value="haiku">Haiku</option>
          </select>
          <span className="input-hint">
            {isStreaming
              ? "Claude is thinking..."
              : "Enter to send, Shift+Enter for newline"}
          </span>
        </div>
      </div>
    </div>
  );
}
