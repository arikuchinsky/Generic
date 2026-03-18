export type DocumentType =
  | "contract"
  | "brief"
  | "memorandum"
  | "agreement"
  | "motion"
  | "pleading"
  | "other";

export type FocusArea = "headings" | "quotes" | "lists" | "spacing";

export type Severity = "minor" | "moderate" | "major";

export interface PrePolishOptions {
  documentType: DocumentType;
  focusAreas: FocusArea[];
  notes: string;
}

export interface JobStatus {
  job_id: string;
  status: string;
  progress_pct: number;
  current_step: string;
  report: PolishReport | null;
  error_message: string | null;
}

export interface Change {
  change_id: string;
  category: string;
  location: string;
  description: string;
  severity: Severity;
  source: "deterministic" | "vision";
}

export interface PolishReport {
  job_id: string;
  original_filename: string;
  total_changes: number;
  changes_by_category: Record<string, number>;
  changes: Change[];
  processing_time_seconds: number;
  deterministic_pass_time: number;
  vision_pass_time: number;
}

export interface ExampleInput {
  category: string;
  description: string;
  before_context?: string;
  after_context?: string;
  document_type?: string;
}
