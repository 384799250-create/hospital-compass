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

export type PendingCandidate = {
  name: string;
  city: string;
  direction: string;
  reason: string;
  placeholder?: boolean;
};

export type AIMatchResponse = MatchResponse & {
  ai: AIMetadata;
  pending_candidates: PendingCandidate[];
};

export type RealtimeHospitalResult = {
  id: string;
  name: string;
  city: string;
  score: number;
  score_reasons: string[];
  sources: { title: string; url: string; snippet: string; fetched_at: string }[];
  source_urls: string[];
  fetched_at: string;
  registration_url: string | null;
  department?: string;
  address?: string;
  reason?: string;
};

export type RealtimeSearchResponse = {
  status: 'OK' | 'EMERGENCY' | 'SEARCH_UNAVAILABLE' | 'NO_RESULTS';
  directions: string[];
  scope: 'district' | 'city' | 'province' | 'national';
  results: RealtimeHospitalResult[];
  sources: string[];
  fetched_at: string | null;
};

export type RealtimeHospitalDetail = {
  id: string;
  name: string;
  city: string;
  address?: string;
  introduction: string | null;
  departments: string[];
  doctors: string[];
  registration_url: string | null;
  sources: RealtimeHospitalResult['sources'];
  fetched_at: string;
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

export async function realtimeSearchHospitals(input: {
  query: string;
  location: { province: string; city: string; district: string };
  scope: RealtimeSearchResponse['scope'];
  ai_consent: boolean;
}): Promise<RealtimeSearchResponse> {
  const response = await fetch('/v1/realtime-hospital-search', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<RealtimeSearchResponse>;
}

export async function getRealtimeHospitalDetail(id: string): Promise<RealtimeHospitalDetail> {
  const response = await fetch(`/v1/realtime-hospitals/${encodeURIComponent(id)}`);
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<RealtimeHospitalDetail>;
}
