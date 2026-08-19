import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { getRealtimeHospitalDetail, realtimeSearchHospitals, triageSymptoms } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  triageSymptoms: vi.fn(), realtimeSearchHospitals: vi.fn(), getRealtimeHospitalDetail: vi.fn(),
}));

describe('hospital detail sources and appointment links', () => {
  beforeEach(() => {
    vi.mocked(triageSymptoms).mockResolvedValue({ summary: 'summary', directions: [{ key: 'cardiology', title: '心脏相关疾病', likelihood: '中', basis: 'basis', department: '心血管内科', urgent_warning: '' }], urgent_warning: '', disclaimer: 'disclaimer', is_diagnosis: false, ai_used: false });
    vi.mocked(realtimeSearchHospitals).mockResolvedValue({
      status: 'OK', scope: 'district', directions: ['心血管内科'], sources: [], fetched_at: '2026-08-13T00:00:00Z',
      results: [{ id: 'hospital-1', name: '示例医院', city: '广州市', tier: '三级甲等', score: 92, score_reasons: [], score_breakdown: { official_service: 0 },
        sources: [{ title: '丁香园医院目录', url: 'https://y.dxy.cn/hospital/', snippet: '医院资料', fetched_at: '2026-08-13T00:00:00Z' }],
        source_urls: ['https://y.dxy.cn/hospital/'], fetched_at: '2026-08-13T00:00:00Z', registration_url: null,
        official_website_url: 'https://hospital.example.org', wechat_appointment: '示例医院公众号', specialties: ['心血管内科'],
        address: '广州市越秀区中山路 1 号', core_advantages: '专科实力', match_reason: '匹配' }],
    });
    vi.mocked(getRealtimeHospitalDetail).mockResolvedValue({
      id: 'hospital-1', name: '示例医院', city: '广州市', address: '广州市越秀区中山路 1 号', introduction: '数据库简介',
      departments: ['心血管内科'], doctors: [], registration_url: null, official_website_url: 'https://hospital.example.org',
      wechat_appointment: '示例医院公众号', sources: [], fetched_at: '2026-08-13T00:00:00Z',
    });
  });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it('shows public source, official website, and hospital公众号 in the card footer', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '持续胸痛');
    await user.click(screen.getByRole('button', { name: '继续' }));
    await user.click(screen.getByRole('radio'));
    await user.click(screen.getByRole('button', { name: '按所选科室继续' }));
    await user.selectOptions(screen.getByRole('combobox', { name: '省份' }), '广东省');
    await user.selectOptions(screen.getByRole('combobox', { name: '城市' }), '广州市');
    await user.click(screen.getByRole('button', { name: '开始推荐医院' }));
    expect((await screen.findAllByRole('link', { name: /查看公开来源/ })).length).toBeGreaterThan(0);
    expect((await screen.findAllByRole('link', { name: /前往医院官网/ })).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('预约挂号方式：示例医院公众号')).length).toBeGreaterThan(0);
    expect((await screen.findAllByLabelText(/官方服务信息 100\.0 分/)).length).toBeGreaterThan(0);
  });
});
