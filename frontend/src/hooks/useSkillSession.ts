import { useCallback, useState } from "react";
import { Skill, SkillSessionState, SkillMessage, SkillResponse } from "../types";

export function useSkillSession() {
  const [skillSession, setSkillSession] = useState<SkillSessionState | null>(null);
  const [availableSkills, setAvailableSkills] = useState<Skill[]>([]);

  const fetchSkills = useCallback(async () => {
    try {
      const res = await fetch("/api/skills");
      const data = await res.json();
      setAvailableSkills(data);
    } catch {
      // ignore
    }
  }, []);

  const startSkill = useCallback(async (skillId: string) => {
    try {
      const res = await fetch(`/api/skills/${skillId}/sessions`, {
        method: "POST",
      });
      const data = await res.json();
      if (data.error) {
        console.error(data.error);
        return;
      }

      const initialMsg: SkillMessage = {
        id: crypto.randomUUID(),
        role: "skill",
        content: data.initialPrompt.content,
        confidence: data.initialPrompt.confidence,
        type: data.initialPrompt.type,
        options: data.initialPrompt.options,
        metadata: data.initialPrompt.metadata,
        timestamp: Date.now(),
      };

      setSkillSession({
        id: data.id,
        skillId: data.skillId,
        currentStage: data.stage,
        stages: data.stages,
        messages: [initialMsg],
        isProcessing: false,
        context: { approvedCount: 0, pendingCount: 0, revisionIndex: 0 },
      });
    } catch (e) {
      console.error("Failed to start skill:", e);
    }
  }, []);

  const sendSkillMessage = useCallback(
    async (content: string, uploadedFilePath?: string) => {
      if (!skillSession) return;

      // Add user message
      const userMsg: SkillMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: Date.now(),
      };

      setSkillSession((prev) =>
        prev
          ? { ...prev, messages: [...prev.messages, userMsg], isProcessing: true }
          : prev
      );

      try {
        const formData = new FormData();
        formData.append("content", content);
        if (uploadedFilePath) {
          formData.append("uploaded_file_path", uploadedFilePath);
        }

        const res = await fetch(
          `/api/skills/sessions/${skillSession.id}/message`,
          { method: "POST", body: formData }
        );
        const data = await res.json();

        if (data.error) {
          const errMsg: SkillMessage = {
            id: crypto.randomUUID(),
            role: "skill",
            content: `Error: ${data.error}`,
            type: "error",
            confidence: 1,
            timestamp: Date.now(),
          };
          setSkillSession((prev) =>
            prev
              ? { ...prev, messages: [...prev.messages, errMsg], isProcessing: false }
              : prev
          );
          return;
        }

        const newMessages: SkillMessage[] = (data.responses || []).map(
          (r: SkillResponse) => ({
            id: crypto.randomUUID(),
            role: "skill" as const,
            content: r.content,
            confidence: r.confidence,
            type: r.type,
            options: r.options,
            metadata: r.metadata,
            timestamp: Date.now(),
          })
        );

        setSkillSession((prev) =>
          prev
            ? {
                ...prev,
                messages: [...prev.messages, ...newMessages],
                currentStage: data.stage,
                isProcessing: false,
                context: data.context || prev.context,
              }
            : prev
        );
      } catch (e) {
        console.error("Skill message failed:", e);
        setSkillSession((prev) =>
          prev ? { ...prev, isProcessing: false } : prev
        );
      }
    },
    [skillSession]
  );

  const uploadFile = useCallback(
    async (file: File): Promise<string | null> => {
      if (!skillSession) return null;

      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(
          `/api/skills/sessions/${skillSession.id}/upload`,
          { method: "POST", body: formData }
        );
        const data = await res.json();
        if (data.error) return null;
        return data.path;
      } catch {
        return null;
      }
    },
    [skillSession]
  );

  const closeSkill = useCallback(() => {
    setSkillSession(null);
  }, []);

  const downloadFile = useCallback(
    (fileKey: string) => {
      if (!skillSession) return;
      window.open(
        `/api/skills/sessions/${skillSession.id}/download/${fileKey}`,
        "_blank"
      );
    },
    [skillSession]
  );

  return {
    skillSession,
    availableSkills,
    fetchSkills,
    startSkill,
    sendSkillMessage,
    uploadFile,
    closeSkill,
    downloadFile,
  };
}
