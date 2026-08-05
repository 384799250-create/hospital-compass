export type MatchResult = {
  name: string;
  city: string;
  demo_label: string;
  score: number;
  specialties?: string[];
  score_reasons?: string[];
  source_date?: string;
};

export type MatchResponse = {
  emergency: boolean;
  directions: string[];
  score_version: string;
  results: MatchResult[];
};

export class MatchApiError extends Error {
  constructor(public readonly status: number) {
    super(`Matching request failed with status ${status}`);
  }
}

export async function matchHospitals(input: {
  query: string;
  city?: string;
  priority: 'overall' | 'specialty' | 'convenience';
}): Promise<MatchResponse> {
  const response = await fetch('/v1/matches', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    throw new MatchApiError(response.status);
  }

  return response.json() as Promise<MatchResponse>;
}
