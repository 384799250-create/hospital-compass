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
  });

  afterEach(cleanup);

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
});
