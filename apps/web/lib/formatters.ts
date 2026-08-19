const LIKELIHOOD_LABELS: Record<string, string> = {
  high: '较高',
  medium: '中等',
  moderate: '中等',
  low: '较低',
  'very high': '很高',
  'very low': '很低',
};

export function formatLikelihood(value: string) {
  const normalized = value.trim().toLowerCase();
  return LIKELIHOOD_LABELS[normalized] ?? value;
}
