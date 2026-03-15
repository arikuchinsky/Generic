import { useCallback, useEffect, useState } from "react";
import { Session, Settings } from "./types";
import { useWebSocket } from "./hooks/useWebSocket";
import { Sidebar } from "./components/Sidebar";
import { ChatArea } from "./components/ChatArea";
import { InputArea } from "./components/InputArea";

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [settings, setSettings] = useState<Settings>({
    model: "sonnet",
    workingDirectory: "",
    autoApprove: true,
  });

  const { messages, isStreaming, isConnected, sendMessage, cancel, clearMessages } =
    useWebSocket({
      sessionId: activeSessionId,
      onSessionUpdate: (claudeSessionId) => {
        // Store Claude's internal session ID for resume support
        console.log("Claude session:", claudeSessionId);
      },
    });

  // Fetch sessions on mount
  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const res = await fetch("/api/sessions");
      const data = await res.json();
      setSessions(data);
      // Set initial working directory from first session or default
      if (data.length > 0 && !settings.workingDirectory) {
        setSettings((s) => ({
          ...s,
          workingDirectory: data[0].workingDirectory || "",
        }));
      }
    } catch {
      // ignore
    }
  };

  const handleNewChat = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/sessions?working_directory=${encodeURIComponent(settings.workingDirectory)}`,
        { method: "POST" }
      );
      const data = await res.json();
      setSessions((prev) => [
        { id: data.id, title: data.title, createdAt: data.createdAt, messageCount: 0 },
        ...prev,
      ]);
      clearMessages();
      setActiveSessionId(data.id);
    } catch {
      // ignore
    }
  }, [settings.workingDirectory, clearMessages]);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id !== activeSessionId) {
        clearMessages();
        setActiveSessionId(id);
      }
    },
    [activeSessionId, clearMessages]
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await fetch(`/api/sessions/${id}`, { method: "DELETE" });
        setSessions((prev) => prev.filter((s) => s.id !== id));
        if (activeSessionId === id) {
          setActiveSessionId(null);
          clearMessages();
        }
      } catch {
        // ignore
      }
    },
    [activeSessionId, clearMessages]
  );

  const handleSend = useCallback(
    (content: string) => {
      // Auto-create session if none active
      if (!activeSessionId) {
        fetch(
          `/api/sessions?working_directory=${encodeURIComponent(settings.workingDirectory)}`,
          { method: "POST" }
        )
          .then((res) => res.json())
          .then((data) => {
            setSessions((prev) => [
              {
                id: data.id,
                title: data.title,
                createdAt: data.createdAt,
                messageCount: 0,
              },
              ...prev,
            ]);
            setActiveSessionId(data.id);
            // Wait for WebSocket to connect, then send
            setTimeout(() => {
              sendMessage(
                content,
                settings.model,
                settings.workingDirectory,
                settings.autoApprove
              );
            }, 500);
          });
        return;
      }
      sendMessage(
        content,
        settings.model,
        settings.workingDirectory,
        settings.autoApprove
      );

      // Update session title if first message
      const session = sessions.find((s) => s.id === activeSessionId);
      if (session && session.title === "New Chat") {
        setSessions((prev) =>
          prev.map((s) =>
            s.id === activeSessionId
              ? {
                  ...s,
                  title:
                    content.slice(0, 60) + (content.length > 60 ? "..." : ""),
                }
              : s
          )
        );
      }
    },
    [activeSessionId, settings, sendMessage, sessions]
  );

  return (
    <div className="app">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        workingDirectory={settings.workingDirectory}
        autoApprove={settings.autoApprove}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onDirectoryChange={(dir) =>
          setSettings((s) => ({ ...s, workingDirectory: dir }))
        }
        onAutoApproveChange={(val) =>
          setSettings((s) => ({ ...s, autoApprove: val }))
        }
      />
      <div className="main-area">
        <ChatArea messages={messages} isStreaming={isStreaming} />
        <InputArea
          onSend={handleSend}
          onCancel={cancel}
          isStreaming={isStreaming}
          isConnected={isConnected}
          model={settings.model}
          onModelChange={(model) =>
            setSettings((s) => ({ ...s, model }))
          }
        />
      </div>
    </div>
  );
}
