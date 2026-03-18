import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ProgressTracker } from "../components/ProgressTracker";
import { usePolishJob } from "../hooks/usePolishJob";

export function ProcessingPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { status, error } = usePolishJob(jobId || null);

  useEffect(() => {
    if (status?.status === "complete") {
      navigate(`/results/${jobId}`);
    }
  }, [status, jobId, navigate]);

  if (error) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700">
        <h3 className="font-medium">Error</h3>
        <p className="text-sm mt-1">{error}</p>
      </div>
    );
  }

  if (!status) {
    return (
      <div className="text-center text-gray-500 py-12">Loading...</div>
    );
  }

  if (status.status === "error") {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700">
        <h3 className="font-medium">Processing Error</h3>
        <p className="text-sm mt-1">
          {status.error_message || "An unexpected error occurred"}
        </p>
        <button
          onClick={() => navigate("/")}
          className="mt-4 text-sm text-blue-600 hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">
        Polishing Your Document
      </h2>
      <ProgressTracker status={status} />
    </div>
  );
}
