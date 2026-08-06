import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { MatchApiError, aiMatchHospitals, matchHospitals } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  aiMatchHospitals: vi.fn(),
  matchHospitals: vi.fn(),
}));

describe('patient matching page', () => {
  beforeEach(() => {
    vi.mocked(aiMatchHospitals).mockReset();
    vi.mocked(matchHospitals).mockReset();
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  function mockMatch(response: Awaited<ReturnType<typeof matchHospitals>>) {
    vi.mocked(matchHospitals).mockResolvedValue(response);
  }

  it('uses the local matching endpoint by default when AI consent is unchecked', async () => {
    mockMatch({ emergency: false, directions: [], score_version: 'demo-v1', results: [] });
    const user = userEvent.setup();

    render(<Page />);
    const consent = screen.getByRole('checkbox', { name: '同意将本次描述发送给 DeepSeek 进行就医方向整理' });
    expect((consent as HTMLInputElement).checked).toBe(false);
    await user.type(screen.getByLabelText('症状或疾病'), '胸痛');
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(matchHospitals).toHaveBeenCalledWith({ query: '胸痛', city: undefined, priority: 'overall' });
    expect(aiMatchHospitals).not.toHaveBeenCalled();
  });

  it('uses the AI matching endpoint when the consent checkbox is checked', async () => {
    vi.mocked(aiMatchHospitals).mockResolvedValue({
      emergency: false,
      directions: [],
      score_version: 'demo-v1',
      results: [],
      ai: { used: false, summary: null, directions: [], fallback: true },
      pending_candidates: [],
    });
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '胸痛');
    await user.click(screen.getByRole('checkbox', { name: '同意将本次描述发送给 DeepSeek 进行就医方向整理' }));
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(aiMatchHospitals).toHaveBeenCalledWith({
      query: '胸痛', city: undefined, priority: 'overall', ai_consent: true,
    });
    expect(matchHospitals).not.toHaveBeenCalled();
  });

  it('shows the AI summary when AI matching succeeds', async () => {
    vi.mocked(aiMatchHospitals).mockResolvedValue({
      emergency: false,
      directions: [],
      score_version: 'demo-v1',
      results: [],
      ai: {
        used: true,
        summary: '已将描述整理为心血管方向，供医院信息匹配参考。',
        directions: ['心血管内科'],
        fallback: false,
      },
      pending_candidates: [],
    });
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '胸痛');
    await user.click(screen.getByRole('checkbox', { name: '同意将本次描述发送给 DeepSeek 进行就医方向整理' }));
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByText('AI 已整理')).not.toBeNull();
    expect(screen.getByText('已将描述整理为心血管方向，供医院信息匹配参考。')).not.toBeNull();
  });

  it('renders a pending-candidate section with only the safe candidate fields', async () => {
    vi.mocked(aiMatchHospitals).mockResolvedValue({
      emergency: false,
      directions: [],
      score_version: 'demo-v1',
      results: [],
      ai: { used: true, summary: null, directions: [], fallback: false },
      pending_candidates: [{
        name: '待核验医院',
        city: '上海',
        direction: '心血管内科',
        reason: '名称可能与所需专科方向相关，需人工核验。',
        score: 99,
        address: '不应展示的地址',
        phone: '400-000-0000',
        source_url: 'https://example.test/not-for-display',
      }],
    } as unknown as Awaited<ReturnType<typeof aiMatchHospitals>>);
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '持续心悸');
    await user.click(screen.getByRole('checkbox', { name: '同意将本次描述发送给 DeepSeek 进行就医方向整理' }));
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByRole('heading', { name: '待人工核验的候选医院' })).not.toBeNull();
    expect(screen.getByText('这些候选由 AI 生成，仅用于流程体验；请通过医院官网或主管部门核验后再作为就医信息参考。')).not.toBeNull();
    const candidateCard = screen.getByRole('heading', { name: '待核验医院' }).closest('article');
    expect(candidateCard).not.toBeNull();
    expect(candidateCard?.textContent).toContain('上海');
    expect(candidateCard?.textContent).toContain('心血管内科');
    expect(candidateCard?.textContent).toContain('名称可能与所需专科方向相关，需人工核验。');
    expect(candidateCard?.textContent).toContain('待人工核验');
    expect(candidateCard?.textContent).not.toContain('99');
    expect(candidateCard?.textContent).not.toContain('不应展示的地址');
    expect(candidateCard?.textContent).not.toContain('400-000-0000');
    expect(candidateCard?.textContent).not.toContain('https://example.test/not-for-display');
    expect(candidateCard?.textContent).not.toContain('收藏');
    expect(candidateCard?.textContent).not.toContain('推荐');
  });

  it('does not render the pending-candidate section for an empty candidate list', async () => {
    vi.mocked(aiMatchHospitals).mockResolvedValue({
      emergency: false,
      directions: [],
      score_version: 'demo-v1',
      results: [],
      ai: { used: true, summary: null, directions: [], fallback: false },
      pending_candidates: [],
    } as unknown as Awaited<ReturnType<typeof aiMatchHospitals>>);
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '持续心悸');
    await user.click(screen.getByRole('checkbox', { name: '同意将本次描述发送给 DeepSeek 进行就医方向整理' }));
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(screen.queryByRole('heading', { name: '待人工核验的候选医院' })).toBeNull();
  });

  it('hides pending candidates when verified hospital results exist', async () => {
    vi.mocked(aiMatchHospitals).mockResolvedValue({
      emergency: false,
      directions: ['心血管内科'],
      score_version: 'demo-v1',
      results: [{
        id: 'demo-1', name: '已核验医院', city: '上海', demo_label: '演示数据', score: 91,
        specialties: ['心血管内科'], score_reasons: ['专科方向匹配'], source_date: '2026-07-26',
      }],
      ai: { used: true, summary: null, directions: ['心血管内科'], fallback: false },
      pending_candidates: [{
        name: '不应展示的候选医院', city: '上海', direction: '心血管内科', reason: '已有正式结果。',
      }],
    } as unknown as Awaited<ReturnType<typeof aiMatchHospitals>>);
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '持续心悸');
    await user.click(screen.getByRole('checkbox', { name: '同意将本次描述发送给 DeepSeek 进行就医方向整理' }));
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByText('已核验医院')).not.toBeNull();
    expect(screen.queryByRole('heading', { name: '待人工核验的候选医院' })).toBeNull();
  });

  it('shows the local matching status when AI matching falls back', async () => {
    vi.mocked(aiMatchHospitals).mockResolvedValue({
      emergency: false,
      directions: [],
      score_version: 'demo-v1',
      results: [],
      ai: { used: false, summary: null, directions: [], fallback: true },
      pending_candidates: [],
    });
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '胸痛');
    await user.click(screen.getByRole('checkbox', { name: '同意将本次描述发送给 DeepSeek 进行就医方向整理' }));
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByText('已按本地规则匹配')).not.toBeNull();
    expect(screen.queryByText('AI 已整理')).toBeNull();
  });

  it('renders the branded hero and a visible no-match card', async () => {
    mockMatch({ emergency: false, directions: [], score_version: 'demo-v1', results: [] });
    const user = userEvent.setup();

    render(<Page />);
    expect(screen.getByText('医途')).not.toBeNull();
    await user.type(screen.getByLabelText('症状或疾病'), '未收录疾病');
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByText('暂未匹配到已审核医院')).not.toBeNull();
  });

  it('interrupts hospital recommendations for an emergency response', async () => {
    vi.mocked(matchHospitals).mockResolvedValue({
      emergency: true,
      directions: [],
      score_version: 'demo-v1',
      results: [],
    });
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '突发胸痛');
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByText('请立即急诊或拨打 120')).not.toBeNull();
    expect(screen.queryByText('推荐医院')).toBeNull();
    expect(screen.getByRole('main').hasAttribute('inert')).toBe(true);
    const acknowledgement = screen.getByRole('button', { name: '我已了解，仍查看医院信息' });
    expect(document.activeElement).toBe(acknowledgement);

    await user.tab();
    expect(document.activeElement).toBe(acknowledgement);

    await user.click(acknowledgement);

    expect(document.activeElement).toBe(screen.getByRole('button', { name: '开始匹配' }));
  });

  it('shows official-source fallback copy when matching is unavailable', async () => {
    vi.mocked(matchHospitals).mockRejectedValue(new MatchApiError(503));
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '胸痛');
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByText(/当地卫生健康部门地址与医院官方站点/)).not.toBeNull();
    expect(screen.queryByText('推荐医院')).toBeNull();
  });

  it('renders specialty, score reasons, and source date from a normal API response', async () => {
    vi.mocked(matchHospitals).mockResolvedValue({
      emergency: false,
      directions: ['心血管内科'],
      score_version: 'demo-v1',
      results: [{
        id: 'demo-1',
        name: '示例市中心医院',
        city: '上海',
        demo_label: '演示数据',
        score: 91.25,
        specialties: ['心血管内科'],
        score_reasons: ['专科方向匹配', '来源信息在有效期内'],
        source_date: '2026-07-26',
      }],
    });
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '冠心病');
    await user.click(screen.getByRole('button', { name: '开始匹配' }));

    expect(await screen.findByText('心血管内科')).not.toBeNull();
    expect(screen.getByText('专科方向匹配；来源信息在有效期内')).not.toBeNull();
    expect(screen.getByText('2026-07-26')).not.toBeNull();
  });

  it('clears browser-local profile data on request', async () => {
    localStorage.setItem('hospital-compass-profile', JSON.stringify({
      favorites: ['demo-1'],
      history: ['Hospital directory'],
    }));
    const user = userEvent.setup();

    render(<Page />);
    await user.click(screen.getByRole('button', { name: '清除本机数据' }));

    expect(localStorage.getItem('hospital-compass-profile')).toBeNull();
  });

  it('offers an accessible local-only favorite toggle and restores its state', async () => {
    vi.mocked(matchHospitals).mockResolvedValue({
      emergency: false,
      directions: ['心血管内科'],
      score_version: 'demo-v1',
      results: [{
        id: 'demo-1',
        name: '示例市中心医院',
        city: '上海',
        demo_label: 'DEMO DATA',
        score: 91.25,
        specialties: ['心血管内科'],
        score_reasons: ['专科方向匹配'],
        source_date: '2026-07-26',
      }],
    });
    const user = userEvent.setup();

    const { unmount } = render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '冠心病');
    await user.click(screen.getByRole('button', { name: '开始匹配' }));
    const favorite = await screen.findByRole('button', { name: '收藏 示例市中心医院' });

    expect(favorite.getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByText('收藏仅保存在此浏览器中。')).not.toBeNull();
    await user.click(favorite);
    expect(favorite.getAttribute('aria-pressed')).toBe('true');
    expect(localStorage.getItem('hospital-compass-profile')).toBe(JSON.stringify({ favorites: ['demo-1'] }));

    unmount();
    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), '冠心病');
    await user.click(screen.getByRole('button', { name: '开始匹配' }));
    expect((await screen.findByRole('button', { name: '取消收藏 示例市中心医院' })).getAttribute('aria-pressed')).toBe('true');
  });

  it('never persists the submitted symptom while exercising local persistence', async () => {
    const symptomQuery = 'private symptom phrase';
    const writes: string[] = [];
    const setItem = Storage.prototype.setItem;
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
      writes.push(`${key}:${value}`);
      return setItem.call(this, key, value);
    });
    vi.mocked(matchHospitals).mockResolvedValue({
      emergency: false,
      directions: ['心血管内科'],
      score_version: 'demo-v1',
      results: [{
        id: 'demo-1', name: '示例市中心医院', city: '上海', demo_label: 'DEMO DATA', score: 1,
        specialties: ['心血管内科'], score_reasons: ['专科方向匹配'], source_date: '2026-07-26',
      }],
    });
    const user = userEvent.setup();

    render(<Page />);
    await user.type(screen.getByLabelText('症状或疾病'), symptomQuery);
    await user.click(screen.getByRole('button', { name: '开始匹配' }));
    await user.click(await screen.findByRole('button', { name: '收藏 示例市中心医院' }));

    expect(writes.length).toBeGreaterThan(0);
    expect(writes.join('\n')).not.toContain(symptomQuery);
    storageSpy.mockRestore();
  });
});
