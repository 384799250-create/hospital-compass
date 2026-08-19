import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import HospitalDirectoryPage from '../app/hospital-directory';
import { getHospitalDirectory, realtimeSearchHospitals, triageSymptoms } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  realtimeSearchHospitals: vi.fn(),
  triageSymptoms: vi.fn(),
  getHospitalDirectory: vi.fn(),
}));

const result = {
  id: 'demo-hospital-1', name: '示例医院', city: '广州市', tier: '三级甲等', score: 92, score_reasons: ['专科实力'],
  score_breakdown: { specialty: 90, official_service: 100 },
  sources: [{ title: '丁香园医院目录', url: 'https://y.dxy.cn/hospital/', snippet: '医院资料', fetched_at: '2026-08-13T00:00:00Z' }],
  source_urls: ['https://y.dxy.cn/hospital/'], fetched_at: '2026-08-13T00:00:00Z', registration_url: null,
  official_website_url: 'https://hospital.example.org', wechat_appointment: '示例医院公众号', specialties: ['心血管内科'],
  address: '广州市越秀区中山路 1 号', core_advantages: '专科实力', match_reason: '匹配',
};

describe('guided patient matching page', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(triageSymptoms).mockResolvedValue({ summary: '已整理方向', directions: [{ key: 'cardiology', title: '心脏相关疾病', likelihood: '较符合', basis: '胸部不适', department: '心血管内科', urgent_warning: '' }], urgent_warning: '', disclaimer: 'disclaimer', is_diagnosis: false, ai_used: true });
    vi.mocked(realtimeSearchHospitals).mockResolvedValue({ status: 'OK', scope: 'city', directions: ['心血管内科'], sources: [], fetched_at: '2026-08-13T00:00:00Z', results: [result] });
    vi.mocked(getHospitalDirectory).mockReturnValue(new Promise(() => {}));
  });

  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  async function completeFlow(user: ReturnType<typeof userEvent.setup>) {
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.type(screen.getByRole('textbox', { name: '症状或疾病' }), '胸痛');
    await user.click(screen.getByRole('button', { name: '继续' }));
    expect(screen.getByText('建议就诊科室：心血管内科')).toBeTruthy();
    await user.click(screen.getByRole('radio'));
    await user.click(screen.getByRole('button', { name: '按所选科室继续' }));
    await user.selectOptions(screen.getByRole('combobox', { name: '省份' }), '广东省');
    await user.selectOptions(screen.getByRole('combobox', { name: '城市' }), '广州市');
    await user.click(screen.getByRole('button', { name: '开始推荐医院' }));
  }

  it('starts with only the guided entry action', () => {
    render(<Page />);
    expect(screen.getByRole('button', { name: '开始使用' })).toBeTruthy();
    expect(screen.getByRole('link', { name: '医院目录' }).getAttribute('href')).toBe('/directory');
    expect(screen.getByRole('link', { name: '使用说明' }).getAttribute('href')).toBe('/guide');
    expect(screen.getByRole('region', { name: /先说清楚症状/ }).className).toContain('landingHeroCentered');
    expect(screen.getByRole('heading', { name: '先说清楚症状再找到合适的医院' }).textContent).toBe('先说清楚症状再找到合适的医院');
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.queryAllByRole('button')).toHaveLength(1);
  });

  it('shows direction before location preferences and calls realtime search', async () => {
    const user = userEvent.setup();
    await completeFlow(user);
    expect(await screen.findByText('示例医院')).toBeTruthy();
    expect(realtimeSearchHospitals).toHaveBeenCalledWith(expect.objectContaining({
      query: '胸痛',
      location: { province: '广东省', city: '广州市', district: '广州市' },
      confirmed_direction: '心血管内科',
    }));
  });

  it('shows a compact result hero with current matching context', async () => {
    const user = userEvent.setup();
    await completeFlow(user);

    expect(screen.getByRole('heading', { name: '找到更适合的医院信息' })).toBeTruthy();
    expect(screen.getByText('心血管内科 · 广东省 · 广州市 · 市级')).toBeTruthy();
  });

  it('keeps hospital score and official service information visible', async () => {
    const user = userEvent.setup();
    await completeFlow(user);
    expect((await screen.findAllByText('示例医院')).length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/官方服务信息 100\.0 分/)).toBeTruthy();
    expect(screen.getByText('预约挂号方式：示例医院公众号')).toBeTruthy();
  });

  it('allows saving a hospital from the result card', async () => {
    const user = userEvent.setup();
    await completeFlow(user);
    const favorite = (await screen.findAllByRole('button', { name: '收藏 示例医院' }))[0];
    await user.click(favorite);
    expect(screen.getByRole('button', { name: '取消收藏 示例医院' })).toBeTruthy();
  });

  it('opens the favorite drawer and expands it without losing results', async () => {
    const user = userEvent.setup();
    await completeFlow(user);
    await user.click((await screen.findAllByRole('button', { name: '收藏 示例医院' }))[0]);
    await user.click(screen.getByRole('button', { name: /收藏夹 1/ }));
    expect(screen.getByRole('dialog', { name: '收藏夹' })).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '放大查看收藏夹' }));
    expect(screen.getByRole('heading', { name: '收藏医院' })).toBeTruthy();
    expect(screen.getByText('示例医院')).toBeTruthy();
  });

  it('provides stable targets for the top navigation links', async () => {
    const user = userEvent.setup();
    await completeFlow(user);
    expect(document.getElementById('results')).toBeTruthy();
    expect(document.getElementById('guide')).toBeTruthy();
    expect(screen.getByRole('link', { name: '医院目录' }).getAttribute('href')).toBe('/directory');
    expect(screen.getByRole('link', { name: '使用说明' }).getAttribute('href')).toBe('/guide');
  });

  it('opens the detailed usage guide at /guide', () => {
    window.history.pushState({}, '', '/guide');
    render(<Page />);

    expect(screen.getByRole('heading', { name: '如何使用医途' })).toBeTruthy();
    expect(screen.getAllByRole('link', { name: '返回首页' }).some((link) => link.getAttribute('href') === '/')).toBe(true);
    expect(screen.getByRole('heading', { name: '评分逻辑' })).toBeTruthy();
  });

  it('opens the hospital directory at /directory', () => {
    window.history.pushState({}, '', '/directory');
    render(<Page />);

    expect(screen.getByRole('heading', { name: '医院目录' })).toBeTruthy();
    expect(screen.getByText('正在加载医院目录')).toBeTruthy();
  });

  it('shows only hospital names in comprehensive directory rows', async () => {
    vi.mocked(getHospitalDirectory).mockResolvedValue({ status: 'OK', page: 1, page_size: 25, total: 2, fetched_at: null, results: [
      { ...result, id: 'h1', name: '甲医院', score: 94 },
      { ...result, id: 'h2', name: '乙医院', score: 81 },
    ] });
    render(<HospitalDirectoryPage />);

    expect(await screen.findByRole('heading', { name: '甲医院' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: '乙医院' })).toBeTruthy();
    expect(screen.queryByText('94.0')).toBeNull();
    expect(screen.queryByText('广州市')).toBeNull();
  });
});
