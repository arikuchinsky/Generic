import { useCallback, useState } from "react";

interface Props {
  onFileSelect: (file: File) => void;
}

export function FileDropzone({ onFileSelect }: Props) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && file.name.toLowerCase().endsWith(".docx")) {
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [onFileSelect]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [onFileSelect]
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
        isDragging
          ? "border-blue-500 bg-blue-50"
          : selectedFile
          ? "border-green-400 bg-green-50"
          : "border-gray-300 hover:border-gray-400 bg-white"
      }`}
      onClick={() => document.getElementById("file-input")?.click()}
    >
      <input
        id="file-input"
        type="file"
        accept=".docx"
        className="hidden"
        onChange={handleFileInput}
      />
      {selectedFile ? (
        <div>
          <div className="text-green-600 text-lg font-medium">
            {selectedFile.name}
          </div>
          <div className="text-sm text-gray-500 mt-1">
            {(selectedFile.size / 1024).toFixed(0)} KB — Click to change
          </div>
        </div>
      ) : (
        <div>
          <div className="text-gray-500 text-lg">
            Drop your .docx file here or click to browse
          </div>
          <div className="text-sm text-gray-400 mt-1">
            Only .docx files are supported
          </div>
        </div>
      )}
    </div>
  );
}
