import type { ExampleInput, JobStatus, PrePolishOptions } from "../types";

const BASE_URL = "/api";

export async function uploadAndPolish(
  file: File,
  options: PrePolishOptions
): Promise<{ job_id: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append(
    "options",
    JSON.stringify({
      document_type: options.documentType,
      focus_areas: options.focusAreas,
      notes: options.notes,
    })
  );

  const res = await fetch(`${BASE_URL}/polish`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Upload failed");
  }

  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${BASE_URL}/polish/${jobId}/status`);
  if (!res.ok) throw new Error("Failed to get job status");
  return res.json();
}

export async function downloadPolished(jobId: string): Promise<Blob> {
  const res = await fetch(`${BASE_URL}/polish/${jobId}/download`);
  if (!res.ok) throw new Error("Failed to download file");
  return res.blob();
}

export async function submitExample(example: ExampleInput): Promise<void> {
  const res = await fetch(`${BASE_URL}/examples`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(example),
  });
  if (!res.ok) throw new Error("Failed to submit example");
}
