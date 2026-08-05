export type LocalProfile = {
  favorites: string[];
};

const PROFILE_KEY = 'hospital-compass-profile';
const EMPTY_PROFILE: LocalProfile = { favorites: [] };

function readProfile(): LocalProfile {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROFILE_KEY) ?? 'null') as Partial<LocalProfile> | null;
    if (!parsed || !Array.isArray(parsed.favorites)) return { ...EMPTY_PROFILE };
    return {
      favorites: parsed.favorites.filter((id): id is string => typeof id === 'string'),
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

export function clearProfile(): LocalProfile {
  localStorage.removeItem(PROFILE_KEY);
  return { ...EMPTY_PROFILE };
}
