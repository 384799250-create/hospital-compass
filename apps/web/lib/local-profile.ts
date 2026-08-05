export type LocalProfile = {
  favorites: string[];
  history: string[];
};

const PROFILE_KEY = 'hospital-compass-profile';
const EMPTY_PROFILE: LocalProfile = { favorites: [], history: [] };

function readProfile(): LocalProfile {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROFILE_KEY) ?? 'null') as Partial<LocalProfile> | null;
    if (!parsed || !Array.isArray(parsed.favorites) || !Array.isArray(parsed.history)) return { ...EMPTY_PROFILE };
    return {
      favorites: parsed.favorites.filter((id): id is string => typeof id === 'string'),
      history: parsed.history.filter((query): query is string => typeof query === 'string').slice(0, 10),
    };
  } catch {
    return { ...EMPTY_PROFILE };
  }
}

function saveProfile(profile: LocalProfile): LocalProfile {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  return profile;
}

function sanitizeQuery(query: string): string {
  return query.trim().replace(/\s+/g, ' ').slice(0, 100);
}

export function getProfile(): LocalProfile {
  return readProfile();
}

export function addFavorite(hospitalId: string): LocalProfile {
  const profile = readProfile();
  const favorite = hospitalId.trim();
  return saveProfile({
    ...profile,
    favorites: favorite && !profile.favorites.includes(favorite) ? [...profile.favorites, favorite] : profile.favorites,
  });
}

export function removeFavorite(hospitalId: string): LocalProfile {
  const profile = readProfile();
  return saveProfile({ ...profile, favorites: profile.favorites.filter((id) => id !== hospitalId) });
}

export function rememberSearch(query: string): LocalProfile {
  const profile = readProfile();
  const sanitized = sanitizeQuery(query);
  const history = sanitized
    ? [sanitized, ...profile.history.filter((item) => item !== sanitized)].slice(0, 10)
    : profile.history;
  return saveProfile({ ...profile, history });
}

export function clearProfile(): LocalProfile {
  localStorage.removeItem(PROFILE_KEY);
  return { ...EMPTY_PROFILE };
}
