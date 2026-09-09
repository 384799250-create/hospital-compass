import { FormEvent, useEffect, useMemo, useState } from 'react';
import { createMediaTask, getMediaBalance, getMediaModelDetail, getMediaModels, getMediaTaskStatus, MatchApiError, MediaModel, MediaType } from '../lib/api';
import styles from './media-studio.module.css';

const POLL_INTERVAL = 5000;

function firstValue(value: unknown): string {
  if (Array.isArray(value)) return String(value[0] ?? '');
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

export default function MediaStudio() {
  const [type, setType] = useState<MediaType>('image');
  const [models, setModels] = useState<MediaModel[]>([]);
  const [model, setModel] = useState('');
  const [detail, setDetail] = useState<Record<string, unknown>>({});
  const [balance, setBalance] = useState<Record<string, unknown> | null>(null);
  const [prompt, setPrompt] = useState('');
  const [params, setParams] = useState<Record<string, string>>({});
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'queued' | 'success' | 'error'>('idle');
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus('loading'); setError(null); setTaskId(null); setResultUrl(null); setDetail({});
    void Promise.all([getMediaModels(type), getMediaBalance()]).then(([nextModels, nextBalance]) => {
      if (cancelled) return;
      setModels(nextModels); setBalance(nextBalance); setModel(nextModels[0]?.name ?? '');
    }).catch((requestError) => { if (!cancelled) { setStatus('error'); setError(requestError instanceof MatchApiError ? `无法加载青霖${type === 'image' ? '图片' : '视频'}模型（${requestError.status}）` : '无法连接青霖服务'); } });
    return () => { cancelled = true; };
  }, [type]);

  useEffect(() => {
    if (!model) return;
    let cancelled = false;
    void getMediaModelDetail(model).then((nextDetail) => {
      if (cancelled) return;
      setDetail(nextDetail);
      const rawParams = nextDetail.params;
      const defaults = rawParams && typeof rawParams === 'object' && !Array.isArray(rawParams)
        ? Object.fromEntries(Object.entries(rawParams as Record<string, unknown>).map(([name, options]) => [name, firstValue(options)]))
        : {};
      setParams(defaults);
      setStatus('idle');
    }).catch(() => { if (!cancelled) { setDetail({}); setStatus('idle'); } });
    return () => { cancelled = true; };
  }, [model]);

  useEffect(() => {
    if (!taskId || status !== 'queued') return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void getMediaTaskStatus(taskId).then((next) => {
        if (cancelled || !next.is_final) return;
        if (next.state === 'success' && next.result_url) { setResultUrl(next.result_url); setStatus('success'); }
        else { setStatus('error'); setError(next.error || '青霖任务生成失败'); }
      }).catch((requestError) => { if (!cancelled) { setStatus('error'); setError(requestError instanceof MatchApiError ? `任务查询失败（${requestError.status}）` : '任务查询失败'); } });
    }, POLL_INTERVAL);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [taskId, status]);

  const parameterSchema = useMemo(() => {
    const raw = detail.params;
    return raw && typeof raw === 'object' && !Array.isArray(raw) ? Object.entries(raw as Record<string, unknown>) : [];
  }, [detail]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!model || !prompt.trim()) { setError('请选择模型并填写提示词'); return; }
    setError(null); setResultUrl(null); setStatus('loading');
    try {
      const created = await createMediaTask({ model, prompt: prompt.trim(), params });
      setTaskId(created.task_id); setStatus('queued');
    } catch (requestError) {
      setStatus('error'); setError(requestError instanceof MatchApiError && requestError.status === 402 ? '青霖余额不足，请充值后再生成' : '提交青霖任务失败，请稍后重试');
    }
  }

  const balanceText = firstValue(balance?.balance ?? balance?.credits ?? balance?.remaining);
  return <main className={styles.shell}>
    <a className={styles.back} href="/">← 返回医途</a>
    <header className={styles.header}><div><span className={styles.eyebrow}>媒体工作台</span><h1>把想法变成画面</h1><p>使用青霖生成项目宣传图和短视频。提示词与结果只通过当前服务端代理处理。</p></div><div className={styles.balance}><span>当前余额</span><strong>{balanceText || '未读取'}</strong></div></header>
    <div className={styles.grid}><form className={styles.panel} onSubmit={submit}><h2>生成设置</h2><div className={styles.tabs} role="group" aria-label="媒体类型"><button type="button" aria-pressed={type === 'image'} onClick={() => setType('image')}>生图</button><button type="button" aria-pressed={type === 'video'} onClick={() => setType('video')}>生视频</button></div><label className={styles.field}><span>模型</span><select value={model} onChange={(event) => setModel(event.target.value)} disabled={status === 'loading' || !models.length}><option value="">{models.length ? '请选择模型' : '暂无可用模型'}</option>{models.map((item) => <option key={item.name} value={item.name}>{item.label || item.name}</option>)}</select></label><label className={styles.field}><span>提示词</span><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={type === 'image' ? '例如：清爽的医疗科技风抖音封面，浅蓝背景，手机展示医院信息卡片' : '例如：一段展示就医信息整理助手使用流程的竖版短视频'} maxLength={4000} required /></label>{parameterSchema.length > 0 && <div className={styles.params}>{parameterSchema.map(([name, options]) => <div className={styles.param} key={name}><label htmlFor={`media-${name}`}>{name}</label><input id={`media-${name}`} value={params[name] ?? firstValue(options)} onChange={(event) => setParams((current) => ({ ...current, [name]: event.target.value }))} /></div>)}</div>}<button className={styles.submit} type="submit" disabled={status === 'loading' || status === 'queued' || !model}>{status === 'queued' ? '生成中…' : '提交生成任务'}</button>{error && <p className={styles.notice} role="alert">{error}</p>}</form><section className={`${styles.panel} ${styles.result}`} aria-live="polite">{status === 'success' && resultUrl ? (type === 'video' ? <video src={resultUrl} controls playsInline /> : <img src={resultUrl} alt="青霖生成结果" />) : status === 'queued' ? <div className={styles.waiting}><strong>任务已提交</strong><p>正在等待青霖生成，页面会自动更新。</p></div> : resultUrl ? <a href={resultUrl} target="_blank" rel="noreferrer">打开生成结果 ↗</a> : <div className={styles.waiting}><strong>结果预览</strong><p>提交任务后，生成结果会显示在这里。</p></div>}</section></div>
  </main>;
}
