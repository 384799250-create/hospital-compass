'use client';

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react';

import { AIMatchResponse, MatchApiError, MatchResponse, RealtimeHospitalDetail, RealtimeSearchResponse, aiMatchHospitals, getRealtimeHospitalDetail, matchHospitals, realtimeSearchHospitals } from '../lib/api';
import { addFavorite, clearProfile, getProfile, removeFavorite } from '../lib/local-profile';
import styles from './page.module.css';
import provinceData from '../data/province.json';
import cityData from '../data/city.json';
import areaData from '../data/area.json';

const FALLBACK_COPY = '匹配服务暂时不可用。请查询当地卫生健康部门地址与医院官方站点；如情况紧急，请立即急诊或拨打 120。';

const LEGACY_LOCATION_TREE: Record<string, Record<string, string[]>> = {
  '广东省': { '广州市': ['越秀区', '天河区', '海珠区', '番禺区', '白云区'], '深圳市': ['南山区', '福田区', '罗湖区', '宝安区', '龙岗区'], '佛山市': ['禅城区', '南海区', '顺德区'], '东莞市': ['莞城区', '南城区', '东城区'] },
  '北京市': { '北京市': ['东城区', '西城区', '朝阳区', '海淀区', '丰台区'] },
  '上海市': { '上海市': ['黄浦区', '徐汇区', '长宁区', '静安区', '浦东新区'] },
  '浙江省': { '杭州市': ['上城区', '拱墅区', '西湖区', '滨江区', '余杭区'], '宁波市': ['海曙区', '江北区', '鄞州区'] },
  '四川省': { '成都市': ['锦江区', '青羊区', '金牛区', '武侯区', '成华区'], '绵阳市': ['涪城区', '游仙区'] },
  '天津市': { '天津市': [] },
  '重庆市': { '重庆市': [] },
  '河北省': { '石家庄市': [], '唐山市': [], '秦皇岛市': [], '保定市': [] },
  '山西省': { '太原市': [], '大同市': [], '运城市': [] },
  '辽宁省': { '沈阳市': [], '大连市': [], '鞍山市': [] },
  '吉林省': { '长春市': [], '吉林市': [] },
  '黑龙江省': { '哈尔滨市': [], '齐齐哈尔市': [] },
  '江苏省': { '南京市': [], '苏州市': [], '无锡市': [], '徐州市': [] },
  '安徽省': { '合肥市': [], '芜湖市': [], '蚌埠市': [] },
  '福建省': { '福州市': [], '厦门市': [], '泉州市': [], '漳州市': [] },
  '江西省': { '南昌市': [], '九江市': [], '赣州市': [] },
  '山东省': { '济南市': [], '青岛市': [], '烟台市': [], '潍坊市': [] },
  '河南省': { '郑州市': [], '洛阳市': [], '开封市': [], '南阳市': [] },
  '湖北省': { '武汉市': [], '宜昌市': [], '襄阳市': [] },
  '湖南省': { '长沙市': [], '株洲市': [], '岳阳市': [] },
  '广西壮族自治区': { '南宁市': [], '柳州市': [], '桂林市': [] },
  '海南省': { '海口市': [], '三亚市': [] },
  '贵州省': { '贵阳市': [], '遵义市': [], '六盘水市': [] },
  '云南省': { '昆明市': [], '曲靖市': [], '大理市': [] },
  '西藏自治区': { '拉萨市': [], '日喀则市': [] },
  '陕西省': { '西安市': [], '宝鸡市': [], '咸阳市': [] },
  '甘肃省': { '兰州市': [], '天水市': [], '酒泉市': [] },
  '青海省': { '西宁市': [], '海东市': [] },
  '宁夏回族自治区': { '银川市': [], '吴忠市': [] },
  '新疆维吾尔自治区': { '乌鲁木齐市': [], '克拉玛依市': [], '喀什市': [] },
  '内蒙古自治区': { '呼和浩特市': [], '包头市': [], '鄂尔多斯市': [] },
  '香港特别行政区': { '香港特别行政区': [] },
  '澳门特别行政区': { '澳门特别行政区': [] },
};

