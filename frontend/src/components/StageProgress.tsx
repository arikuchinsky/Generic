interface StageProgressProps {
  stages: string[];
  currentStage: string;
}

const STAGE_LABELS: Record<string, string> = {
  upload: "Upload",
  playbook: "Playbook",
  party: "Party",
  scope: "Scope",
  initial_review: "Review",
  qa_session: "Q&A",
  revisions: "Revisions",
  redline: "Redline",
  summary: "Summary",
};

export function StageProgress({ stages, currentStage }: StageProgressProps) {
  const currentIdx = stages.indexOf(currentStage);

  return (
    <div className="stage-progress">
      {stages.map((stage, i) => {
        let status: "done" | "active" | "pending" = "pending";
        if (i < currentIdx) status = "done";
        else if (i === currentIdx) status = "active";

        return (
          <div key={stage} className={`stage-item ${status}`}>
            <div className="stage-dot">
              {status === "done" ? "✓" : i + 1}
            </div>
            <span className="stage-label">
              {STAGE_LABELS[stage] || stage}
            </span>
            {i < stages.length - 1 && <div className="stage-connector" />}
          </div>
        );
      })}
    </div>
  );
}
