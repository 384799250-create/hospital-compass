export type LocalProfile = {
  favorites: string[];
};

const PROFILE_KEY = 'hospital-compass-profile';
const EMPTY_PROFILE: LocalProfile = { favorites: [] };
const HOSPITAL_ID_PATTERN = /^demo-[a-z0-9]+(?:-[a-z0-9]+)*$/i;

function isHospitalId(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 64 && HOSPITAL_ID_PATTERN.test(value);
}

function readProfile(): LocalProfile {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROFILE_KEY) ?? 'null') as Partial<LocalProfile> | null;
    if (!parsed || !Array.isArray(parsed.favorites)) return { ...EMPTY_PROFILE };
    return {
      favorites: [...new Set(parsed.favorites.filter(isHospitalId))],
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
  if (!isHospitalId(hospitalId)) return profile;

  return saveProfile({
    ...profile,
    favorites: profile.favorites.includes(hospitalId) ? profile.favorites : [...profile.favorites, hospitalId],
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
