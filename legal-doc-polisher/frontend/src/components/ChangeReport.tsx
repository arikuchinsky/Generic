import { useState } from "react";
import type { Change, PolishReport } from "../types";

interface Props {
  report: PolishReport;
}

const SEVERITY_COLORS = {
  minor: "bg-yellow-100 text-yellow-800",
  moderate: "bg-orange-100 text-orange-800",
  major: "bg-red-100 text-red-800",
};

const CATEGORY_LABELS: Record<string, string> = {
  heading_style: "Heading Style",
  quote_style: "Smart Quotes",
  list_labels: "List Labels",
  paragraph_format: "Paragraph Format",
  cross_references: "Cross References",
  definition_format: "Definitions",
  signature_block: "Signature Blocks",
  header_footer: "Headers/Footers",
  other: "Other",
};

export function ChangeReport({ report }: Props) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const categories = Object.entries(report.changes_by_category).sort(
    (a, b) => b[1] - a[1]
  );

  const changesByCategory: Record<string, Change[]> = {};
  for (const change of report.changes) {
    if (!changesByCategory[change.category]) {
      changesByCategory[change.category] = [];
    }
    changesByCategory[change.category].push(change);
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold mb-4">Polish Summary</h2>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-3xl font-bold text-blue-600">
              {report.total_changes}
            </div>
            <div className="text-sm text-gray-500">Total Changes</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-green-600">
              {report.deterministic_pass_time.toFixed(1)}s
            </div>
            <div className="text-sm text-gray-500">Rules Pass</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-purple-600">
              {report.vision_pass_time.toFixed(1)}s
            </div>
            <div className="text-sm text-gray-500">Vision Pass</div>
          </div>
        </div>
      </div>

      {/* Category breakdown */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold mb-4">Changes by Category</h2>
        <div className="space-y-2">
          {categories.map(([cat, count]) => (
            <div key={cat}>
              <button
                onClick={() =>
                  setExpandedCategory(expandedCategory === cat ? null : cat)
                }
                className="w-full flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-sm">
                    {CATEGORY_LABELS[cat] || cat}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-500">{count} changes</span>
                  <span className="text-gray-400">
                    {expandedCategory === cat ? "\u25B2" : "\u25BC"}
                  </span>
                </div>
              </button>

              {expandedCategory === cat && changesByCategory[cat] && (
                <div className="ml-4 mt-1 space-y-2">
                  {changesByCategory[cat].map((change) => (
                    <div
                      key={change.change_id}
                      className="p-3 bg-gray-50 rounded-lg text-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-gray-500 text-xs">
                            {change.location}
                          </div>
                          <div className="mt-1">{change.description}</div>
                        </div>
                        <div className="flex gap-1 shrink-0">
                          <span
                            className={`px-2 py-0.5 rounded text-xs ${
                              SEVERITY_COLORS[change.severity]
                            }`}
                          >
                            {change.severity}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-xs ${
                              change.source === "vision"
                                ? "bg-purple-100 text-purple-800"
                                : "bg-blue-100 text-blue-800"
                            }`}
                          >
                            {change.source}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
