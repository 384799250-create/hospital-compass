import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FavoriteDrawer } from '../app/favorite-drawer';

const favorite = {
  id: 'a49c5d1e5de78232',
  name: '示例医院',
  city: '广州市',
  tier: '三级甲等',
  address: '越秀区中山路 1 号',
  score: 92,
  department: '心血管内科',
  officialWebsiteUrl: 'https://hospital.example.org',
};

describe('favorite drawer', () => {
  it('shows saved hospitals and exposes expand and remove actions', async () => {
    const user = userEvent.setup();
    const remove = vi.fn();
    const expand = vi.fn();
    render(<FavoriteDrawer open favorites={[favorite]} onClose={vi.fn()} onExpand={expand} onRemove={remove} onOpenDetail={vi.fn()} />);

    expect(screen.getByRole('dialog', { name: '收藏夹' })).toBeTruthy();
    expect(screen.getByText('示例医院')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '放大查看收藏夹' }));
    expect(expand).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('button', { name: '取消收藏 示例医院' }));
    expect(remove).toHaveBeenCalledWith(favorite.id);
  });
});
