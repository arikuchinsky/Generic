import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadAndPolish } from "../api/client";
import { FileDropzone } from "../components/FileDropzone";
import { PrePolishForm } from "../components/PrePolishForm";
import type { PrePolishOptions } from "../types";

export function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (options: PrePolishOptions) => {
    if (!file) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const { job_id } = await uploadAndPolish(file, options);
      navigate(`/processing/${job_id}`);
    } catch (e: any) {
      setError(e.message);
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      <div className="mb-8">
        <h2 className="text-2xl font-bold text-gray-900">Polish a Document</h2>
        <p className="text-gray-500 mt-1">
          Upload a legal document to automatically detect and fix formatting
          inconsistencies.
        </p>
      </div>

      <FileDropzone onFileSelect={setFile} />

      {file && <PrePolishForm onSubmit={handleSubmit} isSubmitting={isSubmitting} />}

      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}
