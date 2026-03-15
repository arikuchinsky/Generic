interface ConfidenceBadgeProps {
  level: number;
}

const CONFIDENCE_CONFIG: Record<
  number,
  { label: string; className: string }
> = {
  1: { label: "Minor", className: "confidence-1" },
  2: { label: "Moderate", className: "confidence-2" },
  3: { label: "Significant", className: "confidence-3" },
  4: { label: "Critical", className: "confidence-4" },
};

export function ConfidenceBadge({ level }: ConfidenceBadgeProps) {
  const config = CONFIDENCE_CONFIG[level] || CONFIDENCE_CONFIG[2];

  return (
    <span className={`confidence-badge ${config.className}`}>
      {level} — {config.label}
    </span>
  );
}
