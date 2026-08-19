'use client';

import { FormEvent, useEffect, useState } from 'react';

import { adminFeedbackSession, FeedbackItem, FeedbackStatus, listAdminFeedback, updateAdminFeedback } from '../lib/api';
import styles from './page.module.css';

const CATEGORY_LABELS = { bug: '遇到问题', improvement: '改进建议', other: '其他反馈' } as const;

export default function FeedbackAdminPage() {
  const [tokenInput, setTokenInput] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [filter, setFilter] = useState<FeedbackStatus | ''>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadItems(nextToken: string, nextFilter = filter) {
    setLoading(true);
    setError('');
    try {
      const result = await listAdminFeedback(nextToken, nextFilter || undefined);
      setItems(result.items);
    } catch {
      setError('无法加载反馈，请检查令牌或服务状态。');
      setToken(null);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const session = await adminFeedbackSession(tokenInput.trim());
      setToken(session.token);
      await loadItems(session.token);
    } catch {
      setError('令牌无效或后台未配置。');
      setLoading(false);
    }
  }

  useEffect(() => {
    if (token) void loadItems(token, filter);
    // The filter change is handled by the select callback to avoid duplicate requests.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleFilterChange(nextFilter: FeedbackStatus | '') {
    setFilter(nextFilter);
    if (token) await loadItems(token, nextFilter);
  }

  async function markProcessed(item: FeedbackItem) {
    if (!token) return;
    try {
      const updated = await updateAdminFeedback(token, item.id, 'processed');
      setItems((current) => current.map((candidate) => candidate.id === updated.id ? updated : candidate));
    } catch {
      setError('更新反馈状态失败，请重试。');
    }
  }

  if (!token) return <main className={styles.adminPage}><section className={styles.adminLogin} aria-labelledby="feedback-admin-title"><span>管理入口</span><h1 id="feedback-admin-title">反馈后台</h1><p>请输入管理员令牌查看用户反馈。</p><form onSubmit={handleLogin}><label><span>管理员令牌</span><input aria-label="管理员令牌" type="password" value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} required /></label>{error && <p className={styles.feedbackError} role="alert">{error}</p>}<button type="submit" disabled={loading}>{loading ? '验证中…' : '进入反馈后台'}</button></form></section></main>;

  return <main className={styles.adminPage}><section className={styles.adminPanel} aria-labelledby="feedback-admin-title"><header className={styles.adminHeader}><div><span>管理入口</span><h1 id="feedback-admin-title">用户反馈</h1></div><button type="button" onClick={() => { setToken(null); setItems([]); setTokenInput(''); }}>退出</button></header><div className={styles.adminToolbar}><label><span>状态筛选</span><select aria-label="状态筛选" value={filter} onChange={(event) => void handleFilterChange(event.target.value as FeedbackStatus | '')}><option value="">全部</option><option value="new">未处理</option><option value="processed">已处理</option></select></label><span>{loading ? '正在加载…' : `共 ${items.length} 条`}</span></div>{error && <p className={styles.feedbackError} role="alert">{error}</p>}<ol className={styles.feedbackList}>{items.map((item) => <li key={item.id} className={styles.feedbackItem}><div className={styles.feedbackItemMeta}><strong>{CATEGORY_LABELS[item.category]}</strong><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('zh-CN')}</time><span>{item.status === 'new' ? '未处理' : '已处理'}</span></div><p>{item.message}</p>{item.contact && <small>联系方式：{item.contact}</small>}{item.attachments.length > 0 && <div className={styles.feedbackItemAttachments} aria-label="反馈图片">{item.attachments.map((attachment) => <a className={styles.feedbackItemAttachment} href={`data:${attachment.content_type};base64,${attachment.data}`} target="_blank" rel="noreferrer" key={attachment.id || attachment.filename}><img src={`data:${attachment.content_type};base64,${attachment.data}`} alt={attachment.filename} title={attachment.filename} /></a>)}</div>}{item.status === 'new' && <button type="button" onClick={() => void markProcessed(item)}>标记已处理</button>}</li>)}</ol>{!items.length && !loading && <p className={styles.adminEmpty}>暂无反馈。</p>}</section></main>;
}
