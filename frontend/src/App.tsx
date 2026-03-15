import { useCallback, useEffect, useState } from "react";
import { Session, Settings } from "./types";
import { useWebSocket } from "./hooks/useWebSocket";
import { useSkillSession } from "./hooks/useSkillSession";
import { Sidebar } from "./components/Sidebar";
import { ChatArea } from "./components/ChatArea";
import { InputArea } from "./components/InputArea";
import { SkillLauncher } from "./components/SkillLauncher";
import { SkillFlow } from "./components/SkillFlow";

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [showSkillLauncher, setShowSkillLauncher] = useState(false);
  const [settings, setSettings] = useState<Settings>({
    model: "sonnet",
    workingDirectory: "",
    autoApprove: true,
  });

  const { messages, isStreaming, isConnected, sendMessage, cancel, clearMessages } =
    useWebSocket({
      sessionId: activeSessionId,
      onSessionUpdate: (claudeSessionId) => {
        console.log("Claude session:", claudeSessionId);
      },
    });

  const {
    skillSession,
    availableSkills,
    fetchSkills,
    startSkill,
    sendSkillMessage,
    uploadFile,
    closeSkill,
    downloadFile,
  } = useSkillSession();

  // Fetch sessions and skills on mount
  useEffect(() => {
    fetchSessions();
    fetchSkills();
  }, [fetchSkills]);

  const fetchSessions = async () => {
    try {
      const res = await fetch("/api/sessions");
      const data = await res.json();
      setSessions(data);
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
    // Close any active skill
    closeSkill();
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
  }, [settings.workingDirectory, clearMessages, closeSkill]);

  const handleNewSkill = useCallback(() => {
    setShowSkillLauncher(true);
  }, []);

  const handleSelectSkill = useCallback(
    (skillId: string) => {
      setShowSkillLauncher(false);
      setActiveSessionId(null);
      clearMessages();
      startSkill(skillId);
    },
    [clearMessages, startSkill]
  );

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id !== activeSessionId) {
        closeSkill();
        clearMessages();
        setActiveSessionId(id);
      }
    },
    [activeSessionId, clearMessages, closeSkill]
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
        hasActiveSkill={!!skillSession}
        onNewChat={handleNewChat}
        onNewSkill={handleNewSkill}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
        onDirectoryChange={(dir) =>
          setSettings((s) => ({ ...s, workingDirectory: dir }))
        }
        onAutoApproveChange={(val) =>
          setSettings((s) => ({ ...s, autoApprove: val }))
        }
      />

      {/* Skill flow takes over the main area when active */}
      {skillSession ? (
        <SkillFlow
          session={skillSession}
          onSendMessage={sendSkillMessage}
          onUploadFile={uploadFile}
          onClose={closeSkill}
          onDownload={downloadFile}
        />
      ) : (
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
      )}

      {showSkillLauncher && (
        <SkillLauncher
          skills={availableSkills}
          onSelectSkill={handleSelectSkill}
          onClose={() => setShowSkillLauncher(false)}
        />
      )}
    </div>
  );
}
