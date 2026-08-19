import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { realtimeSearchHospitals, submitFeedback } from '../lib/api';

vi.mock('../app/guided-intake', () => ({
  default: ({ onComplete }: { onComplete: (input: object) => Promise<void> }) => (
    <button type="button" onClick={() => void onComplete({
      query: '儿童发热咳嗽', province: '广东省', city: '广州市', district: '', scope: 'city',
      priority: 'overall', direction: '儿科',
      triage: { summary: '已整理就医方向', urgent_warning: '', disclaimer: '仅供信息参考', is_diagnosis: false, ai_used: false, directions: [] },
    })}>显示推荐结果</button>
  ),
}));

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  realtimeSearchHospitals: vi.fn(),
  submitFeedback: vi.fn(),
}));

const response = {
  status: 'OK' as const, scope: 'city' as const, directions: ['儿科'], sources: [], fetched_at: '2026-08-18T00:00:00Z',
  results: [{
    id: 'hospital-1', name: '示例医院', city: '广州市', tier: '三级甲等', score: 90,
    score_reasons: [], score_breakdown: {}, sources: [], source_urls: [], fetched_at: '2026-08-18T00:00:00Z',
    registration_url: null, official_website_url: null, wechat_appointment: null, specialties: ['儿科'], address: '广州市',
  }],
};

describe('feedback entry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(realtimeSearchHospitals).mockResolvedValue(response);
    vi.mocked(submitFeedback).mockResolvedValue({ id: 'feedback-1', status: 'new' });
  });

  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('opens the feedback dialog and submits a validated message', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));
    await screen.findByText('示例医院');

    await user.click(screen.getByRole('button', { name: '信息反馈' }));
    await user.selectOptions(screen.getByRole('combobox', { name: '反馈类型' }), 'bug');
    await user.type(screen.getByRole('textbox', { name: '反馈内容' }), '提交结果后页面没有更新，请检查。');
    await user.type(screen.getByRole('textbox', { name: '联系方式（可选）' }), 'user@example.com');
    await user.click(screen.getByRole('button', { name: '提交反馈' }));

    await waitFor(() => expect(submitFeedback).toHaveBeenCalledWith({
      category: 'bug', message: '提交结果后页面没有更新，请检查。', contact: 'user@example.com',
    }));
    expect(await screen.findByText('反馈已提交')).toBeTruthy();
  });

  it('adds an image attachment to the feedback submission', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));
    await screen.findByText('示例医院');
    await user.click(screen.getByRole('button', { name: '信息反馈' }));
    await user.type(screen.getByRole('textbox', { name: '反馈内容' }), '附带截图说明这个问题，方便后台排查。');

    const image = new File(['image-bytes'], 'issue.png', { type: 'image/png' });
    await user.upload(screen.getByLabelText('添加图片'), image);
    expect(await screen.findByText('issue.png')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '提交反馈' }));

    await waitFor(() => expect(submitFeedback).toHaveBeenCalledWith(expect.objectContaining({
      category: 'improvement',
      message: '附带截图说明这个问题，方便后台排查。',
      contact: '',
      attachments: expect.arrayContaining([expect.objectContaining({ filename: 'issue.png', content_type: 'image/png' })]),
    })));
  });
});
