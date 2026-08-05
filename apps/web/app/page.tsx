'use client';

import { FormEvent, useState } from 'react';

import { MatchApiError, MatchResponse, matchHospitals } from '../lib/api';
import styles from './page.module.css';

const FALLBACK_COPY = '匹配服务暂时不可用。请查询当地卫生健康部门地址与医院官方站点；如情况紧急，请立即急诊或拨打 120。';

export default function Page() {
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('');
  const [priority, setPriority] = useState<'overall' | 'specialty' | 'convenience'>('overall');
  const [response, setResponse] = useState<MatchResponse | null>(null);
  const [showEmergency, setShowEmergency] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResponse(null);
    setLoading(true);

    try {
      const nextResponse = await matchHospitals({
        query,
        city: city || undefined,
        priority,
      });
      setResponse(nextResponse);
      setShowEmergency(nextResponse.emergency);
    } catch (requestError) {
      setShowEmergency(false);
      setError(requestError instanceof MatchApiError && requestError.status === 503
        ? FALLBACK_COPY
        : '暂时无法完成匹配，请稍后再试。');
    } finally {
      setLoading(false);
    }
  }

  const recommendations = response && !response.emergency ? response.results : [];

  return (
    <main className={styles.page}>
      <section className={styles.search} aria-labelledby="page-title">
        <p className={styles.eyebrow}>医疗信息导航</p>
        <h1 id="page-title">医院信息匹配</h1>
        <p className={styles.disclaimer}>本工具仅供查找演示医院信息，不提供诊断、治疗或疗效建议。</p>

        <form onSubmit={submit} className={styles.form}>
          <label htmlFor="query">症状或疾病</label>
          <textarea
            id="query"
            name="query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            maxLength={500}
            rows={3}
          />

          <label htmlFor="city">所在城市</label>
          <select id="city" name="city" value={city} onChange={(event) => setCity(event.target.value)}>
            <option value="">不限城市</option>
            <option value="上海">上海</option>
            <option value="杭州">杭州</option>
          </select>

          <label htmlFor="priority">匹配偏好</label>
          <select id="priority" name="priority" value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}>
            <option value="overall">综合信息</option>
            <option value="specialty">专科方向</option>
            <option value="convenience">就近便利</option>
          </select>

          <button type="submit" disabled={loading}>{loading ? '匹配中…' : '开始匹配'}</button>
        </form>
      </section>

      {error && <p className={styles.notice} role="alert">{error}</p>}

      {recommendations.length > 0 && (
        <section aria-labelledby="recommendations-title" className={styles.results}>
          <h2 id="recommendations-title">推荐医院</h2>
          <p>以下为演示数据生成的信息匹配结果，请通过官方渠道核实。</p>
          <div className={styles.cards}>
            {recommendations.map((hospital) => (
              <article className={styles.card} key={`${hospital.name}-${hospital.city}`}>
                <h3>{hospital.name}</h3>
                <p>{hospital.city} · {hospital.demo_label || '演示数据'}</p>
                <dl>
                  <div><dt>专科方向</dt><dd>{(hospital.specialties ?? response.directions).join('、') || '未提供'}</dd></div>
                  <div><dt>匹配分数</dt><dd>{hospital.score}</dd></div>
                  <div><dt>分数说明</dt><dd>{(hospital.score_reasons ?? ['根据所选匹配偏好与演示资料生成']).join('；')}</dd></div>
                  <div><dt>来源日期</dt><dd>{hospital.source_date ?? '未提供'}</dd></div>
                </dl>
              </article>
            ))}
          </div>
        </section>
      )}

      {showEmergency && (
        <div className={styles.backdrop} role="presentation">
          <section aria-modal="true" aria-labelledby="emergency-title" className={styles.dialog} role="dialog">
            <h2 id="emergency-title">请立即急诊或拨打 120</h2>
            <p>当前描述可能需要紧急处理。此工具不能替代紧急医疗服务。</p>
            <button type="button" onClick={() => setShowEmergency(false)}>我已了解，仍查看医院信息</button>
          </section>
        </div>
      )}
    </main>
  );
}
