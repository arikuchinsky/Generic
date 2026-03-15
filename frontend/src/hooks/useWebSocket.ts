import { useCallback, useEffect, useRef, useState } from "react";
import { Message, ToolUse } from "../types";

interface UseWebSocketOptions {
  sessionId: string | null;
  onSessionUpdate?: (claudeSessionId: string) => void;
}

export function useWebSocket({ sessionId, onSessionUpdate }: UseWebSocketOptions) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const currentAssistantRef = useRef<{ content: string; toolUses: ToolUse[] }>({
    content: "",
    toolUses: [],
  });
  const contentBlocksRef = useRef<Map<number, { type: string; id?: string; name?: string; input_json?: string }>>(new Map());

  const connect = useCallback(() => {
    if (!sessionId) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.hostname;
    const port = window.location.port || "5173";
    const ws = new WebSocket(`${protocol}//${host}:${port}/ws/${sessionId}`);

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => {
      setIsConnected(false);
      setIsStreaming(false);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleEvent(data);
    };

    wsRef.current = ws;
  }, [sessionId]);

  const handleEvent = useCallback((event: Record<string, unknown>) => {
    const type = event.type as string;

    if (type === "content_block_start") {
      const index = event.index as number;
      const block = event.content_block as Record<string, unknown>;
      contentBlocksRef.current.set(index, {
        type: block.type as string,
        id: block.id as string | undefined,
        name: block.name as string | undefined,
        input_json: "",
      });

      if (block.type === "tool_use") {
        const toolUse: ToolUse = {
          id: block.id as string,
          name: block.name as string,
          input: {},
          status: "running",
        };
        currentAssistantRef.current.toolUses = [
          ...currentAssistantRef.current.toolUses,
          toolUse,
        ];
        updateAssistantMessage();
      }
    } else if (type === "content_block_delta") {
      const index = event.index as number;
      const delta = event.delta as Record<string, unknown>;
      const block = contentBlocksRef.current.get(index);

      if (delta.type === "text_delta") {
        currentAssistantRef.current.content += delta.text as string;
        updateAssistantMessage();
      } else if (delta.type === "input_json_delta" && block) {
        block.input_json = (block.input_json || "") + (delta.partial_json as string);
      }
    } else if (type === "content_block_stop") {
      const index = event.index as number;
      const block = contentBlocksRef.current.get(index);
      if (block?.type === "tool_use" && block.input_json) {
        try {
          const input = JSON.parse(block.input_json);
          const toolUses = currentAssistantRef.current.toolUses;
          const tu = toolUses.find((t) => t.id === block.id);
          if (tu) {
            tu.input = input;
            updateAssistantMessage();
          }
        } catch {
          // partial json, ignore
        }
      }
    } else if (type === "result") {
      // Final result from Claude CLI
      const result = event.result as string;
      const cost = event.cost_usd as number | undefined;
      const sid = event.session_id as string;

      if (result && !currentAssistantRef.current.content) {
        currentAssistantRef.current.content = result;
      }

      // Mark all tool uses as done
      currentAssistantRef.current.toolUses.forEach((tu) => {
        if (tu.status === "running") tu.status = "done";
      });

      if (cost !== undefined) {
        currentAssistantRef.current.content +=
          `\n\n---\n*Cost: $${cost.toFixed(4)}*`;
      }

      updateAssistantMessage();

      if (sid && onSessionUpdate) {
        onSessionUpdate(sid);
      }
    } else if (type === "assistant") {
      // Full assistant message (stream-json format)
      const msg = event.message as Record<string, unknown>;
      const content = msg?.content as Array<Record<string, unknown>>;
      if (content) {
        for (const block of content) {
          if (block.type === "text") {
            if (!currentAssistantRef.current.content) {
              currentAssistantRef.current.content = block.text as string;
            }
          } else if (block.type === "tool_use") {
            const existing = currentAssistantRef.current.toolUses.find(
              (t) => t.id === block.id
            );
            if (!existing) {
              currentAssistantRef.current.toolUses.push({
                id: block.id as string,
                name: block.name as string,
                input: block.input as Record<string, unknown>,
                status: "done",
              });
            }
          } else if (block.type === "tool_result") {
            const toolId = block.tool_use_id as string;
            const tu = currentAssistantRef.current.toolUses.find(
              (t) => t.id === toolId
            );
            if (tu) {
              const resultContent = block.content as string | Array<Record<string, unknown>>;
              if (typeof resultContent === "string") {
                tu.output = resultContent;
              } else if (Array.isArray(resultContent)) {
                tu.output = resultContent
                  .filter((c) => c.type === "text")
                  .map((c) => c.text)
                  .join("\n");
              }
              tu.status = block.is_error ? "error" : "done";
            }
          }
        }
        updateAssistantMessage();
      }
    } else if (type === "done") {
      setIsStreaming(false);
      contentBlocksRef.current.clear();
    } else if (type === "cancelled") {
      setIsStreaming(false);
      contentBlocksRef.current.clear();
    } else if (type === "error") {
      const errData = event.data as Record<string, unknown>;
      const errMsg = (errData?.message as string) || "Unknown error";
      currentAssistantRef.current.content += `\n\n**Error:** ${errMsg}`;
      updateAssistantMessage();
      setIsStreaming(false);
    }
  }, [onSessionUpdate]);

  const updateAssistantMessage = useCallback(() => {
    setMessages((prev) => {
      const lastMsg = prev[prev.length - 1];
      const assistantMsg: Message = {
        id: lastMsg?.role === "assistant" ? lastMsg.id : crypto.randomUUID(),
        role: "assistant",
        content: currentAssistantRef.current.content,
        toolUses: [...currentAssistantRef.current.toolUses],
        timestamp: Date.now(),
      };

      if (lastMsg?.role === "assistant") {
        return [...prev.slice(0, -1), assistantMsg];
      }
      return [...prev, assistantMsg];
    });
  }, []);

  const sendMessage = useCallback(
    (
      content: string,
      model: string,
      workingDir: string,
      autoApprove: boolean
    ) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

      // Add user message
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        toolUses: [],
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMsg]);

      // Reset assistant state
      currentAssistantRef.current = { content: "", toolUses: [] };
      contentBlocksRef.current.clear();
      setIsStreaming(true);

      wsRef.current.send(
        JSON.stringify({
          type: "prompt",
          content,
          model,
          workingDir,
          autoApprove,
        })
      );
    },
    []
  );

  const cancel = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "cancel" }));
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    currentAssistantRef.current = { content: "", toolUses: [] };
    contentBlocksRef.current.clear();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    messages,
    isStreaming,
    isConnected,
    sendMessage,
    cancel,
    clearMessages,
  };
}
