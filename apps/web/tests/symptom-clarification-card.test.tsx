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

const ambiguousTriage = {
  summary: '当前描述还需要补充信息。',
  directions: [{ key: 'general', title: '需要进一步评估的健康问题', likelihood: '待评估', basis: '信息不足', department: '全科医学科', urgent_warning: '' }],
  urgent_warning: '', disclaimer: '以上是健康信息整理，不是医学诊断。', is_diagnosis: false as const, ai_used: true,
};

const questionResponse = {
  status: 'NEEDS_CLARIFICATION' as const,
  question: { id: 'location', text: '你主要是哪里不舒服？', type: 'single' as const, options: ['胸口', '肚子', '头部', '胳膊、腿或关节', '其他', '不确定'] },
  progress: { current: 1, total: 1 }, directions: [], urgent_warning: '',
};

describe('symptom clarification card', () => {
  beforeEach(() => {
    vi.mocked(triageSymptoms).mockReset();
    vi.mocked(clarifySymptoms).mockReset();
    vi.mocked(realtimeSearchHospitals).mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  async function submitAmbiguous(user: ReturnType<typeof userEvent.setup>) {
    vi.mocked(triageSymptoms).mockResolvedValue(ambiguousTriage);
    vi.mocked(clarifySymptoms).mockResolvedValue(questionResponse);
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '不舒服');
    await user.click(screen.getByRole('button', { name: '继续' }));
  }

  it('shows exactly one accessible question card for an ambiguous description', async () => {
    const user = userEvent.setup();
    await submitAmbiguous(user);

    expect(await screen.findByRole('region', { name: '补充确认问题' })).toBeTruthy();
    expect(screen.getByText('你主要是哪里不舒服？')).toBeTruthy();
    expect(screen.getByText(/第 1 题 · 预计共 1-3 个问题/)).toBeTruthy();
    expect(screen.getAllByRole('checkbox')).toHaveLength(7);
    expect((screen.getByRole('button', { name: '继续' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('asks a follow-up when AI returns multiple competing directions', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      ...ambiguousTriage,
      directions: [
        { ...ambiguousTriage.directions[0], key: 'tension', title: '紧张性头痛', likelihood: '常见可能' },
        { ...ambiguousTriage.directions[0], key: 'migraine', title: '偏头痛', likelihood: '可能' },
      ],
    });
    vi.mocked(clarifySymptoms).mockResolvedValue(questionResponse);
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '头疼');
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(await screen.findByRole('region', { name: '补充确认问题' })).toBeTruthy();
    expect(clarifySymptoms).toHaveBeenCalledWith({ query: '头疼', answers: [], ai_consent: true });
  });

  it('submits the selected uncertain option and renders the resolved department', async () => {
    const user = userEvent.setup();
    await submitAmbiguous(user);
    vi.mocked(clarifySymptoms).mockResolvedValueOnce({
      status: 'COMPLETE', question: null, progress: { current: 1, total: 1 }, urgent_warning: '', directions: [{
        key: 'cardiology', title: '心血管相关疾病方向', likelihood: '更符合', basis: '胸部不适', department: '心血管内科', possible_diseases: ['心绞痛', '冠心病'], urgent_warning: '',
      }],
    });

    await user.click(screen.getByRole('checkbox', { name: '不确定' }));
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(clarifySymptoms).toHaveBeenLastCalledWith({
      query: '不舒服',
      answers: [{ question_id: 'location', value: '不确定' }],
      asked_questions: [{ id: 'location', text: '你主要是哪里不舒服？', options: ['胸口', '肚子', '头部', '胳膊、腿或关节', '其他', '不确定'] }],
      ai_consent: true,
    });
    expect(await screen.findByText(/心血管内科/)).toBeTruthy();
    expect(screen.getByText('心绞痛、冠心病')).toBeTruthy();
    expect(screen.queryByRole('region', { name: '补充确认问题' })).toBeNull();
  });

  it('interrupts clarification with an emergency warning for a red flag answer', async () => {
    const user = userEvent.setup();
    await submitAmbiguous(user);
    vi.mocked(clarifySymptoms).mockResolvedValueOnce({
      status: 'EMERGENCY', question: null, progress: { current: 1, total: 1 }, directions: [], urgent_warning: '请立即拨打120或前往急诊。',
    });

    await user.click(screen.getByRole('checkbox', { name: '胸口' }));
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(screen.getAllByRole('alert').some((node) => node.textContent?.includes('请立即拨打120或前往急诊。'))).toBe(true);
    expect(screen.queryByRole('region', { name: '补充确认问题' })).toBeNull();
  });

  it('lets the user enter a custom answer when no option fits', async () => {
    const user = userEvent.setup();
    await submitAmbiguous(user);
    vi.mocked(clarifySymptoms).mockResolvedValueOnce({
      status: 'COMPLETE', question: null, progress: { current: 1, total: 1 }, urgent_warning: '', directions: [{
        key: 'general', title: '需要进一步评估的健康问题', likelihood: '待评估', basis: '需要更多信息', department: '全科医学科', urgent_warning: '',
      }],
    });

    await user.click(screen.getByRole('checkbox', { name: '以上都不符合，我自己填写' }));
    const customInput = screen.getByRole('textbox', { name: '自己填写' });
    await user.type(customInput, '胸口左边像针扎一样，活动时更明显');
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(clarifySymptoms).toHaveBeenLastCalledWith({
      query: '不舒服',
      answers: [{ question_id: 'location', value: '胸口左边像针扎一样，活动时更明显' }],
      asked_questions: [{ id: 'location', text: '你主要是哪里不舒服？', options: ['胸口', '肚子', '头部', '胳膊、腿或关节', '其他', '不确定'] }],
      ai_consent: true,
    });
  });
});
