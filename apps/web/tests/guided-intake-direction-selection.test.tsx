import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import GuidedIntake from '../app/guided-intake';
import { clarifySymptoms, triageSymptoms } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  clarifySymptoms: vi.fn(),
  triageSymptoms: vi.fn(),
}));

describe('guided direction selection', () => {
  beforeEach(() => {
    vi.mocked(triageSymptoms).mockReset();
    vi.mocked(clarifySymptoms).mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('uses the department from the direction selected for hospital recommendations', async () => {
    const user = userEvent.setup();
    const onComplete = vi.fn();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '\u9700\u8981\u8865\u5145\u4fe1\u606f',
      directions: [{
        key: 'general', title: '\u5f85\u786e\u8ba4\u65b9\u5411', likelihood: '\u5f85\u8bc4\u4f30',
        basis: '\u4fe1\u606f\u4e0d\u8db3', department: '\u5168\u79d1\u533b\u5b66\u79d1', urgent_warning: '',
      }],
      urgent_warning: '', disclaimer: '\u4ec5\u4f5c\u5065\u5eb7\u4fe1\u606f\u6574\u7406', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms).mockResolvedValue({
      status: 'COMPLETE', question: null, progress: { current: 1, total: 1 }, urgent_warning: '', ai_used: true,
      directions: [
        {
          key: 'knee', title: '\u819d\u76d6\u9aa8\u75bc\u75db', likelihood: '\u4e2d\u7b49',
          basis: '\u8dd1\u8df3\u65f6\u75bc\u75db', department: '\u8fd0\u52a8\u533b\u5b66\u79d1\u6216\u9aa8\u79d1', possible_diseases: [], urgent_warning: '',
        },
        {
          key: 'strain', title: '\u808c\u8089\u52b3\u635f', likelihood: '\u8f83\u4f4e',
          basis: '\u6d3b\u52a8\u540e\u9178\u80c0', department: '\u5eb7\u590d\u79d1', possible_diseases: [], urgent_warning: '',
        },
      ],
    });
    render(<GuidedIntake onComplete={onComplete} />);

    await user.type(screen.getByRole('textbox'), '\u819d\u76d6\u75bc');
    await user.click(screen.getAllByRole('button').at(-1)!);
    await user.click(await screen.findByRole('radio', { name: /\u808c\u8089\u52b3\u635f/ }));
    await user.click(screen.getByRole('button', { name: '\u6309\u6240\u9009\u79d1\u5ba4\u7ee7\u7eed' }));
    await user.selectOptions(screen.getByLabelText('\u7701\u4efd'), '\u5317\u4eac\u5e02');
    await user.selectOptions(screen.getByLabelText('\u57ce\u5e02'), '\u5317\u4eac\u5e02');
    await user.click(screen.getByRole('button', { name: '\u5f00\u59cb\u63a8\u8350\u533b\u9662' }));

    expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({
      direction: '\u5eb7\u590d\u79d1',
    }));
  });
});
