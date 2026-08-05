import { beforeEach, describe, expect, it } from 'vitest';

import * as localProfile from '../lib/local-profile';
import {
  addFavorite,
  clearProfile,
  getProfile,
  removeFavorite,
} from '../lib/local-profile';

describe('local profile', () => {
  beforeEach(() => localStorage.clear());

  it('never writes symptom-like text to local storage', () => {
    const symptomQuery = 'sudden chest pain';

    (localProfile as { rememberSearch?: (query: string) => void }).rememberSearch?.(symptomQuery);

    expect(localStorage.getItem('hospital-compass-profile') ?? '').not.toContain(symptomQuery);
  });

  it('stores only hospital IDs as favorites and can remove them', () => {
    addFavorite('demo-1');
    addFavorite('demo-1');
    addFavorite('demo-2');
    removeFavorite('demo-1');

    expect(getProfile().favorites).toEqual(['demo-2']);
  });

  it('clears browser-local favorites', () => {
    addFavorite('demo-1');

    expect(clearProfile()).toEqual({ favorites: [] });
    expect(getProfile()).toEqual({ favorites: [] });
  });
});
