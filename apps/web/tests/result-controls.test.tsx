import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { RealtimeSearchResponse, realtimeSearchHospitals } from '../lib/api';

vi.mock('../app/guided-intake', () => ({
  default: ({ onComplete }: { onComplete: (input: object) => Promise<void> }) => (
    <button type="button" onClick={() => void onComplete({
      query: '\u513f\u7ae5\u53d1\u70ed\u54b3\u55fd', province: '\u5e7f\u4e1c\u7701', city: '\u5e7f\u5dde\u5e02', district: '',
      scope: 'city', priority: 'overall', direction: '\u513f\u79d1',
      triage: {
        summary: '\u5df2\u6574\u7406\u5c31\u533b\u65b9\u5411', urgent_warning: '', disclaimer: '\u4ec5\u4f9b\u4fe1\u606f\u53c2\u8003', is_diagnosis: false, ai_used: true,
        directions: [
          { key: 'pediatrics', title: '\u513f\u7ae5\u4e0a\u547c\u5438\u9053\u611f\u67d3', likelihood: '\u5e38\u89c1', basis: '\u53d1\u70ed\u54b3\u55fd', department: '\u513f\u79d1', urgent_warning: '' },
          { key: 'pediatric-asthma', title: '\u513f\u7ae5\u54ee\u5598', likelihood: '\u53ef\u80fd', basis: '\u54b3\u55fd\u4f34\u968f\u54ee\u9e23', department: '\u513f\u79d1', urgent_warning: '' },
          { key: 'respiratory', title: '\u6025\u6027\u652f\u6c14\u7ba1\u708e', likelihood: '\u53ef\u80fd', basis: '\u54b3\u55fd\u6301\u7eed', department: '\u547c\u5438\u79d1', urgent_warning: '' },
        ],
      },
    })}>{'\u663e\u793a\u63a8\u8350\u7ed3\u679c'}</button>
  ),
}));

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  realtimeSearchHospitals: vi.fn(),
}));

const response = {
  status: 'OK' as const, scope: 'city' as const, directions: ['\u513f\u79d1'], sources: [], fetched_at: '2026-08-14T00:00:00Z',
  results: [{
    id: 'hospital-1', name: '\u793a\u4f8b\u533b\u9662', city: '\u5e7f\u5dde\u5e02', tier: '\u4e09\u7ea7\u7532\u7b49', score: 90,
    score_reasons: [], score_breakdown: {}, sources: [], source_urls: [], fetched_at: '2026-08-14T00:00:00Z',
    registration_url: null, official_website_url: null, wechat_appointment: '\u793a\u4f8b\u533b\u9662\u516c\u4f17\u53f7', specialties: ['\u513f\u79d1'], address: '\u5e7f\u5dde\u5e02', core_advantages: '\u793a\u4f8b\u4f18\u52bf', match_reason: '\u5339\u914d',
  }],
};

