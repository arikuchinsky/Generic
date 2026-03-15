import { useCallback, useState } from "react";

interface FileUploadProps {
  accept?: string;
  onUpload: (file: File) => Promise<void>;
  label?: string;
}

export function FileUpload({
  accept = ".docx",
  onUpload,
  label = "Drop your file here or click to browse",
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadedName, setUploadedName] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setUploading(true);
      try {
        await onUpload(file);
        setUploadedName(file.name);
      } finally {
        setUploading(false);
      }
    },
    [onUpload]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile]
  );

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleClick = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) handleFile(file);
    };
    input.click();
  };

  if (uploadedName) {
    return (
      <div className="file-upload uploaded">
        <span className="file-upload-icon">✓</span>
        <span className="file-upload-name">{uploadedName}</span>
      </div>
    );
  }

  return (
    <div
      className={`file-upload ${isDragging ? "dragging" : ""} ${uploading ? "uploading" : ""}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={handleClick}
    >
      <span className="file-upload-icon">
        {uploading ? "⏳" : "📄"}
      </span>
      <span className="file-upload-label">
        {uploading ? "Uploading..." : label}
      </span>
      <span className="file-upload-hint">
        Accepts: {accept}
      </span>
    </div>
  );
}
