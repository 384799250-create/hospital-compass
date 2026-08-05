import { beforeEach, describe, expect, it } from 'vitest';

import {
  addFavorite,
  clearProfile,
  getProfile,
  removeFavorite,
} from '../lib/local-profile';

describe('local profile', () => {
  beforeEach(() => localStorage.clear());

  it('discards malformed and non-hospital favorite IDs when reading storage', () => {
    localStorage.setItem('hospital-compass-profile', JSON.stringify({
      favorites: ['demo-1', ' sudden chest pain ', '../demo-2', '', 42],
    }));

    expect(getProfile()).toEqual({ favorites: ['demo-1'] });
  });

  it('does not persist an invalid favorite ID', () => {
    addFavorite('sudden chest pain');

    expect(getProfile()).toEqual({ favorites: [] });
    expect(localStorage.getItem('hospital-compass-profile')).toBeNull();
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