describe('result controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    vi.mocked(realtimeSearchHospitals).mockResolvedValue(response);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('switches department directions, shows the selected address, and keeps direction-scope results cached', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '\u5f00\u59cb\u4f7f\u7528' }));
    await user.click(screen.getByRole('button', { name: '\u663e\u793a\u63a8\u8350\u7ed3\u679c' }));

    await screen.findByText('\u793a\u4f8b\u533b\u9662');
    expect(screen.getByText('\u5f53\u524d\u9009\u62e9\u7684\u5730\u5740')).toBeTruthy();
    expect(screen.getByLabelText('\u9009\u62e9\u7701\u4efd')).toBeTruthy();
    expect(screen.getByLabelText('\u9009\u62e9\u57ce\u5e02')).toBeTruthy();
    expect(screen.getByLabelText('\u9009\u62e9\u533a\u53bf')).toBeTruthy();
    expect(screen.getByLabelText(/\u5f53\u524d\u9009\u62e9\uff1a\u513f\u7ae5\u4e0a\u547c\u5438\u9053\u611f\u67d3/)).toBeTruthy();
    expect(screen.getByRole('radio', { name: /\u513f\u7ae5\u4e0a\u547c\u5438\u9053\u611f\u67d3/ }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('radio', { name: /\u513f\u7ae5\u54ee\u5598/ }).getAttribute('aria-checked')).toBe('false');
    expect(screen.getByRole('radio', { name: /\u6025\u6027\u652f\u6c14\u7ba1\u708e/ })).toBeTruthy();

    await user.click(screen.getByRole('radio', { name: /\u6025\u6027\u652f\u6c14\u7ba1\u708e/ }));
    await waitFor(() => expect(realtimeSearchHospitals).toHaveBeenCalledTimes(2));
    expect(vi.mocked(realtimeSearchHospitals)).toHaveBeenLastCalledWith(expect.objectContaining({ confirmed_direction: '\u547c\u5438\u79d1' }));

    await user.click(screen.getByRole('radio', { name: /\u513f\u7ae5\u4e0a\u547c\u5438\u9053\u611f\u67d3/ }));
    await user.click(screen.getByRole('radio', { name: /\u6025\u6027\u652f\u6c14\u7ba1\u708e/ }));
    expect(realtimeSearchHospitals).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole('tab', { name: '\u533a/\u53bf\u7ea7' }));
    expect(screen.getByLabelText('\u9009\u62e9\u533a\u53bf')).toBeTruthy();
    expect(realtimeSearchHospitals).toHaveBeenCalledTimes(2);
  });

  it('positions the scope switcher after the initial hospital results load', async () => {
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));
    await screen.findByText('示例医院');

    await waitFor(() => expect(window.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' })));
    expect(screen.getByRole('tablist', { name: '切换排名范围' })).toBeTruthy();
  });

  it('sets every geography score to 100 and recomputes the displayed total without refetching', async () => {
    const user = userEvent.setup();
    vi.mocked(realtimeSearchHospitals).mockResolvedValue({
      ...response,
      results: [{
        ...response.results[0],
        score: 70.75,
        score_breakdown: {
          specialty: 80,
          public_capability: 75,
          geography: 30,
          freshness_completeness: 80,
          official_service: 100,
        },
        official_website_url: 'https://example.org/hospital',
      }],
    });
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));
    await screen.findByText('示例医院');
    expect(screen.getByText('综合评分 70.75')).toBeTruthy();

    await user.click(screen.getByRole('checkbox', { name: '不考虑地理位置' }));
    expect(screen.getByText('综合评分 84.75')).toBeTruthy();
    await user.click(screen.getByText('评分详情'));
    expect(screen.getByLabelText('地理位置 100.0 分')).toBeTruthy();
    await waitFor(() => expect(realtimeSearchHospitals).toHaveBeenCalledTimes(2));
    expect(vi.mocked(realtimeSearchHospitals)).toHaveBeenLastCalledWith(expect.objectContaining({ ignore_geography: true }));
  });

  it('updates the city-level list when the selected city changes', async () => {
    const user = userEvent.setup();
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '\u5f00\u59cb\u4f7f\u7528' }));
    await user.click(screen.getByRole('button', { name: '\u663e\u793a\u63a8\u8350\u7ed3\u679c' }));
    await screen.findByText('\u793a\u4f8b\u533b\u9662');

    await user.selectOptions(screen.getByLabelText('\u9009\u62e9\u7701\u4efd'), '\u5e7f\u4e1c\u7701');
    await user.selectOptions(screen.getByLabelText('\u9009\u62e9\u57ce\u5e02'), '\u6df1\u5733\u5e02');

    await waitFor(() => expect(realtimeSearchHospitals).toHaveBeenCalledTimes(2));
    expect(vi.mocked(realtimeSearchHospitals)).toHaveBeenLastCalledWith(expect.objectContaining({
      location: expect.objectContaining({ province: '\u5e7f\u4e1c\u7701', city: '\u6df1\u5733\u5e02' }),
      location_level: 'city',
    }));
  });

  it('shows the target scope while preserving the current ranking list during a scope change', async () => {
    const user = userEvent.setup();
    let resolveScopeChange: ((value: RealtimeSearchResponse) => void) | undefined;
    vi.mocked(realtimeSearchHospitals)
      .mockResolvedValueOnce(response)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveScopeChange = resolve;
      }));
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));
    await screen.findByText('示例医院');

    await user.click(screen.getByRole('tab', { name: '省级' }));

    expect(screen.getByRole('status').textContent).toContain('正在切换到省级排名');
    expect(screen.getByText('保留当前结果，新的医院范围正在刷新')).toBeTruthy();
    expect(screen.getByRole('tab', { name: '市级' }).hasAttribute('disabled')).toBe(true);
    expect(screen.getByLabelText('实时医院排名').getAttribute('aria-busy')).toBe('true');
    expect(screen.getByText('示例医院')).toBeTruthy();

    resolveScopeChange?.({ ...response, scope: 'province' });
    await screen.findByText('当前排名范围：省级。系统已按用户选择的最小地址范围检索公开资料。');
  });

  it('keeps scope controls disabled while a direction refresh is pending', async () => {
    const user = userEvent.setup();
    vi.mocked(realtimeSearchHospitals)
      .mockResolvedValueOnce(response)
      .mockImplementationOnce(() => new Promise<RealtimeSearchResponse>(() => {}));
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));
    await screen.findByText('示例医院');

    await user.click(screen.getByRole('radio', { name: /急性支气管炎/ }));

    expect(screen.getByRole('tab', { name: '市级' }).hasAttribute('disabled')).toBe(true);
    expect(screen.queryByText(/正在切换到.*排名/)).toBeNull();
  });

  it('automatically expands the search scope after an empty result', async () => {
    const user = userEvent.setup();
    vi.mocked(realtimeSearchHospitals)
      .mockResolvedValueOnce({ status: 'NO_RESULTS', scope: 'city', directions: ['儿科'], sources: [], fetched_at: null, results: [], fallback_scope: 'province', fallback_message: '当前区域暂无足够医院资料。' })
      .mockResolvedValueOnce({ ...response, scope: 'province' });
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));

    expect(await screen.findByText('示例医院')).toBeTruthy();
    expect(realtimeSearchHospitals).toHaveBeenCalledTimes(2);
    expect(vi.mocked(realtimeSearchHospitals)).toHaveBeenLastCalledWith(expect.objectContaining({ scope: 'province' }));
  });

  it('labels hospital-strength evidence separately and removes duplicate entries', async () => {
    const user = userEvent.setup();
    vi.mocked(realtimeSearchHospitals).mockResolvedValue({
      ...response,
      results: [{
        ...response.results[0],
        score_breakdown: { specialty: 58.2, public_capability: 97, official_service: 100 },
        specialty_evidence: [
          {
            hospital: '示例医院', city: '广州市', specialty: '', rank: 1552, year: 2024,
            ranking_name: '全国综合排名', ranking_scope: '全国', ranking_source_name: '2024年全国综合排名',
            source: 'https://example.org/ranking', verification_status: '已通过',
          },
          {
            hospital: '示例医院', city: '广州市', specialty: '', rank: 1552, year: 2024,
            ranking_name: '全国综合排名', ranking_scope: '全国', ranking_source_name: '2024年全国综合排名',
            source: 'https://example.org/ranking', verification_status: '已通过',
          },
        ],
      }],
    });
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));

    expect(await screen.findByText('医院综合实力依据')).toBeTruthy();
    expect(screen.queryByText('权威专科依据')).toBeNull();
    expect(screen.getAllByText(/2024年全国综合排名第1552名/).length).toBe(1);
    expect(screen.getByText('暂无直接专科依据')).toBeTruthy();
    expect(screen.getByText('58.2')).toBeTruthy();
  });

  it('separates source-backed specialty capability from hospital-strength rankings', async () => {
    const user = userEvent.setup();
    vi.mocked(realtimeSearchHospitals).mockResolvedValue({
      ...response,
      results: [{
        ...response.results[0],
        has_direct_specialty_evidence: true,
        score_breakdown: { specialty: 82, public_capability: 77.3, official_service: 100 },
        specialty_evidence: [
          {
            hospital: '示例医院', city: '广州市', department: '神经内科',
            strength_level: '神经内科为广西医疗卫生重点学科（县级）',
            source: 'https://example.org/about', verification_status: '公开资料',
          },
          {
            hospital: '示例医院', city: '广州市', specialty: '', rank: 1552, year: 2024,
            ranking_name: '全国综合排名', ranking_scope: '全国', ranking_source_name: '2024年全国综合排名',
            source: 'https://example.org/ranking', verification_status: '已通过',
          },
        ],
      }],
    });
    render(<Page />);
    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));

    expect(await screen.findByText('专科能力依据')).toBeTruthy();
    expect(screen.getByText(/神经内科.*广西医疗卫生重点学科/)).toBeTruthy();
    expect(screen.getByText('医院综合实力依据')).toBeTruthy();
    expect(screen.getByText(/2024年全国综合排名第1552名/)).toBeTruthy();
    expect(screen.queryByText('权威专科依据')).toBeNull();
  });

  it('merges equivalent national specialty capability labels and keeps specialty ranking visible', async () => {
    const user = userEvent.setup();
    vi.mocked(realtimeSearchHospitals).mockResolvedValue({
      ...response,
      results: [{
        ...response.results[0],
        has_direct_specialty_evidence: true,
        score_breakdown: { specialty: 91.15, public_capability: 100, geography: 100 },
        specialty_evidence: [
          {
            hospital: '示例医院', city: '广州市', department: '神经内科', year: 2023,
            strength_level: '国家级', diagnosis_scope: '国家临床重点专科建设项目',
            source: 'https://www.nhc.gov.cn/', verification_status: '已核验',
          },
          {
            hospital: '示例医院', city: '广州市', department: '神经内科',
            strength_level: '国家级重点', source: 'https://hospital.example.org/', verification_status: 'verified',
          },
          {
            hospital: '示例医院', city: '广州市', specialty: '神经内科', rank: 8, year: 2023,
            ranking_name: '专科声誉排行榜', ranking_scope: '全国', ranking_source_name: '2023年度全国专科声誉排行榜',
            source: 'https://rank.example.org/', verification_status: '已通过',
          },
        ],
      }],
    });
    render(<Page />);

    await user.click(screen.getByRole('button', { name: '开始使用' }));
    await user.click(screen.getByRole('button', { name: '显示推荐结果' }));
    await screen.findByText('示例医院');

    expect(screen.getByText('专科能力依据')).toBeTruthy();
    expect(screen.getByText('专科排名依据')).toBeTruthy();
    const specialtyEvidenceBox = screen.getByLabelText('专科依据');
    expect(specialtyEvidenceBox.contains(screen.getByText('专科能力依据'))).toBe(true);
    expect(specialtyEvidenceBox.contains(screen.getByText('专科排名依据'))).toBe(true);
    expect(screen.getAllByText(/神经内科 · 国家级重点/)).toHaveLength(1);
    expect(screen.getByText(/专科声誉排行榜第8名/)).toBeTruthy();
    expect(screen.getAllByText('查看来源')).toHaveLength(3);
  });
});
