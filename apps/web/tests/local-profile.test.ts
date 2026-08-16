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

    expect(getProfile()).toEqual({ favorites: ['demo-1'], favoriteHospitals: [] });
  });

  it('does not persist an invalid favorite ID', () => {
    addFavorite('sudden chest pain');

    expect(getProfile()).toEqual({ favorites: [], favoriteHospitals: [] });
    expect(localStorage.getItem('hospital-compass-profile')).toBeNull();
  });

  it('stores only hospital IDs as favorites and can remove them', () => {
    addFavorite('demo-1');
    addFavorite('demo-1');
    addFavorite('demo-2');
    removeFavorite('demo-1');

    expect(getProfile().favorites).toEqual(['demo-2']);
  });

  it('stores the hashed IDs returned by the real hospital search', () => {
    addFavorite('a49c5d1e5de78232');

    expect(getProfile().favorites).toEqual(['a49c5d1e5de78232']);
    expect(getProfile().favoriteHospitals).toEqual([]);
  });

  it('persists a favorite hospital snapshot alongside its ID', () => {
    addFavorite({
      id: 'a49c5d1e5de78232',
      name: '示例医院',
      city: '广州市',
      tier: '三级甲等',
      address: '越秀区中山路 1 号',
      score: 92,
      department: '心血管内科',
      officialWebsiteUrl: 'https://hospital.example.org',
    });

    expect(getProfile().favoriteHospitals).toEqual([
      expect.objectContaining({ id: 'a49c5d1e5de78232', name: '示例医院', score: 92 }),
    ]);
  });

  it('clears browser-local favorites', () => {
    addFavorite('demo-1');

    expect(clearProfile()).toEqual({ favorites: [], favoriteHospitals: [] });
    expect(getProfile()).toEqual({ favorites: [], favoriteHospitals: [] });
  });
});
