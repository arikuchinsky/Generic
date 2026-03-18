import type { JobStatus } from "../types";

const STEPS = [
  { key: "profiling", label: "Analyzing Styles" },
  { key: "deterministic_pass", label: "Running Format Rules" },
  { key: "rendering", label: "Rendering Pages" },
  { key: "vision_pass", label: "AI Vision Analysis" },
  { key: "applying_fixes", label: "Applying Fixes" },
  { key: "complete", label: "Done" },
];

interface Props {
  status: JobStatus;
}

export function ProgressTracker({ status }: Props) {
  const currentIdx = STEPS.findIndex((s) => s.key === status.status);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="mb-6">
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>{status.current_step}</span>
          <span>{status.progress_pct}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-blue-600 h-2 rounded-full transition-all duration-500"
            style={{ width: `${status.progress_pct}%` }}
          />
        </div>
      </div>

      <div className="space-y-3">
        {STEPS.map((step, idx) => {
          const isDone = idx < currentIdx;
          const isCurrent = idx === currentIdx;
          return (
            <div key={step.key} className="flex items-center gap-3">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                  isDone
                    ? "bg-green-500 text-white"
                    : isCurrent
                    ? "bg-blue-500 text-white animate-pulse"
                    : "bg-gray-200 text-gray-500"
                }`}
              >
                {isDone ? "\u2713" : idx + 1}
              </div>
              <span
                className={`text-sm ${
                  isDone
                    ? "text-green-700"
                    : isCurrent
                    ? "text-blue-700 font-medium"
                    : "text-gray-400"
                }`}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
