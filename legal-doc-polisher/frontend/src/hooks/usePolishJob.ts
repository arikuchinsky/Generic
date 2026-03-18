import { useCallback, useEffect, useRef, useState } from "react";
import { getJobStatus } from "../api/client";
import type { JobStatus } from "../types";

export function usePolishJob(jobId: string | null) {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<number | null>(null);

  const poll = useCallback(async () => {
    if (!jobId) return;
    try {
      const s = await getJobStatus(jobId);
      setStatus(s);
      if (s.status === "complete" || s.status === "error") {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (e: any) {
      setError(e.message);
    }
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;
    poll();
    intervalRef.current = window.setInterval(poll, 2000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [jobId, poll]);

  return { status, error };
}
