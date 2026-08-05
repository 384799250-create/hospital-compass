import { beforeEach, describe, expect, it } from 'vitest';

import {
  addFavorite,
  clearProfile,
  getProfile,
  rememberSearch,
  removeFavorite,
} from '../lib/local-profile';

describe('local profile', () => {
  beforeEach(() => localStorage.clear());

  it('retains the ten most recent sanitized search queries', () => {
    for (let index = 0; index < 11; index += 1) {
      rememberSearch(`  Hospital   ${index}  `);
    }

    expect(getProfile().history).toEqual([
      'Hospital 10',
      'Hospital 9',
      'Hospital 8',
      'Hospital 7',
      'Hospital 6',
      'Hospital 5',
      'Hospital 4',
      'Hospital 3',
      'Hospital 2',
      'Hospital 1',
    ]);
  });

  it('stores only hospital IDs as favorites and can remove them', () => {
    addFavorite('demo-1');
    addFavorite('demo-1');
    addFavorite('demo-2');
    removeFavorite('demo-1');

    expect(getProfile().favorites).toEqual(['demo-2']);
  });

  it('clears browser-local favorites and history', () => {
    addFavorite('demo-1');
    rememberSearch('Hospital directory');

    expect(clearProfile()).toEqual({ favorites: [], history: [] });
    expect(getProfile()).toEqual({ favorites: [], history: [] });
  });
});