type RegionRow = { code: string; name: string; province: string; city?: string; area?: string };
const LOCATION_TREE: Record<string, Record<string, string[]>> = (provinceData as RegionRow[]).reduce((tree, provinceRow) => {
  const cities = (cityData as RegionRow[]).filter((row) => row.province === provinceRow.province);
  const cityRows = cities.length ? cities : [{ name: provinceRow.name, province: provinceRow.province, code: provinceRow.code }];
  tree[provinceRow.name] = Object.fromEntries(cityRows.map((cityRow) => [
    cityRow.name,
    (areaData as RegionRow[])
      .filter((areaRow) => areaRow.province === provinceRow.province && areaRow.city === (cityRow.city ?? '01'))
      .map((areaRow) => areaRow.name),
  ]));
  return tree;
}, {} as Record<string, Record<string, string[]>>);

export default function Page() {
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('');
  const [priority, setPriority] = useState<'overall' | 'specialty' | 'convenience'>('overall');
  const [aiConsent, setAiConsent] = useState(false);
  const [response, setResponse] = useState<(MatchResponse | AIMatchResponse) | null>(null);
  const [showEmergency, setShowEmergency] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [realtimeQuery, setRealtimeQuery] = useState('');
  const [province, setProvince] = useState('');
  const [realtimeCity, setRealtimeCity] = useState('');
  const [district, setDistrict] = useState('');
  const [scope, setScope] = useState<RealtimeSearchResponse['scope']>('district');
  const [realtimeConsent, setRealtimeConsent] = useState(true);
  const [realtimeResponse, setRealtimeResponse] = useState<RealtimeSearchResponse | null>(null);
  const [realtimeLoading, setRealtimeLoading] = useState(false);
  const [realtimeError, setRealtimeError] = useState<string | null>(null);
  const [locationNotice, setLocationNotice] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [detail, setDetail] = useState<RealtimeHospitalDetail | null>(null);
  const [favorites, setFavorites] = useState<string[]>([]);
  const submitButtonRef = useRef<HTMLButtonElement>(null);
  const acknowledgementRef = useRef<HTMLButtonElement>(null);
  const emergencyDialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    setFavorites(getProfile().favorites);
  }, []);

  useEffect(() => {
    if (!showEmergency) return;

    const dialog = emergencyDialogRef.current;
    if (dialog && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    }
    acknowledgementRef.current?.focus();
  }, [showEmergency]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResponse(null);
    setLoading(true);

    try {
      const input = {
        query,
        city: city || undefined,
        priority,
      };
      const nextResponse = aiConsent
        ? await aiMatchHospitals({ ...input, ai_consent: true })
        : await matchHospitals(input);
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

  async function searchRealtime(nextScope: RealtimeSearchResponse['scope']) {
    setRealtimeError(null);
    setRealtimeResponse(null);
    setDetail(null);
    setRealtimeLoading(true);
    try {
      const result = await realtimeSearchHospitals({
        query: realtimeQuery,
        location: { province: province.trim(), city: realtimeCity.trim(), district: district.trim() || realtimeCity.trim() },
        scope: nextScope,
        ai_consent: realtimeConsent,
      });
      setRealtimeResponse(result);
    } catch (requestError) {
      setRealtimeError(requestError instanceof MatchApiError && requestError.status === 503
        ? '公开资料搜索暂时不可用，请稍后重试。'
        : '实时搜索暂时失败，请检查服务是否已启动。');
    } finally {
      setRealtimeLoading(false);
    }
  }

  async function submitRealtime(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await searchRealtime(scope);
  }

  async function switchRealtimeScope(nextScope: RealtimeSearchResponse['scope']) {
    setScope(nextScope);
    await searchRealtime(nextScope);
  }

  function locateUser() {
    if (!navigator.geolocation) {
      setLocationNotice('当前浏览器不支持自动定位，请手动填写地址。');
      return;
    }
    setLocating(true);
    setLocationNotice(null);
    navigator.geolocation.getCurrentPosition(async ({ coords }) => {
      try {
        const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&accept-language=zh-CN&lat=${coords.latitude}&lon=${coords.longitude}`);
        if (!response.ok) throw new Error('reverse geocode failed');
        const payload = await response.json() as { address?: Record<string, string> };
        const address = payload.address ?? {};
        const nextProvince = address.state || address.province || '';
        const nextCity = address.city || address.municipality || address.town || '';
        const nextDistrict = address.suburb || address.district || address.county || '';
        if (nextProvince) setProvince(nextProvince);
        if (nextCity) setRealtimeCity(nextCity);
        if (nextDistrict) setDistrict(nextDistrict);
        setLocationNotice(nextCity ? `已定位到${nextCity}${nextDistrict || ''}` : '已获取定位，但未解析出城市，请确认地址。');
      } catch {
        setLocationNotice('定位成功但地址解析失败，请手动确认省、市、区。');
      } finally {
        setLocating(false);
      }
    }, () => {
      setLocating(false);
      setLocationNotice('未获得定位权限，请手动填写地址。');
    }, { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 });
  }

  async function openDetail(id: string) {
    try {
      setDetail(await getRealtimeHospitalDetail(id));
    } catch {
      setRealtimeError('详情已过期，请重新搜索。');
    }
  }

  function closeEmergency() {
    const dialog = emergencyDialogRef.current;
    if (dialog && typeof dialog.close === 'function') dialog.close();
    setShowEmergency(false);
    queueMicrotask(() => submitButtonRef.current?.focus());
  }

  function clearLocalData() {
    clearProfile();
    setFavorites([]);
  }

  function toggleFavorite(hospitalId: string) {
    const profile = favorites.includes(hospitalId)
      ? removeFavorite(hospitalId)
      : addFavorite(hospitalId);
    setFavorites(profile.favorites);
  }

  function trapEmergencyFocus(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key === 'Tab') {
      event.preventDefault();
      acknowledgementRef.current?.focus();
    }
  }

  const recommendations = response && !response.emergency ? response.results : [];
  const hasNoMatches = response && !response.emergency && response.results.length === 0;
  const aiResponse = response && 'ai' in response ? response : null;
  const ai = aiResponse?.ai ?? null;
  const pendingCandidates = aiResponse && !aiResponse.emergency && recommendations.length === 0
    ? aiResponse.pending_candidates
    : null;
  const hasDirectionPlaceholders = pendingCandidates?.some((candidate) => candidate.placeholder) ?? false;
  const matchStatus = ai?.used && ai.summary
    ? { title: 'AI 已整理', summary: ai.summary }
    : response && !response.emergency
      ? { title: '已按本地规则匹配', summary: null }
      : null;
  const cityOptions = province ? Object.keys(LOCATION_TREE[province] ?? {}) : [];
  const districtOptions = province && realtimeCity ? LOCATION_TREE[province]?.[realtimeCity] ?? [] : [];
  const selectProvince = (value: string) => {
    setProvince(value);
    setRealtimeCity('');
    setDistrict('');
    setScope('province');
  };
  const selectCity = (value: string) => {
    setRealtimeCity(value);
    setDistrict('');
    setScope('city');
  };
  const selectDistrict = (value: string) => {
    setDistrict(value);
    setScope(value ? 'district' : 'city');
  };

  function renderRealtimeCard(hospital: RealtimeSearchResponse['results'][number], index: number) {
    const breakdown = hospital.score_breakdown ?? {};
    return (
      <article className={styles.card} key={hospital.id}>
        <div className={styles.cardRank}>第 {index + 1} 名 <b>综合评分 {hospital.score}</b></div>
        <h3>{hospital.name}</h3>
        <dl className={styles.hospitalFacts}>
          <div><dt>核心优势</dt><dd>{hospital.core_advantages || '暂无公开资料'}</dd></div>
          <div><dt>匹配理由</dt><dd>{hospital.match_reason || '根据症状、科室和地理范围综合匹配。'}</dd></div>
          <div><dt>推荐科室</dt><dd>{realtimeResponse?.directions.length ? realtimeResponse.directions.join('、') : '暂无公开科室资料'}</dd></div>
          <div><dt>医院地址</dt><dd>{hospital.address || hospital.city || '暂无公开地址资料'}</dd></div>
        </dl>
        <details className={styles.scoreDetails}>
          <summary>评分详情</summary>
          <dl>
            {Object.entries(breakdown).map(([key, value]) => <div key={key}><dt>{({ specialty: '专科匹配度', hospital_strength: '医院专科实力', geography: '地理位置', completeness: '资料完整度', accessibility: '就医便利性' } as Record<string, string>)[key] || key}</dt><dd>{value}</dd></div>)}
          </dl>
          <p className={styles.evidenceStatus}>{hospital.evidence_status || '暂无公开资料'}</p>
          {hospital.source_urls?.length ? <div className={styles.sourceLinks}>{hospital.source_urls.slice(0, 3).map((url) => <a key={url} href={url} target="_blank" rel="noreferrer">查看资料来源</a>)}</div> : null}
        </details>
        <button type="button" onClick={() => void openDetail(hospital.id)}>查看医院详情</button>
      </article>
    );
  }

  return (
    <main className={styles.page} inert={showEmergency}>
      <nav className={styles.nav} aria-label="主导航">
        <span className={styles.brand}>医途</span>
        <span>医院信息导航</span>
        <div className={styles.navLinks} aria-label="页面导航"><a href="#match">智能匹配</a><a href="#results">医院目录</a><a href="#guide">使用说明</a></div>
        <button type="button" className={styles.clearProfile} onClick={clearLocalData}>清除本机数据</button>
      </nav>

      <section className={styles.hero} aria-labelledby="page-title">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>演示医院信息匹配</p>
          <h1 id="page-title">找到更适合的医院信息</h1>
          <p className={styles.disclaimer}>本工具仅供查找演示医院信息，不提供诊断、治疗或疗效建议。</p>
        </div>
        <div className={styles.heroStats} aria-label="平台数据概览"><div><strong>31</strong><span>个省级行政区覆盖规划</span></div><div><strong>3</strong><span>项核心匹配维度</span></div></div>
        <div className={styles.artwork} aria-hidden="true"><i /><b /><em /></div>
      </section>

      <section id="match" className={`${styles.search} ${styles.match}`} aria-label="医院信息匹配">
        <div className={styles.panelHeading}><span>01</span><h2>告诉我们你的需求</h2></div>
        <form onSubmit={submitRealtime} className={styles.form}>
          <label htmlFor="query">症状或疾病</label>
          <textarea className={styles.query} id="query" name="query" value={realtimeQuery} onChange={(event) => { setRealtimeQuery(event.target.value); setQuery(event.target.value); }} required maxLength={500} rows={3} />
          <div className={styles.formGrid}>
            <label htmlFor="province-main">省份<select id="province-main" value={province} onChange={(event) => selectProvince(event.target.value)} required><option value="">请选择省份</option>{Object.keys(LOCATION_TREE).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="city-main">城市<select id="city-main" value={realtimeCity} onChange={(event) => selectCity(event.target.value)} disabled={!province} required><option value="">{province ? '请选择城市' : '请先选择省份'}</option>{cityOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="district-main">市区（可选）<select id="district-main" value={district} onChange={(event) => selectDistrict(event.target.value)} disabled={!realtimeCity}><option value="">{realtimeCity ? '请选择区县' : '请先选择城市'}</option>{districtOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="scope-main">排名范围<select id="scope-main" value={scope} onChange={(event) => setScope(event.target.value as RealtimeSearchResponse['scope'])}><option value="district">市区级</option><option value="city">市级</option><option value="province">省级</option><option value="national">全国</option></select></label>
          </div>
          <div className={styles.locationTools}><button type="button" onClick={locateUser} disabled={locating}>{locating ? '正在定位…' : '使用当前位置'}</button>{locationNotice && <span role="status">{locationNotice}</span>}</div>
          <label htmlFor="city">所在城市</label>
          <select className={styles.city} id="city" name="city" value={city} onChange={(event) => setCity(event.target.value)}><option value="">不限城市</option><option value="上海">上海</option><option value="杭州">杭州</option></select>
          <label htmlFor="priority">匹配偏好</label>
          <select className={styles.priority} id="priority" name="priority" value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}><option value="overall">综合信息</option><option value="specialty">专科方向</option><option value="convenience">就近便利</option></select>
          <div className={styles.aiConsent}>
            <label htmlFor="ai-consent"><input id="ai-consent" type="checkbox" checked={aiConsent} onChange={(event) => setAiConsent(event.target.checked)} />同意将本次描述发送给 DeepSeek 进行就医方向整理</label>
            <p>AI 仅整理就医方向，不提供诊断或治疗建议。</p>
          </div>
          {!realtimeConsent && <p className={styles.consentRequired} role="alert">请先同意使用 DeepSeek 进行就医方向整理。</p>}
          <button ref={submitButtonRef} type="submit" disabled={realtimeLoading || !realtimeConsent}>{realtimeLoading && <span className={styles.buttonSpinner} aria-hidden="true" />}{realtimeLoading ? '正在匹配…' : '开始匹配'}</button>
        </form>
        <div className={styles.quickTags}><span>常见就医方向：</span><button type="button" onClick={() => setQuery('冠心病')}>心血管疾病</button><button type="button" onClick={() => setQuery('儿童发热咳嗽')}>儿童发热咳嗽</button><button type="button" onClick={() => setQuery('肿瘤治疗')}>肿瘤治疗</button><button type="button" onClick={() => setQuery('关节疼痛')}>关节疼痛</button></div>
        {realtimeLoading && <div className={styles.loadingState} role="status" aria-live="polite"><span className={styles.loadingBars} aria-hidden="true"><i /><i /><i /></span><div><strong>正在检索公开资料</strong><p>正在根据症状、位置和排名范围整理医院信息，请稍候。</p></div></div>}
        {realtimeError && <p className={styles.notice} role="alert">{realtimeError}</p>}
        {realtimeResponse && realtimeResponse.status !== 'OK' && <p className={styles.notice}>{realtimeResponse.status === 'SEARCH_UNAVAILABLE' ? '暂时无法连接公开资料搜索服务，请稍后重试。你的输入没有问题。' : realtimeResponse.status === 'NO_RESULTS' ? '暂未找到符合当前范围的医院资料，请扩大排名范围或补充症状描述。' : '当前描述可能需要急诊处理，请优先联系 120。'}</p>}
        {realtimeResponse?.status === 'OK' && <><p className={styles.scopeNote}>当前排名范围：{({ district: '市区级', city: '市级', province: '省级', national: '全国' } as Record<string, string>)[realtimeResponse.scope]}。系统已按用户选择的最小地址范围检索公开资料。</p>{realtimeResponse.fallback_message && <div className={styles.fallbackNotice}><span>{realtimeResponse.fallback_message}</span>{realtimeResponse.fallback_scope && <button type="button" onClick={() => void switchRealtimeScope(realtimeResponse.fallback_scope!)}>切换至更高一级范围</button>}</div>}<div className={styles.cards} aria-label="实时医院排名">{realtimeResponse.results.map(renderRealtimeCard)}</div></>}
        {detail && <aside className={styles.detailPanel} aria-label="医院详情"><button type="button" onClick={() => setDetail(null)}>关闭详情</button><h3>{detail.name}</h3><p>{detail.introduction || '暂无医院简介公开摘要。'}</p><h4>相关科室</h4><p>{detail.departments.length ? detail.departments.join('、') : '暂无结构化科室信息。'}</p><h4>主要医生</h4><p>{detail.doctors.length ? detail.doctors.join('、') : '暂无可靠的公开医生信息。'}</p>{detail.registration_url && <a href={detail.registration_url} target="_blank" rel="noreferrer">前往官方挂号服务</a>}</aside>}
      </section>

      <section className={styles.search} aria-labelledby="realtime-title">
        <div className={styles.panelHeading}><span>实时</span><h2 id="realtime-title">公开资料医院排名</h2></div>
        <p>输入症状或疾病，检索公开资料并按综合评分返回前 10 家医院，默认按市区范围。</p>
        <form onSubmit={submitRealtime} className={styles.form}>
          <label htmlFor="realtime-query">实时症状或疾病</label>
          <textarea id="realtime-query" value={realtimeQuery} onChange={(event) => setRealtimeQuery(event.target.value)} required maxLength={500} rows={3} placeholder="例如：持续胸痛、膝关节疼痛" />
          <div className={styles.formGrid}>
            <label htmlFor="province">省份<input id="province" value={province} onChange={(event) => setProvince(event.target.value)} required /></label>
            <label htmlFor="realtime-city">城市<input id="realtime-city" value={realtimeCity} onChange={(event) => setRealtimeCity(event.target.value)} required /></label>
            <label htmlFor="district">市区<input id="district" value={district} onChange={(event) => setDistrict(event.target.value)} required /></label>
            <label htmlFor="scope">排名范围<select id="scope" value={scope} onChange={(event) => setScope(event.target.value as RealtimeSearchResponse['scope'])}><option value="district">市区级</option><option value="city">市级</option><option value="province">省级</option><option value="national">全国</option></select></label>
          </div>
          <label className={styles.aiConsent} htmlFor="realtime-consent"><input id="realtime-consent" type="checkbox" checked={realtimeConsent} onChange={(event) => setRealtimeConsent(event.target.checked)} />允许 DeepSeek 整理就医方向（可选）</label>
          <button type="submit" disabled={realtimeLoading || !realtimeConsent}>{realtimeLoading ? '正在检索公开资料…' : '开始实时匹配'}</button>
        </form>
        {realtimeError && <p className={styles.notice} role="alert">{realtimeError}</p>}
        {realtimeResponse && realtimeResponse.status !== 'OK' && <p className={styles.notice}>{realtimeResponse.status === 'SEARCH_UNAVAILABLE' ? '暂时无法连接公开资料搜索服务，请稍后重试。你的输入没有问题。' : realtimeResponse.status === 'NO_RESULTS' ? '暂未找到符合当前范围的医院资料，请扩大排名范围或补充症状描述。' : '当前描述可能需要急诊处理，请优先联系 120。'}</p>}
        {realtimeResponse?.status === 'OK' && <div className={styles.cards} aria-label="实时医院排名">{realtimeResponse.results.map(renderRealtimeCard)}</div>}
        {detail && <aside className={styles.detailPanel} aria-label="医院详情"><button type="button" onClick={() => setDetail(null)}>关闭详情</button><h3>{detail.name}</h3><p>{detail.introduction || '暂无医院简介公开摘要。'}</p><h4>相关科室</h4><p>{detail.departments.length ? detail.departments.join('、') : '暂无结构化科室信息。'}</p><h4>主要医生</h4><p>{detail.doctors.length ? detail.doctors.join('、') : '暂无可靠的公开医生信息。'}</p>{detail.registration_url && <a href={detail.registration_url} target="_blank" rel="noreferrer">前往官方挂号服务</a>}</aside>}
      </section>

      <section className={styles.overview} aria-label="平台信息概览">
        <div><span>覆盖规划</span><strong>31</strong><small>个省级行政区</small></div>
        <div><span>核心匹配维度</span><strong>03</strong><small>专科 · 便利 · 数据时效</small></div>
        <div><span>使用方式</span><strong>3 min</strong><small>描述情况、比较医院、保存候选</small></div>
        <aside><b>就医前建议</b><p>推荐结果仅供信息参考，请通过医院官方渠道核实门诊与服务信息。</p></aside>
      </section>

      <section className={styles.guide} aria-labelledby="guide-title">
        <header><span>服务导航</span><h2 id="guide-title">把复杂选择，拆成清楚的三步</h2></header>
        <ol>
          <li><b>01</b><h3>描述情况</h3><p>输入症状、疾病或检查报告的关键结论。</p></li>
          <li><b>02</b><h3>设定偏好</h3><p>选择城市，并说明更看重专科还是便利。</p></li>
          <li><b>03</b><h3>比较与收藏</h3><p>查看数据日期和理由，再保存候选医院。</p></li>
        </ol>
      </section>

      {error && <p className={styles.notice} role="alert">{error}</p>}

      {(recommendations.length > 0 || hasNoMatches) && (
        <section aria-labelledby="recommendations-title" className={styles.results}>
          <header className={styles.resultHeader}><div><span>02</span><h2 id="recommendations-title">匹配结果</h2></div><p>{recommendations.length > 0 ? '推荐医院' : '继续探索其他方向'}</p></header>
          {matchStatus && <div className={styles.matchStatus}><strong>{matchStatus.title}</strong>{matchStatus.summary && <p>{matchStatus.summary}</p>}</div>}
          <p>以下为演示数据生成的信息匹配结果，请通过官方渠道核实。</p>
          {recommendations.length > 0 && <p className={styles.localOnly}>收藏仅保存在此浏览器中。</p>}
          {hasNoMatches && <article className={styles.noMatch}><div className={styles.mapPanel} aria-hidden="true"><span /><i /><b /></div><div><h3>暂未匹配到已审核医院</h3><p>可尝试补充更具体的症状、所在城市或匹配偏好。请通过官方渠道查询医院信息。</p></div></article>}
          {recommendations.length > 0 && <div className={styles.cards}>
            {recommendations.map((hospital) => (
              <article className={styles.card} key={hospital.id}>
                <h3>{hospital.name}</h3>
                <p>{hospital.city} · {hospital.demo_label || '演示数据'}</p>
                <dl>
                  <div><dt>专科方向</dt><dd>{hospital.specialties.join('、')}</dd></div>
                  <div><dt>匹配分数</dt><dd>{hospital.score}</dd></div>
                  <div><dt>分数说明</dt><dd>{hospital.score_reasons.join('；')}</dd></div>
                  <div><dt>来源日期</dt><dd>{hospital.source_date}</dd></div>
                </dl>
                <button
                  type="button"
                  className={styles.favorite}
                  aria-pressed={favorites.includes(hospital.id)}
                  aria-label={`${favorites.includes(hospital.id) ? '取消收藏' : '收藏'} ${hospital.name}`}
                  onClick={() => toggleFavorite(hospital.id)}
                >
                  {favorites.includes(hospital.id) ? '已收藏' : '收藏'}
                </button>
              </article>
            ))}
          </div>}
        </section>
      )}

      {pendingCandidates && pendingCandidates.length > 0 && (
        <section aria-labelledby="pending-candidates-title" className={styles.pendingCandidates}>
          <header className={styles.pendingHeader}><div><span>03</span><h2 id="pending-candidates-title">待人工核验的候选医疗机构</h2></div></header>
          <p>{hasDirectionPlaceholders
            ? 'AI 方向占位仅用于流程体验，不代表真实医疗机构；待补充或人工核验。'
            : '这些候选医疗机构由 AI 生成，仅用于流程体验；请通过医疗机构官网或主管部门核验后再作为就医信息参考。'}
          </p>
          <div className={styles.pendingCards}>
            {pendingCandidates.map((candidate) => (
              <article className={styles.pendingCard} key={`${candidate.name}-${candidate.city}`}>
                <h3>{candidate.name}</h3>
                <p>{candidate.city}</p>
                <dl>
                  <div><dt>就医方向</dt><dd>{candidate.direction}</dd></div>
                  <div><dt>候选理由</dt><dd>{candidate.reason}</dd></div>
                </dl>
                {candidate.placeholder && <p>非真实机构名称</p>}
                <span>{candidate.placeholder ? 'AI 方向占位' : '待人工核验'}</span>
              </article>
            ))}
          </div>
        </section>
      )}

      {showEmergency && (
        <dialog
          ref={emergencyDialogRef}
          aria-labelledby="emergency-title"
          className={styles.dialog}
          onCancel={(event) => event.preventDefault()}
          onKeyDown={trapEmergencyFocus}
        >
          <h2 id="emergency-title">请立即急诊或拨打 120</h2>
          <p>当前描述可能需要紧急处理。此工具不能替代紧急医疗服务。</p>
          <button ref={acknowledgementRef} type="button" onClick={closeEmergency}>我已了解，仍查看医院信息</button>
        </dialog>
      )}
    </main>
  );
}
