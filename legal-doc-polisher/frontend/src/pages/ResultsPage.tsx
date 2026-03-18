import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { downloadPolished, getJobStatus } from "../api/client";
import { ChangeReport } from "../components/ChangeReport";
import { ExampleSubmitDialog } from "../components/ExampleSubmitDialog";
import type { PolishReport } from "../types";

export function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [report, setReport] = useState<PolishReport | null>(null);
  const [showDialog, setShowDialog] = useState(false);

  useEffect(() => {
    if (jobId) {
      getJobStatus(jobId).then((s) => {
        if (s.report) setReport(s.report);
      });
    }
  }, [jobId]);

  const handleDownload = async () => {
    if (!jobId) return;
    const blob = await downloadPolished(jobId);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `polished_${report?.original_filename || "document.docx"}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!report) {
    return <div className="text-center text-gray-500 py-12">Loading results...</div>;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Results</h2>
        <div className="flex gap-3">
          <button
            onClick={() => setShowDialog(true)}
            className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Report Missed Issue
          </button>
          <button
            onClick={handleDownload}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Download Polished Document
          </button>
        </div>
      </div>

      <ChangeReport report={report} />

      <ExampleSubmitDialog
        isOpen={showDialog}
        onClose={() => setShowDialog(false)}
      />
    </div>
  );
}
