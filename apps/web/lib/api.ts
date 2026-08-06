export type MatchResult = {
  id: string;
  name: string;
  city: string;
  demo_label: string;
  score: number;
  specialties: string[];
  score_reasons: string[];
  source_date: string;
};

export type MatchResponse = {
  emergency: boolean;
  directions: string[];
  score_version: string;
  results: MatchResult[];
};

export type AIMetadata = {
  used: boolean;
  summary: string | null;
  directions: string[];
  fallback: boolean;
};

export type AIMatchResponse = MatchResponse & {
  ai: AIMetadata;
};

type MatchInput = {
  query: string;
  city?: string;
  priority: 'overall' | 'specialty' | 'convenience';
};

export class MatchApiError extends Error {
  constructor(public readonly status: number) {
    super(`Matching request failed with status ${status}`);
  }
}

async function postMatch<Response>(path: string, input: MatchInput | (MatchInput & { ai_consent: true })): Promise<Response> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    throw new MatchApiError(response.status);
  }

  return response.json() as Promise<Response>;
}

export function matchHospitals(input: MatchInput): Promise<MatchResponse> {
  return postMatch<MatchResponse>('/v1/matches', input);
}

export function aiMatchHospitals(input: MatchInput & { ai_consent: true }): Promise<AIMatchResponse> {
  return postMatch<AIMatchResponse>('/v1/ai-matches', input);
}
