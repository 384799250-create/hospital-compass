import { useEffect, useState } from 'react';

import { getHospitalDirectory, MatchApiError, RealtimeHospitalResult } from '../lib/api';
import styles from './hospital-directory.module.css';

const PAGE_SIZE = 25;

function formatDate(value: string | null | undefined) {
  if (!value) return '暂无更新日期';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function HospitalRow({ hospital, rank }: { hospital: RealtimeHospitalResult; rank: number }) {
  return (
    <li className={styles.row}>
      <div className={styles.rank} aria-label={`第 ${rank} 名`}>{String(rank).padStart(2, '0')}</div>
      <div className={styles.hospital}>
        <h2>{hospital.name}</h2>
      </div>
    </li>
  );
}

export default function HospitalDirectoryPage() {
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [results, setResults] = useState<RealtimeHospitalResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getHospitalDirectory(page, PAGE_SIZE).then((response) => {
      if (cancelled) return;
      setResults(response.results);
      setTotal(response.total);
      setFetchedAt(response.fetched_at);
    }).catch((requestError: unknown) => {
      if (cancelled) return;
      setError(requestError instanceof MatchApiError ? '医院目录暂时无法加载，请稍后重试。' : '医院目录加载失败，请检查网络连接后重试。');
      setResults([]);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [page]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const firstRank = (page - 1) * PAGE_SIZE + 1;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/" aria-label="返回医途首页">医途</a>
        <nav className={styles.headerNav} aria-label="医院目录导航">
          <span>按综合排名查看</span>
          <a href="/guide">使用说明</a>
          <a className={styles.backLink} href="/">返回首页</a>
        </nav>
      </header>

      <div className={styles.content}>
        <section className={styles.intro} aria-labelledby="directory-title">
          <div>
            <h1 id="directory-title">医院目录</h1>
            <p>这里按三甲医院综合实力分从高到低展示医院名称。综合实力分沿用医院匹配页的医院综合实力评分，地理位置不参与目录排序。</p>
          </div>
          <aside className={styles.introMeta}>
            <strong>三甲医院综合排名</strong>
            <span>列表顺序由综合实力分决定，排名越靠前代表分数越高。</span>
          </aside>
        </section>

        <div className={styles.toolbar}>
          <p>{loading ? '正在整理综合排名…' : <>共 <strong>{total}</strong> 家医院 · 当前第 {page} / {pageCount} 页</>}</p>
          {fetchedAt && <p>目录资料更新：{formatDate(fetchedAt)}</p>}
        </div>

        {loading && <p className={styles.status} role="status">正在加载医院目录</p>}
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!loading && !error && results.length === 0 && <p className={styles.status}>暂无可展示的医院资料。</p>}
        {!loading && !error && results.length > 0 && <ol className={styles.list} aria-label="按综合排名排序的医院名单">
          {results.map((hospital, index) => <HospitalRow key={hospital.id} hospital={hospital} rank={firstRank + index} />)}
        </ol>}

        {!loading && !error && total > PAGE_SIZE && <nav className={styles.pagination} aria-label="医院目录分页">
          <button type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}>上一页</button>
          <span>第 {page} / {pageCount} 页</span>
          <button type="button" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page >= pageCount}>下一页</button>
        </nav>}

        <footer className={styles.footer}>
          <span>公开资料整理</span>
          <span>仅供就医信息参考</span>
          <span>不替代医生诊断</span>
          <a href="/">返回首页</a>
        </footer>
      </div>
    </main>
  );
}
