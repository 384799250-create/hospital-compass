import { describe, expect, it } from 'vitest';
import { getDisplayedResultScore } from '../lib/result-score';

describe('getDisplayedResultScore', () => {
  it('preserves the backend specialty baseline without direct evidence', () => {
    const result = getDisplayedResultScore({
      score: 71.916,
      score_breakdown: {
        specialty: 43.26,
        public_capability: 72.1,
        geography: 100,
        freshness_completeness: 87.5,
        official_service: 100,
      },
      specialty_evidence: [{ specialty: '', rank: 1271 }],
    });

    expect(result.hasDirectSpecialtyEvidence).toBe(false);
    expect(result.breakdown.specialty).toBe(43.26);
    expect(result.score).toBe(71.916);
  });
});
