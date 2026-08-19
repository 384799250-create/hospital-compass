import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { adminFeedbackSession, listAdminFeedback, updateAdminFeedback } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  adminFeedbackSession: vi.fn(),
  listAdminFeedback: vi.fn(),
  updateAdminFeedback: vi.fn(),
}));

describe('feedback admin page', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/feedback-admin');
    vi.clearAllMocks();
    vi.mocked(adminFeedbackSession).mockResolvedValue({ token: 'session-token' });
    vi.mocked(listAdminFeedback).mockResolvedValue({
      items: [{ id: 'feedback-1', category: 'bug', message: '页面没有更新', contact: null, status: 'new', created_at: '2026-08-18T00:00:00Z', updated_at: '2026-08-18T00:00:00Z', attachments: [] }],
      total: 1, limit: 50, offset: 0,
    });
    vi.mocked(updateAdminFeedback).mockResolvedValue({ id: 'feedback-1', category: 'bug', message: '页面没有更新', contact: null, status: 'processed', created_at: '2026-08-18T00:00:00Z', updated_at: '2026-08-18T00:00:00Z', attachments: [] });
  });

  afterEach(() => { cleanup(); window.history.pushState({}, '', '/'); vi.restoreAllMocks(); });

  it('authenticates and lets an admin mark a feedback item processed', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.type(screen.getByLabelText('管理员令牌'), 'admin-token');
    await user.click(screen.getByRole('button', { name: '进入反馈后台' }));
    expect(await screen.findByText('页面没有更新')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '标记已处理' }));
    await waitFor(() => expect(updateAdminFeedback).toHaveBeenCalledWith('session-token', 'feedback-1', 'processed'));
  });
});
