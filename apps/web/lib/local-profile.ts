export type FavoriteHospital = {
  id: string;
  name: string;
  city: string;
  tier: string;
  address: string;
  score: number | null;
  department: string;
  officialWebsiteUrl: string | null;
};

export type LocalProfile = {
  favorites: string[];
  favoriteHospitals: FavoriteHospital[];
};

const PROFILE_KEY = 'hospital-compass-profile';
const EMPTY_PROFILE: LocalProfile = { favorites: [], favoriteHospitals: [] };
// Search results use a 16-character SHA-256 prefix; demo IDs are retained
// for the fixture data used by the development test suite.
const HOSPITAL_ID_PATTERN = /^(?:demo-[a-z0-9]+(?:-[a-z0-9]+)*|[a-f0-9]{16})$/i;

function isHospitalId(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 64 && HOSPITAL_ID_PATTERN.test(value);
}

function readProfile(): LocalProfile {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROFILE_KEY) ?? 'null') as Partial<LocalProfile> | null;
    if (!parsed || !Array.isArray(parsed.favorites)) return { ...EMPTY_PROFILE };
    const favorites = [...new Set(parsed.favorites.filter(isHospitalId))];
    return {
      favorites,
      favoriteHospitals: deduplicateSnapshots(
        Array.isArray(parsed.favoriteHospitals) ? parsed.favoriteHospitals : [],
        favorites,
      ),
    };
  } catch {
    return { ...EMPTY_PROFILE };
  }
}

function saveProfile(profile: LocalProfile): LocalProfile {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  return profile;
}

export function getProfile(): LocalProfile {
  return readProfile();
}

export function addFavorite(hospital: FavoriteHospital | string): LocalProfile {
  const profile = readProfile();
  const hospitalId = typeof hospital === 'string' ? hospital : hospital.id;
  if (!isHospitalId(hospitalId)) return profile;

  const favoriteHospitals = typeof hospital === 'string'
    ? profile.favoriteHospitals
    : replaceSnapshot(profile.favoriteHospitals, sanitizeSnapshot(hospital));

  return saveProfile({
    ...profile,
    favorites: profile.favorites.includes(hospitalId) ? profile.favorites : [...profile.favorites, hospitalId],
    favoriteHospitals,
  });
}

export function removeFavorite(hospitalId: string): LocalProfile {
  const profile = readProfile();
  return saveProfile({
    favorites: profile.favorites.filter((id) => id !== hospitalId),
    favoriteHospitals: profile.favoriteHospitals.filter((hospital) => hospital.id !== hospitalId),
  });
}

export function clearProfile(): LocalProfile {
  localStorage.removeItem(PROFILE_KEY);
  return { ...EMPTY_PROFILE };
}

function sanitizeSnapshot(value: unknown): FavoriteHospital | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Partial<FavoriteHospital>;
  if (!isHospitalId(record.id) || !normalizedText(record.name, 100)) return null;
  const score = typeof record.score === 'number' && Number.isFinite(record.score)
    ? Math.max(0, Math.min(100, record.score))
    : null;
  return {
    id: record.id,
    name: normalizedText(record.name, 100),
    city: normalizedText(record.city, 60),
    tier: normalizedText(record.tier, 60),
    address: normalizedText(record.address, 200),
    score,
    department: normalizedText(record.department, 100),
    officialWebsiteUrl: normalizedUrl(record.officialWebsiteUrl),
  };
}

function normalizedText(value: unknown, maxLength: number): string {
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
}

function normalizedUrl(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 300) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function replaceSnapshot(existing: FavoriteHospital[], snapshot: FavoriteHospital | null): FavoriteHospital[] {
  if (!snapshot) return existing;
  return [...existing.filter((item) => item.id !== snapshot.id), snapshot];
}

function deduplicateSnapshots(values: unknown[], favoriteIds: string[]): FavoriteHospital[] {
  const snapshots = new Map<string, FavoriteHospital>();
  for (const value of values) {
    const snapshot = sanitizeSnapshot(value);
    if (snapshot && favoriteIds.includes(snapshot.id)) snapshots.set(snapshot.id, snapshot);
  }
  return [...snapshots.values()];
}
