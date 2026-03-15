import { useCallback, useEffect, useState } from "react";
import { Session } from "../types";

interface SidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  workingDirectory: string;
  autoApprove: boolean;
  hasActiveSkill: boolean;
  onNewChat: () => void;
  onNewSkill: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onDirectoryChange: (dir: string) => void;
  onAutoApproveChange: (value: boolean) => void;
}

interface DirectoryEntry {
  name: string;
  path: string;
}

export function Sidebar({
  sessions,
  activeSessionId,
  workingDirectory,
  autoApprove,
  hasActiveSkill,
  onNewChat,
  onNewSkill,
  onSelectSession,
  onDeleteSession,
  onDirectoryChange,
  onAutoApproveChange,
}: SidebarProps) {
  const [showDirPicker, setShowDirPicker] = useState(false);
  const [currentPath, setCurrentPath] = useState(workingDirectory);
  const [directories, setDirectories] = useState<DirectoryEntry[]>([]);
  const [parentPath, setParentPath] = useState("");

  const fetchDirectories = useCallback(async (path: string) => {
    try {
      const res = await fetch(
        `/api/directories?path=${encodeURIComponent(path)}`
      );
      const data = await res.json();
      if (!data.error) {
        setCurrentPath(data.path);
        setParentPath(data.parent);
        setDirectories(data.directories || []);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (showDirPicker) {
      fetchDirectories(currentPath);
    }
  }, [showDirPicker]);

  const handleSelectDir = () => {
    onDirectoryChange(currentPath);
    setShowDirPicker(false);
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60000) return "Just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString();
  };

  const displayPath =
    workingDirectory.length > 30
      ? "..." + workingDirectory.slice(-27)
      : workingDirectory;

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={onNewChat}>
            + New Chat
          </button>
          <button className="new-skill-btn" onClick={onNewSkill}>
            ⚡ New Skill
          </button>
        </div>

        <div
          className="sidebar-directory"
          onClick={() => setShowDirPicker(true)}
          title={workingDirectory}
        >
          <span className="dir-icon">📁</span>
          <span className="dir-path">{displayPath || "Select directory"}</span>
        </div>

        <div className="session-list">
          {sessions.map((session) => (
            <div
              key={session.id}
              className={`session-item ${session.id === activeSessionId ? "active" : ""}`}
              onClick={() => onSelectSession(session.id)}
            >
              <div className="session-title">{session.title}</div>
              <div className="session-time">{formatTime(session.createdAt)}</div>
              <button
                className="session-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSession(session.id);
                }}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <div style={{ padding: "20px 12px", color: "var(--text-tertiary)", fontSize: "13px", textAlign: "center" }}>
              No conversations yet
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <label className="auto-approve-toggle">
            <div
              className={`toggle-switch ${autoApprove ? "active" : ""}`}
              onClick={() => onAutoApproveChange(!autoApprove)}
            />
            <span>Auto-approve</span>
          </label>
        </div>
      </aside>

      {showDirPicker && (
        <div className="modal-overlay" onClick={() => setShowDirPicker(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Select Working Directory</h3>
              <button
                className="modal-close"
                onClick={() => setShowDirPicker(false)}
              >
                ×
              </button>
            </div>
            <div className="modal-current-path">{currentPath}</div>
            <div className="modal-body">
              {parentPath && parentPath !== currentPath && (
                <div
                  className="dir-item"
                  onClick={() => fetchDirectories(parentPath)}
                >
                  <span className="dir-icon">⬆️</span>
                  <span>.. (parent)</span>
                </div>
              )}
              {directories.map((dir) => (
                <div
                  key={dir.path}
                  className="dir-item"
                  onClick={() => fetchDirectories(dir.path)}
                >
                  <span className="dir-icon">📁</span>
                  <span>{dir.name}</span>
                </div>
              ))}
              {directories.length === 0 && (
                <div style={{ padding: "20px", color: "var(--text-tertiary)", textAlign: "center", fontSize: "13px" }}>
                  No subdirectories
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button
                className="modal-btn secondary"
                onClick={() => setShowDirPicker(false)}
              >
                Cancel
              </button>
              <button className="modal-btn primary" onClick={handleSelectDir}>
                Select This Directory
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
