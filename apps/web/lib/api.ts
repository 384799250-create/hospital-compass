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
  tier?: string;
  specialties?: string[];
  score: number;
  score_reasons: string[];
  sources: { title: string; url: string; snippet: string; fetched_at: string }[];
  source_urls: string[];
  fetched_at: string;
  registration_url: string | null;
  official_website_url?: string | null;
  wechat_appointment?: string | null;
  department?: string;
  address?: string;
  reason?: string;
  core_advantages?: string;
  match_reason?: string;
  evidence_status?: string;
  score_breakdown?: Record<string, number>;
  has_direct_specialty_evidence?: boolean;
  specialty_evidence?: Array<{
    hospital: string;
    city: string;
    specialty?: string;
    department?: string;
    strength_level?: string;
    diagnosis_scope?: string;
    rank?: number | null;
    tier?: string;
    year?: number | null;
    source?: string;
    verification_status?: string;
    ranking_name?: string;
    ranking_source_name?: string;
    ranking_scope?: string;
    scope?: string;
  }>;
};

export type RealtimeSearchResponse = {
  status: 'OK' | 'EMERGENCY' | 'SEARCH_UNAVAILABLE' | 'NO_RESULTS';
  directions: string[];
  scope: 'district' | 'city' | 'province' | 'national';
  results: RealtimeHospitalResult[];
  sources: string[];
  fetched_at: string | null;
  fallback_scope?: 'district' | 'city' | 'province' | 'national' | null;
  fallback_message?: string | null;
  processing_notice?: string | null;
};

export type HospitalDirectoryResponse = {
  status: 'OK';
  page: number;
  page_size: number;
  total: number;
  fetched_at: string | null;
  results: RealtimeHospitalResult[];
};

export type FeedbackCategory = 'bug' | 'improvement' | 'other';
export type FeedbackStatus = 'new' | 'processed';
export type FeedbackAttachment = {
  id?: string;
  filename: string;
  content_type: 'image/jpeg' | 'image/png' | 'image/webp';
  data: string;
};
export type FeedbackItem = {
  id: string;
  category: FeedbackCategory;
  message: string;
  contact: string | null;
  status: FeedbackStatus;
  created_at: string;
  updated_at: string;
  attachments: FeedbackAttachment[];
};

export type TriageDirection = {
  key: string;
  title: string;
  likelihood: string;
  basis: string;
  department: string;
  possible_diseases?: string[];
  urgent_warning: string;
};

export type TriageResponse = {
  summary: string;
  directions: TriageDirection[];
  urgent_warning: string;
  disclaimer: string;
  is_diagnosis: false;
  ai_used: boolean;
  explicit_disease_input?: boolean;
};

export type SymptomClarificationAnswer = { question_id: string; value: string };
export type SymptomClarificationAskedQuestion = { id: string; text: string; options: string[] };
export type SymptomClarificationResponse = {
  status: 'NEEDS_CLARIFICATION' | 'COMPLETE' | 'EMERGENCY';
  question: { id: string; text: string; type: 'single' | 'multi' | 'text'; options: string[] } | null;
  progress: { current: number; total: number };
  estimated_total?: number;
  directions: TriageDirection[];
  urgent_warning: string;
  ai_used?: boolean;
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
  official_website_url?: string | null;
  wechat_appointment?: string | null;
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

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function postMatch<Response>(path: string, input: MatchInput | (MatchInput & { ai_consent: true })): Promise<Response> {
  const response = await fetch(apiUrl(path), {
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
  location_level: 'province' | 'city' | 'district';
  scope: RealtimeSearchResponse['scope'];
  ai_consent: boolean;
  confirmed_direction?: string;
  hospital_tiers: Array<'tertiary_a'>;
  ignore_geography?: boolean;
}): Promise<RealtimeSearchResponse> {
  const response = await fetch(apiUrl('/v1/realtime-hospital-search'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<RealtimeSearchResponse>;
}

export async function triageSymptoms(input: { query: string; ai_consent: true }): Promise<TriageResponse> {
  const response = await fetch(apiUrl('/v1/triage'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<TriageResponse>;
}

export async function clarifySymptoms(input: { query: string; answers: SymptomClarificationAnswer[]; asked_questions?: SymptomClarificationAskedQuestion[]; ai_consent: true }): Promise<SymptomClarificationResponse> {
  const response = await fetch(apiUrl('/v1/symptom-clarification'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<SymptomClarificationResponse>;
}

export async function getRealtimeHospitalDetail(id: string): Promise<RealtimeHospitalDetail> {
  const response = await fetch(apiUrl(`/v1/realtime-hospitals/${encodeURIComponent(id)}`));
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<RealtimeHospitalDetail>;
}

export async function getHospitalDirectory(page = 1, pageSize = 25): Promise<HospitalDirectoryResponse> {
  const response = await fetch(apiUrl(`/v1/hospital-directory?page=${page}&page_size=${pageSize}`));
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<HospitalDirectoryResponse>;
}

export async function submitFeedback(input: { category: FeedbackCategory; message: string; contact?: string; attachments?: FeedbackAttachment[] }): Promise<{ id: string; status: FeedbackStatus }> {
  const response = await fetch(apiUrl('/v1/feedback'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input),
  });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<{ id: string; status: FeedbackStatus }>;
}

export async function adminFeedbackSession(token: string): Promise<{ token: string }> {
  const response = await fetch(apiUrl('/admin/feedback/session'), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }),
  });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<{ token: string }>;
}

export async function listAdminFeedback(token: string, status?: FeedbackStatus): Promise<{ items: FeedbackItem[]; total: number; limit: number; offset: number }> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  const response = await fetch(apiUrl(`/admin/feedback${query}`), { headers: { 'X-Feedback-Admin-Token': token } });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<{ items: FeedbackItem[]; total: number; limit: number; offset: number }>;
}

export async function updateAdminFeedback(token: string, feedbackId: string, status: FeedbackStatus): Promise<FeedbackItem> {
  const response = await fetch(apiUrl(`/admin/feedback/${encodeURIComponent(feedbackId)}`), {
    method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-Feedback-Admin-Token': token }, body: JSON.stringify({ status }),
  });
  if (!response.ok) throw new MatchApiError(response.status);
  return response.json() as Promise<FeedbackItem>;
}
