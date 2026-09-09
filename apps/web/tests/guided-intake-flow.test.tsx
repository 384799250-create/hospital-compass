import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { clarifySymptoms, MatchApiError, realtimeSearchHospitals, triageSymptoms } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  clarifySymptoms: vi.fn(),
  realtimeSearchHospitals: vi.fn(),
  triageSymptoms: vi.fn(),
}));

describe('guided medical entry flow', () => {
  beforeEach(() => {
    vi.mocked(triageSymptoms).mockReset();
    vi.mocked(clarifySymptoms).mockReset();
    vi.mocked(realtimeSearchHospitals).mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('opens with only the start action available', () => {
    render(<Page />);

    expect(screen.getByRole('button', { name: '开始使用' })).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.getByRole('link', { name: '医院目录' }).getAttribute('href')).toBe('/directory');
    expect(screen.getByRole('link', { name: '使用说明' }).getAttribute('href')).toBe('/guide');
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('opens the symptom dialog after the start action', async () => {
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));

    expect(screen.getByRole('dialog', { name: '先告诉我，你哪里不舒服？' })).toBeTruthy();
    expect(screen.getByText('症状或疾病').className).toContain('guidedFieldLabel');
    expect(screen.getByRole('textbox', { name: '症状或疾病' })).toBeTruthy();
  });

  it('shows an animated AI thinking status while the first symptom assessment is pending', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockImplementation(() => new Promise(() => {}));
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '孩子发热咳嗽');
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(screen.getByRole('status', { name: 'AI 正在理解你的描述，请稍候' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '正在理解你的描述…' })).toBeTruthy();
  });

  it('submits the symptom description when Enter is pressed', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '已整理方向',
      directions: [{ key: 'ophthalmology', title: '眼科相关方向', likelihood: '较符合', basis: '视物模糊需要眼科评估。', department: '眼科', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '仅作健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: true,
    });
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '眼睛模糊，看不清远处');
    await user.keyboard('{Enter}');

    expect(triageSymptoms).toHaveBeenCalledWith({ query: '眼睛模糊，看不清远处', ai_consent: true });
  });

  it('keeps a line break in the symptom description when Shift and Enter are pressed', async () => {
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    const input = screen.getByRole('textbox', { name: '症状或疾病' }) as HTMLTextAreaElement;
    await user.type(input, '眼睛模糊');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    await user.type(input, '看不清远处');

    expect(input.value).toBe('眼睛模糊\n看不清远处');
    expect(triageSymptoms).not.toHaveBeenCalled();
  });

  it('labels each direction likelihood as a disease possibility', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '\u5df2\u6574\u7406\u75be\u75c5\u65b9\u5411',
      directions: [{
        key: 'neurology', title: '\u795e\u7ecf\u5185\u79d1\u65b9\u5411', likelihood: '\u4e2d\u7b49',
        basis: '\u9700\u8981\u7ed3\u5408\u66f4\u591a\u4fe1\u606f\u8bc4\u4f30', department: '\u795e\u7ecf\u5185\u79d1', urgent_warning: '',
      }],
      urgent_warning: '', disclaimer: '\u4ec5\u4f5c\u5065\u5eb7\u4fe1\u606f\u6574\u7406', is_diagnosis: false, ai_used: true,
    });
    render(<Page />);

    await user.click(screen.getAllByRole('button')[0]);
    await user.type(screen.getByRole('textbox'), '\u5934\u75db');
    await user.click(screen.getAllByRole('button').at(-1)!);

    expect(await screen.findByText('\u75be\u75c5\u53ef\u80fd\u6027\uff1a\u4e2d\u7b49')).toBeTruthy();
  });

  it('translates English likelihood values into Chinese labels', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '\u5df2\u6574\u7406\u75be\u75c5\u65b9\u5411',
      directions: [{
        key: 'neurology', title: '\u795e\u7ecf\u5185\u79d1\u65b9\u5411', likelihood: 'medium',
        basis: '\u9700\u8981\u7ed3\u5408\u66f4\u591a\u4fe1\u606f\u8bc4\u4f30', department: '\u795e\u7ecf\u5185\u79d1', urgent_warning: '',
      }],
      urgent_warning: '', disclaimer: '\u4ec5\u4f5c\u5065\u5eb7\u4fe1\u606f\u6574\u7406', is_diagnosis: false, ai_used: true,
    });
    render(<Page />);

    await user.click(screen.getAllByRole('button')[0]);
    await user.type(screen.getByRole('textbox'), '\u5934\u75db');
    await user.click(screen.getAllByRole('button').at(-1)!);

    expect(await screen.findByText('\u75be\u75c5\u53ef\u80fd\u6027\uff1a\u4e2d\u7b49')).toBeTruthy();
    expect(screen.queryByText('\u75be\u75c5\u53ef\u80fd\u6027\uff1amedium')).toBeNull();
  });

  it('shows direction confirmation before preferences after clarification', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '需要补充信息',
      directions: [{ key: 'general', title: '待确认方向', likelihood: '待评估', basis: '信息不足', department: '全科医学科', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '仅作健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms)
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'duration', text: '这种不舒服多久了？', type: 'single', options: ['刚开始', '几天了', '不确定'] },
        progress: { current: 1, total: 1 }, directions: [], urgent_warning: '',
      })
      .mockResolvedValueOnce({
        status: 'COMPLETE', question: null, progress: { current: 1, total: 1 }, urgent_warning: '',
        directions: [{ key: 'cardiology', title: '心血管相关疾病方向', likelihood: '较符合', basis: '症状和回答相关', department: '心血管内科', possible_diseases: ['冠心病'], urgent_warning: '' }],
      });
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '持续胸闷');
    await user.click(screen.getByRole('button', { name: '继续' }));
    await user.click(screen.getByRole('checkbox', { name: '几天了' }));
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(await screen.findByText('心血管相关疾病方向')).toBeTruthy();
    expect(screen.getByText('建议就诊科室：心血管内科')).toBeTruthy();
    expect(screen.queryByText('综合信息')).toBeNull();

    await user.click(screen.getByRole('radio', { name: /心血管相关疾病方向/ }));
    await user.click(screen.getByRole('button', { name: '按所选科室继续' }));
    expect(await screen.findByRole('heading', { name: '告诉我你的所在位置和就医偏好' })).toBeTruthy();
  });

  it('skips clarification for a recognized explicit disease even when multiple directions are returned', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '已整理疾病相关方向',
      directions: [
        { key: 'endocrinology', title: '糖尿病相关方向', likelihood: '待评估', basis: '需要结合并发症情况判断。', department: '内分泌科', possible_diseases: ['糖尿病'], urgent_warning: '' },
        { key: 'vascular', title: '糖尿病并发症方向', likelihood: '待评估', basis: '需要结合下肢症状判断。', department: '血管外科', possible_diseases: ['糖尿病足'], urgent_warning: '' },
      ],
      urgent_warning: '', disclaimer: '仅作健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: true,
      explicit_disease_input: true,
    } as never);
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '糖尿病');
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(await screen.findByText('糖尿病相关方向')).toBeTruthy();
    expect(clarifySymptoms).not.toHaveBeenCalled();
  });

  it('keeps asking when clarification remains unresolved after the first answer', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '需要补充信息',
      directions: [{ key: 'general', title: '待确认方向', likelihood: '待评估', basis: '信息不足', department: '全科医学科', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '仅作健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms)
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'location', text: '你主要是哪里不舒服？', type: 'single', options: ['胸口', '肚子', '其他', '不确定'] },
        progress: { current: 1, total: 1 }, directions: [], urgent_warning: '',
      })
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'duration', text: '这种不舒服大概多久了？', type: 'single', options: ['刚开始', '几天了', '不确定'] },
        progress: { current: 2, total: 2 }, directions: [], urgent_warning: '',
      })
      .mockResolvedValueOnce({
        status: 'COMPLETE', question: null, progress: { current: 2, total: 2 }, urgent_warning: '',
        directions: [{ key: 'general', title: '需要进一步评估的健康问题', likelihood: '待评估', basis: '需要更多信息', department: '全科医学科', possible_diseases: [], urgent_warning: '' }],
      });

    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '不舒服');
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(await screen.findByText('你主要是哪里不舒服？')).toBeTruthy();
    await user.click(screen.getByRole('checkbox', { name: '不确定' }));
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(await screen.findByText('这种不舒服大概多久了？')).toBeTruthy();
    expect(screen.getByText(/第 2 题 · 预计共 2-4 个问题/)).toBeTruthy();
    expect(screen.queryByText('需要进一步评估的健康问题')).toBeNull();

    await user.click(screen.getByRole('checkbox', { name: '刚开始' }));
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(await screen.findByText('需要进一步评估的健康问题')).toBeTruthy();
    expect(clarifySymptoms).toHaveBeenLastCalledWith({
      query: '不舒服',
      answers: [
        { question_id: 'location', value: '不确定' },
        { question_id: 'duration', value: '刚开始' },
      ],
      asked_questions: [
        { id: 'location', text: '你主要是哪里不舒服？', options: ['胸口', '肚子', '其他', '不确定'] },
        { id: 'duration', text: '这种不舒服大概多久了？', options: ['刚开始', '几天了', '不确定'] },
      ],
      ai_consent: true,
    });
  });

  it('submits every selected clarification option together', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '需要补充信息',
      directions: [{ key: 'general', title: '待确认方向', likelihood: '待评估', basis: '信息不足', department: '全科医学科', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '仅作健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms)
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'lifestyle', text: '你的生活方式是否有以下特点？', type: 'single', options: ['经常熬夜或压力大', '饮食油腻', '不确定'] },
        progress: { current: 1, total: 1 }, directions: [], urgent_warning: '',
      })
      .mockResolvedValueOnce({
        status: 'COMPLETE', question: null, progress: { current: 1, total: 1 }, directions: [], urgent_warning: '',
      });

    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '头发容易出油');
    await user.click(screen.getByRole('button', { name: '继续' }));
    await user.click(screen.getByRole('checkbox', { name: '经常熬夜或压力大' }));
    await user.click(screen.getByRole('checkbox', { name: '饮食油腻' }));
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(clarifySymptoms).toHaveBeenLastCalledWith({
      query: '头发容易出油',
      answers: [{ question_id: 'lifestyle', value: '经常熬夜或压力大；饮食油腻', values: ['经常熬夜或压力大', '饮食油腻'] }],
      asked_questions: [{ id: 'lifestyle', text: '你的生活方式是否有以下特点？', options: ['经常熬夜或压力大', '饮食油腻', '不确定'] }],
      ai_consent: true,
    });
  });

  it('keeps the triage direction available when the first clarification request fails', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '需要补充信息',
      directions: [{ key: 'ophthalmology', title: '眼科相关方向', likelihood: '待评估', basis: '视物模糊需要眼科评估。', department: '眼科', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '仅作健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms).mockRejectedValue(new MatchApiError(503));
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '视物模糊');
    await user.click(screen.getByRole('button', { name: '继续' }));

    expect(await screen.findByText('眼科相关方向')).toBeTruthy();
    expect(screen.getByText('智能整理暂时未能继续出题，已保留当前就医方向。')).toBeTruthy();
  });

  it('keeps the selected answer and retries after an AI availability error', async () => {
    const user = userEvent.setup();
    vi.mocked(triageSymptoms).mockResolvedValue({
      summary: '需要补充信息',
      directions: [{ key: 'general', title: '待确认方向', likelihood: '待评估', basis: '信息不足', department: '全科医学科', urgent_warning: '' }],
      urgent_warning: '', disclaimer: '仅作健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: true,
    });
    vi.mocked(clarifySymptoms)
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'location', text: '你主要是哪里不舒服？', type: 'single', options: ['胸口', '肚子', '不确定'] },
        progress: { current: 1, total: 1 }, directions: [], urgent_warning: '',
      })
      .mockRejectedValueOnce(new MatchApiError(503))
      .mockResolvedValueOnce({
        status: 'NEEDS_CLARIFICATION',
        question: { id: 'duration', text: '这种不舒服大概多久了？', type: 'single', options: ['刚开始', '几天了', '不确定'] },
        progress: { current: 2, total: 2 }, directions: [], urgent_warning: '',
      });

    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '不舒服');
    await user.click(screen.getByRole('button', { name: '继续' }));
    await user.click(screen.getByRole('checkbox', { name: '不确定' }));
    await user.click(screen.getByRole('button', { name: '继续' }));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('智能整理服务暂时不可用，请重试。');
    expect((screen.getByRole('checkbox', { name: '不确定' }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy();

    await user.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('这种不舒服大概多久了？')).toBeTruthy();
    expect(clarifySymptoms).toHaveBeenLastCalledWith({
      query: '不舒服',
      answers: [{ question_id: 'location', value: '不确定' }],
      asked_questions: [{ id: 'location', text: '你主要是哪里不舒服？', options: ['胸口', '肚子', '不确定'] }],
      ai_consent: true,
    });
  });
});
