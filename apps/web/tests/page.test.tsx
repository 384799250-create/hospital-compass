import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Page from '../app/page';
import { MatchApiError, matchHospitals } from '../lib/api';

vi.mock('../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/api')>()),
  matchHospitals: vi.fn(),
}));

describe('patient matching page', () => {
  beforeEach(() => {
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
    await user.click(screen.getByRole('button', { name: 'Clear local data' }));

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
