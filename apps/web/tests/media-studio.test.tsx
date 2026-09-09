import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import MediaStudio from '../app/media-studio';

const api = vi.hoisted(() => ({
  getMediaModels: vi.fn(), getMediaBalance: vi.fn(), getMediaModelDetail: vi.fn(), createMediaTask: vi.fn(), getMediaTaskStatus: vi.fn(),
}));

vi.mock('../lib/api', () => api);

describe('MediaStudio', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    vi.clearAllMocks();
    api.getMediaModels.mockResolvedValue([{ name: 'image-model', label: '图片模型' }]);
    api.getMediaBalance.mockResolvedValue({ balance: 3 });
    api.getMediaModelDetail.mockResolvedValue({ params: { size: ['1:1'] } });
    api.createMediaTask.mockResolvedValue({ task_id: 'task-1', status: 'queued' });
    api.getMediaTaskStatus.mockResolvedValue({ is_final: true, state: 'success', result_url: 'https://cdn.test/cover.png' });
  });

  it('loads models and submits an image task', async () => {
    render(<MediaStudio />);
    expect(await screen.findByText('图片模型')).toBeTruthy();
    await waitFor(() => expect(screen.getByRole('button', { name: '提交生成任务' }).hasAttribute('disabled')).toBe(false));
    fireEvent.change(screen.getByLabelText('提示词'), { target: { value: '医疗科技封面' } });
    fireEvent.click(screen.getByRole('button', { name: '提交生成任务' }));
    await waitFor(() => expect(api.createMediaTask).toHaveBeenCalledWith({ model: 'image-model', prompt: '医疗科技封面', params: { size: '1:1' } }));
  });

  it('switches to video and renders the final video result', async () => {
    api.getMediaModels.mockImplementation(async (type: string) => [{ name: `${type}-model` }]);
    api.getMediaModelDetail.mockResolvedValue({ params: {} });
    render(<MediaStudio />);
    fireEvent.click(screen.getAllByRole('button', { name: '生视频' })[0]);
    await waitFor(() => expect(api.getMediaModels).toHaveBeenLastCalledWith('video'));
    await waitFor(() => expect(screen.getByRole('button', { name: '提交生成任务' }).hasAttribute('disabled')).toBe(false));
    fireEvent.change(screen.getByLabelText('提示词'), { target: { value: '短视频' } });
    fireEvent.click(screen.getByRole('button', { name: '提交生成任务' }));
    await waitFor(() => expect(screen.getByText('任务已提交')).toBeTruthy());
    await new Promise((resolve) => setTimeout(resolve, 5200));
    await waitFor(() => expect(document.querySelector('video')?.getAttribute('src')).toBe('https://cdn.test/cover.png'));
  }, 12000);
});
