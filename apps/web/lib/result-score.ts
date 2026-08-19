type SpecialtyEvidence = {
  specialty?: string;
  department?: string;
  rank?: number | null;
};

type ResultScoreInput = {
  score: number;
  score_breakdown?: Record<string, number>;
  has_direct_specialty_evidence?: boolean;
  specialty_evidence?: SpecialtyEvidence[];
};

const SCORE_WEIGHTS: Record<string, number> = {
  specialty: 35,
  public_capability: 25,
  geography: 20,
  freshness_completeness: 10,
  official_service: 10,
};

function recalculateScore(breakdown: Record<string, number>) {
  const weightedDimensions = Object.entries(SCORE_WEIGHTS).filter(([key]) => Number.isFinite(Number(breakdown[key])));
  if (!weightedDimensions.length) return null;
  return Number(weightedDimensions.reduce((total, [key, weight]) => (
    total + Math.max(0, Math.min(100, Number(breakdown[key]) || 0)) * weight / 100
  ), 0).toFixed(4));
}

export function getDisplayedResultScore(result: ResultScoreInput, options: { ignoreGeography?: boolean } = {}) {
  const breakdown = { ...(result.score_breakdown ?? {}) };
  const inferredEvidence = (result.specialty_evidence ?? []).some((item) => Boolean(
    item.specialty?.trim() || item.department?.trim(),
  ));
  const hasDirectSpecialtyEvidence = result.has_direct_specialty_evidence ?? inferredEvidence;
  if (options.ignoreGeography) breakdown.geography = 100;
  const score = options.ignoreGeography ? recalculateScore(breakdown) ?? result.score : result.score;
  return { breakdown, hasDirectSpecialtyEvidence, score };
}
