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

describe('clarification question history', () => {
  beforeEach(() => {
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '\u9700\u8981\u8865\u5145',
      directions: [{ key: 'general', title: '\u5f85\u786e\u8ba4', likelihood: '\u5f85\u8bc4\u4f30', basis: '\u4fe1\u606f\u4e0d\u8db3', department: '\u5168\u79d1\u533b\u5b66\u79d1', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '\u4ec5\u4f9b\u4fe1\u606f\u53c2\u8003', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms)
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'q1', text: '\u7b2c\u4e00\u4e2a\u95ee\u9898', type: 'single', options: ['\u9009\u9879A', '\u9009\u9879B'] },
        progress: { current: 1, total: 2 }, directions: [], urgent_warning: '',
      })
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'q2', text: '\u7b2c\u4e8c\u4e2a\u95ee\u9898', type: 'single', options: ['\u9009\u9879C', '\u9009\u9879D'] },
        progress: { current: 2, total: 2 }, directions: [], urgent_warning: '',
      })
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'q2-new', text: '\u6839\u636e\u4fee\u6539\u540e\u7684\u7b2c\u4e8c\u4e2a\u95ee\u9898', type: 'single', options: ['\u9009\u9879E'] },
        progress: { current: 2, total: 2 }, directions: [], urgent_warning: '',
      });
    vi.mocked(realtimeSearchHospitals).mockResolvedValue({
      status: 'NO_RESULTS', scope: 'city', directions: [], sources: [], fetched_at: '', results: [],
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('returns to the previous question with its answer selected and resubmits the edited history', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '\u5f00\u59cb\u4f7f\u7528' }));
    await user.type(screen.getByRole('textbox', { name: /\u75c7\u72b6/ }), '\u4e0d\u8212\u670d');
    await user.click(screen.getByRole('button', { name: '\u7ee7\u7eed' }));

    await user.click(screen.getByRole('checkbox', { name: '\u9009\u9879A' }));
    await user.click(screen.getByRole('button', { name: '\u7ee7\u7eed' }));
    expect(await screen.findByText('\u7b2c\u4e8c\u4e2a\u95ee\u9898')).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '\u8fd4\u56de\u4e0a\u4e00\u9898' }));
    expect(await screen.findByText('\u7b2c\u4e00\u4e2a\u95ee\u9898')).toBeTruthy();
    expect((screen.getByRole('checkbox', { name: '\u9009\u9879A' }) as HTMLInputElement).checked).toBe(true);

    await user.click(screen.getByRole('checkbox', { name: '\u9009\u9879A' }));
    await user.click(screen.getByRole('checkbox', { name: '\u9009\u9879B' }));
    await user.click(screen.getByRole('button', { name: '\u7ee7\u7eed' }));
    expect(await screen.findByText('\u6839\u636e\u4fee\u6539\u540e\u7684\u7b2c\u4e8c\u4e2a\u95ee\u9898')).toBeTruthy();
    expect(vi.mocked(clarifySymptoms)).toHaveBeenLastCalledWith({
      query: '\u4e0d\u8212\u670d',
      answers: [{ question_id: 'q1', value: '\u9009\u9879B' }],
      asked_questions: [{ id: 'q1', text: '\u7b2c\u4e00\u4e2a\u95ee\u9898', options: ['\u9009\u9879A', '\u9009\u9879B'] }],
      ai_consent: true,
    });
  });
});
