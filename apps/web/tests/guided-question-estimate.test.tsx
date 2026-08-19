import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { clarifySymptoms, realtimeSearchHospitals, triageSymptoms } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  clarifySymptoms: vi.fn(),
  realtimeSearchHospitals: vi.fn(),
  triageSymptoms: vi.fn(),
}));

describe('clarification question estimate', () => {
  beforeEach(() => {
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '\u9700\u8981\u8865\u5145',
      directions: [{ key: 'general', title: '\u5f85\u786e\u8ba4', likelihood: '\u5f85\u8bc4\u4f30', basis: '\u4fe1\u606f\u4e0d\u8db3', department: '\u5168\u79d1\u533b\u5b66\u79d1', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '\u4ec5\u4f9b\u4fe1\u606f\u53c2\u8003', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms).mockResolvedValue({
      status: 'NEEDS_CLARIFICATION',
      question: { id: 'q1', text: '\u5b69\u5b50\u7684\u5e74\u9f84\u5927\u6982\u591a\u5927', type: 'single', options: ['\u51e0\u5c0f\u65f6', '\u51e0\u4e2a\u6708'] },
      progress: { current: 1, total: 1 }, estimated_total: 4, directions: [], urgent_warning: '',
    });
    vi.mocked(realtimeSearchHospitals).mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows an approximate question count and explains that AI adjusts it', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '\u5f00\u59cb\u4f7f\u7528' }));
    await user.type(screen.getByRole('textbox', { name: /\u75c7\u72b6/ }), '\u5b69\u5b50\u4e0d\u8212\u670d');
    await user.click(screen.getByRole('button', { name: '\u7ee7\u7eed' }));

    expect(await screen.findByText(/\u9884\u8ba1\u5171 4 \u4e2a\u95ee\u9898/)).toBeTruthy();
    expect(screen.getByText(/AI \u4f1a\u6839\u636e\u4f60\u7684\u56de\u7b54\u52a8\u6001\u8c03\u6574/)).toBeTruthy();
  });
});
