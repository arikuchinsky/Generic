import { useState } from "react";
import type { DocumentType, FocusArea, PrePolishOptions } from "../types";

const DOC_TYPES: { value: DocumentType; label: string }[] = [
  { value: "contract", label: "Contract" },
  { value: "agreement", label: "Agreement" },
  { value: "brief", label: "Brief" },
  { value: "memorandum", label: "Memorandum" },
  { value: "motion", label: "Motion" },
  { value: "pleading", label: "Pleading" },
  { value: "other", label: "Other" },
];

const FOCUS_AREAS: { value: FocusArea; label: string }[] = [
  { value: "headings", label: "Headings" },
  { value: "quotes", label: "Quotes" },
  { value: "lists", label: "Lists & Numbering" },
  { value: "spacing", label: "Spacing & Alignment" },
];

interface Props {
  onSubmit: (options: PrePolishOptions) => void;
  isSubmitting: boolean;
}

export function PrePolishForm({ onSubmit, isSubmitting }: Props) {
  const [docType, setDocType] = useState<DocumentType>("contract");
  const [focusAreas, setFocusAreas] = useState<FocusArea[]>([]);
  const [notes, setNotes] = useState("");

  const toggleFocus = (area: FocusArea) => {
    setFocusAreas((prev) =>
      prev.includes(area) ? prev.filter((a) => a !== area) : [...prev, area]
    );
  };

  return (
    <div className="space-y-6 mt-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Document Type
        </label>
        <select
          value={docType}
          onChange={(e) => setDocType(e.target.value as DocumentType)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {DOC_TYPES.map((dt) => (
            <option key={dt.value} value={dt.value}>
              {dt.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Focus Areas (optional)
        </label>
        <div className="flex flex-wrap gap-2">
          {FOCUS_AREAS.map((fa) => (
            <button
              key={fa.value}
              type="button"
              onClick={() => toggleFocus(fa.value)}
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                focusAreas.includes(fa.value)
                  ? "bg-blue-100 border-blue-300 text-blue-700"
                  : "bg-white border-gray-300 text-gray-600 hover:border-gray-400"
              }`}
            >
              {fa.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Special Notes (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any specific formatting concerns..."
          rows={2}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <button
        onClick={() =>
          onSubmit({
            documentType: docType,
            focusAreas,
            notes,
          })
        }
        disabled={isSubmitting}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium py-3 rounded-lg transition-colors"
      >
        {isSubmitting ? "Uploading..." : "Polish Document"}
      </button>
    </div>
  );
}
