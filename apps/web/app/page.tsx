'use client';

import { CSSProperties, FormEvent, KeyboardEvent, useEffect, useRef, useState } from 'react';

import { AIMatchResponse, FeedbackCategory, MatchApiError, MatchResponse, RealtimeHospitalDetail, RealtimeSearchResponse, SymptomClarificationAnswer, SymptomClarificationResponse, TriageResponse, aiMatchHospitals, clarifySymptoms, getRealtimeHospitalDetail, matchHospitals, realtimeSearchHospitals, triageSymptoms } from '../lib/api';
import { addFavorite, clearProfile, FavoriteHospital, getProfile, removeFavorite } from '../lib/local-profile';
import { formatLikelihood } from '../lib/formatters';
import { getDisplayedResultScore } from '../lib/result-score';
import { FavoriteDrawer, FavoriteHospitalList } from './favorite-drawer';
import FeedbackAdminPage from './feedback-admin';
import FeedbackDialog from './feedback-dialog';
import GuidedIntake, { GuidedSearchInput } from './guided-intake';
import UsageGuidePage from './usage-guide';
import HospitalDirectoryPage from './hospital-directory';
import styles from './page.module.css';
import provinceData from '../data/province.json';
import cityData from '../data/city.json';
import areaData from '../data/area.json';

const FALLBACK_COPY = '匹配服务暂时不可用。请查询当地卫生健康部门地址与医院官方站点；如情况紧急，请立即急诊或拨打 120。';
const CUSTOM_CLARIFICATION_OPTION = '以上都不符合，我自己填写';

function realtimeCacheKey(direction: string | null | undefined, scope: RealtimeSearchResponse['scope'], ignoreGeography = false) {
  return `${direction?.trim() || 'default'}:${scope}:${ignoreGeography ? 'no-geo' : 'geo'}`;
}

const SCORE_LABELS: Record<string, string> = {
  specialty: '专科实力',
  hospital_strength: '医院综合实力',
  public_capability: '医院综合实力',
  geography: '地理位置',
  completeness: '资料完整度',
  freshness_completeness: '资料时效与完整度',
  accessibility: '就医便利性',
  official_service: '官方服务信息',
};

const SCOPE_LABELS: Record<RealtimeSearchResponse['scope'], string> = {
  district: '区/县级',
  city: '市级',
  province: '省级',
  national: '全国',
};

type DisplayEvidence = NonNullable<RealtimeSearchResponse['results'][number]['specialty_evidence']>[number] & {
  source_urls?: string[];
};

function normalizeSpecialtyCapabilityLevel(value: string | undefined) {
  const level = value?.trim() || '';
  return /^(国家级|国家级重点|国家临床重点|国家重点)/.test(level) ? '国家级重点' : level;
}

function mergeSpecialtyCapabilityEvidence(items: DisplayEvidence[]) {
  const grouped = new Map<string, DisplayEvidence>();
  for (const item of items) {
    const specialty = item.department?.trim() || item.specialty?.trim() || '';
    const level = normalizeSpecialtyCapabilityLevel(item.strength_level);
    const key = `${specialty}|${level}`;
    const sourceUrls = [...new Set([...(item.source_urls ?? []), item.source?.trim() || ''].filter(Boolean))];
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, { ...item, strength_level: level, source_urls: sourceUrls });
      continue;
    }
    grouped.set(key, {
      ...existing,
      source_urls: [...new Set([...(existing.source_urls ?? []), ...sourceUrls])],
      diagnosis_scope: existing.diagnosis_scope || item.diagnosis_scope,
      verification_status: [...new Set([existing.verification_status, item.verification_status].filter(Boolean))].join('、'),
    });
  }
  return [...grouped.values()];
}

function formatScoreText(value: string) {
  return value
    .replace(/specialty/g, '专科实力')
    .replace(/hospital_strength|public_capability/g, '医院综合实力')
    .replace(/geography/g, '地理位置')
    .replace(/freshness_completeness/g, '资料时效与完整度')
    .replace(/completeness/g, '资料完整度')
    .replace(/accessibility/g, '就医便利性')
    .replace(/official_service/g, '官方服务信息')
    .replace(/\(weight\s*\d+\)/g, '');
}

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

export function scrollToResultScope(element: HTMLElement | null) {
  if (!element || typeof window === 'undefined') return;
  const top = Math.max(0, element.getBoundingClientRect().top + window.scrollY - 16);
  window.scrollTo({ top, behavior: 'smooth' });
}

export default function Page() {
  const [surface, setSurface] = useState<'landing' | 'guided' | 'results'>('landing');
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
  const [ignoreGeography, setIgnoreGeography] = useState(false);
  const [realtimeResponse, setRealtimeResponse] = useState<RealtimeSearchResponse | null>(null);
  const realtimeScopeCacheRef = useRef<Record<string, RealtimeSearchResponse>>({});
  const [districtSelectionRequired, setDistrictSelectionRequired] = useState(false);
  const [triageResponse, setTriageResponse] = useState<TriageResponse | null>(null);
  const [clarification, setClarification] = useState<SymptomClarificationResponse | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<SymptomClarificationAnswer[]>([]);
  const [clarificationChoice, setClarificationChoice] = useState('');
  const [clarificationCustomAnswer, setClarificationCustomAnswer] = useState('');
  const [selectedDirection, setSelectedDirection] = useState<string | null>(null);
  const [selectedResultDirectionKey, setSelectedResultDirectionKey] = useState<string | null>(null);
  const [hospitalTiers, setHospitalTiers] = useState<Array<'tertiary_a'>>(['tertiary_a']);
  const [realtimeLoading, setRealtimeLoading] = useState(false);
  const [scopeSwitching, setScopeSwitching] = useState(false);
  const [realtimeError, setRealtimeError] = useState<string | null>(null);
  const [locationNotice, setLocationNotice] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [detail, setDetail] = useState<RealtimeHospitalDetail | null>(null);
  const [favorites, setFavorites] = useState<string[]>([]);
  const [favoriteHospitals, setFavoriteHospitals] = useState<FavoriteHospital[]>([]);
  const [favoriteDrawerOpen, setFavoriteDrawerOpen] = useState(false);
  const [favoritePageOpen, setFavoritePageOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const submitButtonRef = useRef<HTMLButtonElement>(null);
  const acknowledgementRef = useRef<HTMLButtonElement>(null);
  const emergencyDialogRef = useRef<HTMLDialogElement>(null);
  const triagePanelRef = useRef<HTMLElement>(null);
  const scopeBarRef = useRef<HTMLDivElement>(null);
  const pendingScopeScrollRef = useRef(false);

  useEffect(() => {
    const profile = getProfile();
    setFavorites(profile.favorites);
    setFavoriteHospitals(profile.favoriteHospitals);
  }, []);

  if (typeof window !== 'undefined' && window.location.pathname === '/feedback-admin') {
    return <FeedbackAdminPage />;
  }

  if (typeof window !== 'undefined' && window.location.pathname === '/guide') {
    return <UsageGuidePage />;
  }

  if (typeof window !== 'undefined' && window.location.pathname === '/directory') {
    return <HospitalDirectoryPage />;
  }

  useEffect(() => {
    const missingIds = favorites.filter((id) => !favoriteHospitals.some((hospital) => hospital.id === id));
    if (!missingIds.length) return;
    let cancelled = false;
    void Promise.all(missingIds.map(async (id) => {
      try {
        return favoriteFromDetail(await getRealtimeHospitalDetail(id));
      } catch {
        return null;
      }
    })).then((snapshots) => {
      if (cancelled) return;
      let profile = getProfile();
      for (const snapshot of snapshots) {
        if (snapshot) profile = addFavorite(snapshot);
      }
      setFavorites(profile.favorites);
      setFavoriteHospitals(profile.favoriteHospitals);
    });
    return () => { cancelled = true; };
  }, [favorites, favoriteHospitals]);

  useEffect(() => {
    if (!showEmergency) return;

    const dialog = emergencyDialogRef.current;
    if (dialog && !dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    }
    acknowledgementRef.current?.focus();
  }, [showEmergency]);

  useEffect(() => {
    if (!triageResponse || realtimeResponse || surface === 'results') return;

    const frame = window.requestAnimationFrame(() => {
      const panel = triagePanelRef.current;
      if (panel && typeof panel.scrollIntoView === 'function') {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [triageResponse, realtimeResponse]);

  useEffect(() => {
    if (!pendingScopeScrollRef.current || realtimeResponse?.status !== 'OK') return;
    const frame = window.requestAnimationFrame(() => {
      scrollToResultScope(scopeBarRef.current);
      pendingScopeScrollRef.current = false;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [realtimeResponse]);

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

  async function searchRealtime(
    nextScope: RealtimeSearchResponse['scope'],
    confirmedDirection = selectedDirection,
    preserveCurrent = false,
    nextDistrict = district,
    nextCity = realtimeCity,
    nextProvince = province,
    isScopeSwitch = false,
    nextIgnoreGeography = ignoreGeography,
  ) {
    const normalizedDistrict = nextDistrict.trim();
    const normalizedCity = nextCity.trim();
    const normalizedProvince = nextProvince.trim();
    if (nextScope === 'district' && !normalizedDistrict) {
      setDistrictSelectionRequired(true);
      return;
    }
    setRealtimeError(null);
    setScopeSwitching(isScopeSwitch);
    if (!preserveCurrent) {
      pendingScopeScrollRef.current = true;
      setRealtimeResponse(null);
      setDetail(null);
    }
    setRealtimeLoading(true);
    try {
      const { result, scope: resolvedScope } = await searchRealtimeWithFallback({
        query: realtimeQuery,
        location: { province: normalizedProvince, city: normalizedCity, district: normalizedDistrict || normalizedCity },
        location_level: normalizedDistrict ? 'district' : 'city',
        initialScope: nextScope,
        confirmedDirection,
        aiConsent: realtimeConsent,
        ignoreGeography: nextIgnoreGeography,
      });
      setScope(resolvedScope);
      setRealtimeResponse(result);
      setDistrictSelectionRequired(false);
    } catch (requestError) {
      setRealtimeError(requestError instanceof MatchApiError && requestError.status === 503
        ? '公开资料搜索暂时不可用，请稍后重试。'
        : '实时搜索暂时失败，请检查服务是否已启动。');
    } finally {
      setScopeSwitching(false);
      setRealtimeLoading(false);
    }
  }

  async function searchRealtimeWithFallback({
    query: nextQuery,
    location,
    location_level,
    initialScope,
    confirmedDirection,
    aiConsent,
    ignoreGeography: nextIgnoreGeography,
  }: {
    query: string;
    location: { province: string; city: string; district: string };
    location_level: 'city' | 'district';
    initialScope: RealtimeSearchResponse['scope'];
    confirmedDirection: string | null | undefined;
    aiConsent: boolean;
    ignoreGeography: boolean;
  }) {
    let currentScope = initialScope;
    const visitedScopes = new Set<RealtimeSearchResponse['scope']>();

    while (!visitedScopes.has(currentScope)) {
      visitedScopes.add(currentScope);
      const cacheKey = realtimeCacheKey(confirmedDirection, currentScope, nextIgnoreGeography);
      const cachedResponse = realtimeScopeCacheRef.current[cacheKey];
      const result = cachedResponse ?? await realtimeSearchHospitals({
        query: nextQuery,
        location,
        location_level,
        scope: currentScope,
        ai_consent: aiConsent,
        confirmed_direction: confirmedDirection || undefined,
        hospital_tiers: hospitalTiers,
        ignore_geography: nextIgnoreGeography,
      });
      realtimeScopeCacheRef.current[cacheKey] = result;

      if (result.status !== 'NO_RESULTS' || !result.fallback_scope || visitedScopes.has(result.fallback_scope)) {
        return { result, scope: currentScope };
      }
      currentScope = result.fallback_scope;
    }

    throw new Error('Unable to resolve a hospital search scope.');
  }

  async function submitRealtime(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!realtimeConsent) {
      setRealtimeError('请先勾选“同意使用智能体”后再开始匹配。');
      return;
    }
    if (hospitalTiers.length === 0) {
      setRealtimeError('请至少选择一个可用的医院等级。');
      return;
    }
    if (!triageResponse && !clarification) {
      setRealtimeError(null);
      realtimeScopeCacheRef.current = {};
      setTriageResponse(null);
      setSelectedDirection(null);
      setSelectedResultDirectionKey(null);
      setClarificationAnswers([]);
      setClarificationChoice('');
      setClarificationCustomAnswer('');
      setRealtimeLoading(true);
      try {
        const triage = await triageSymptoms({ query: realtimeQuery, ai_consent: true });
        setTriageResponse(triage);
        const needsClarification = !triage.explicit_disease_input
          && (triage.directions.length !== 1 || triage.directions[0].likelihood === '待评估');
        if (needsClarification) {
          const next = await clarifySymptoms({ query: realtimeQuery, answers: [], ai_consent: true });
          if (next.status === 'NEEDS_CLARIFICATION') setClarification(next);
        }
      } catch {
        setRealtimeError('暂时无法完成症状分流，请稍后重试。');
      } finally {
        setRealtimeLoading(false);
      }
      return;
    }
    await searchRealtime(scope);
  }

  async function submitClarificationAnswer() {
    if (!clarification?.question || !clarificationChoice) return;
    const answerValue = clarificationChoice === CUSTOM_CLARIFICATION_OPTION ? clarificationCustomAnswer.trim() : clarificationChoice;
    if (!answerValue) return;
    const nextAnswers = [...clarificationAnswers, { question_id: clarification.question.id, value: answerValue }];
    setClarificationAnswers(nextAnswers);
    setClarificationChoice('');
    setClarificationCustomAnswer('');
    setRealtimeLoading(true);
    try {
      const next = await clarifySymptoms({ query: realtimeQuery, answers: nextAnswers, ai_consent: true });
      if (next.status === 'EMERGENCY') {
        setRealtimeError(next.urgent_warning);
        setClarification(null);
      } else if (next.status === 'COMPLETE') {
        setClarification(null);
        setTriageResponse({ summary: '根据补充信息，当前结果更符合以下就医方向。', directions: next.directions, urgent_warning: next.urgent_warning, disclaimer: '以上是健康信息整理，不是医学诊断。', is_diagnosis: false, ai_used: false });
      } else setClarification(next);
    } catch { setRealtimeError('暂时无法完成补充问题，请稍后重试。'); }
    finally { setRealtimeLoading(false); }
  }

  async function confirmDirection(direction: TriageResponse['directions'][number]) {
    setSelectedDirection(direction.department);
    setSelectedResultDirectionKey(direction.key);
    await searchRealtime(scope, direction.department);
  }

  async function switchRealtimeScope(nextScope: RealtimeSearchResponse['scope']) {
    setScope(nextScope);
    if (nextScope === 'district' && !district.trim()) {
      setDistrictSelectionRequired(true);
      return;
    }
    if (nextScope === realtimeResponse?.scope && !realtimeLoading) return;
    await searchRealtime(nextScope, selectedDirection, true, district, realtimeCity, province, true);
  }

  async function switchResultDirection(direction: TriageResponse['directions'][number]) {
    if (direction.key === selectedResultDirectionKey && realtimeResponse) return;
    setSelectedDirection(direction.department);
    setSelectedResultDirectionKey(direction.key);
    setDetail(null);
    await searchRealtime(scope, direction.department, true);
  }

  function selectResultProvince(value: string) {
    realtimeScopeCacheRef.current = {};
    setProvince(value);
    setRealtimeCity('');
    setDistrict('');
    setDistrictSelectionRequired(false);
    setScope('city');
  }

  function selectResultCity(value: string) {
    realtimeScopeCacheRef.current = {};
    setRealtimeCity(value);
    setDistrict('');
    setDistrictSelectionRequired(false);
    setScope('city');
    if (value) void searchRealtime('city', selectedDirection, true, '', value, province);
  }

  function selectResultDistrict(value: string) {
    realtimeScopeCacheRef.current = {};
    setDistrict(value);
    if (value && (districtSelectionRequired || scope === 'district')) {
      void searchRealtime('district', selectedDirection, true, value, realtimeCity, province);
    }
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
    if (detail?.id === id) {
      setDetail(null);
      return;
    }
    const hospital = realtimeResponse?.results.find((item) => item.id === id);
    if (!hospital) return;
    setDetail({
      id: hospital.id,
      name: hospital.name,
      city: hospital.city,
      address: hospital.address || hospital.city,
      introduction: hospital.core_advantages || hospital.match_reason || null,
      departments: hospital.specialties || (hospital.department ? [hospital.department] : []),
      doctors: [],
      registration_url: hospital.registration_url,
      official_website_url: hospital.official_website_url,
      wechat_appointment: hospital.wechat_appointment || `${hospital.name}公众号`,
      sources: hospital.sources,
      fetched_at: hospital.fetched_at,
    });
    try {
      setDetail(await getRealtimeHospitalDetail(id));
    } catch {
      setRealtimeError(null);
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
    setFavoriteHospitals([]);
    setFavoriteDrawerOpen(false);
  }

  function toggleFavoriteId(hospitalId: string) {
    const profile = favorites.includes(hospitalId)
      ? removeFavorite(hospitalId)
      : addFavorite(hospitalId);
    setFavorites(profile.favorites);
    setFavoriteHospitals(profile.favoriteHospitals);
  }

  function favoriteFromResult(hospital: RealtimeSearchResponse['results'][number]): FavoriteHospital {
    return {
      id: hospital.id,
      name: hospital.name,
      city: hospital.city,
      tier: hospital.tier || '',
      address: hospital.address || '',
      score: Number.isFinite(hospital.score) ? hospital.score : null,
      department: hospital.department || realtimeResponse?.directions.join('、') || '',
      officialWebsiteUrl: hospital.official_website_url || null,
    };
  }

  function favoriteFromDetail(hospital: RealtimeHospitalDetail): FavoriteHospital {
    return {
      id: hospital.id,
      name: hospital.name,
      city: hospital.city,
      tier: '',
      address: hospital.address || '',
      score: null,
      department: hospital.departments.join('、'),
      officialWebsiteUrl: hospital.official_website_url || null,
    };
  }

  function toggleFavoriteHospital(hospital: RealtimeSearchResponse['results'][number]) {
    const profile = favorites.includes(hospital.id)
      ? removeFavorite(hospital.id)
      : addFavorite(favoriteFromResult(hospital));
    setFavorites(profile.favorites);
    setFavoriteHospitals(profile.favoriteHospitals);
  }

  function removeFavoriteHospital(hospitalId: string) {
    const profile = removeFavorite(hospitalId);
    setFavorites(profile.favorites);
    setFavoriteHospitals(profile.favoriteHospitals);
    if (detail?.id === hospitalId) setDetail(null);
  }

  async function openFavoriteDetail(hospitalId: string) {
    const snapshot = favoriteHospitals.find((hospital) => hospital.id === hospitalId);
    setFavoriteDrawerOpen(false);
    setFavoritePageOpen(true);
    if (snapshot) {
      setDetail({
        id: snapshot.id,
        name: snapshot.name,
        city: snapshot.city,
        address: snapshot.address,
        introduction: null,
        departments: snapshot.department ? snapshot.department.split('、') : [],
        doctors: [],
        registration_url: null,
        official_website_url: snapshot.officialWebsiteUrl,
        sources: [],
        fetched_at: new Date().toISOString(),
      });
    }
    try {
      setDetail(await getRealtimeHospitalDetail(hospitalId));
    } catch {
      setRealtimeError('暂时无法加载医院详情，请稍后重试。');
    }
  }

  function useQuickQuery(value: string) {
    setQuery(value);
    setRealtimeQuery(value);
    setTriageResponse(null);
    setSelectedDirection(null);
    setSelectedResultDirectionKey(null);
    setRealtimeResponse(null);
    realtimeScopeCacheRef.current = {};
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
    realtimeScopeCacheRef.current = {};
    setProvince(value);
    setRealtimeCity('');
    setDistrict('');
    setDistrictSelectionRequired(false);
    setScope('province');
  };
  const selectCity = (value: string) => {
    realtimeScopeCacheRef.current = {};
    setRealtimeCity(value);
    setDistrict('');
    setDistrictSelectionRequired(false);
    setScope('city');
  };
  const selectDistrict = (value: string) => {
    realtimeScopeCacheRef.current = {};
    setDistrict(value);
    setDistrictSelectionRequired(false);
    setScope(value ? 'district' : 'city');
  };
  const selectedResultDirection = triageResponse?.directions.find((item) => item.key === selectedResultDirectionKey) ?? null;
  const currentResultAddress = [province, realtimeCity, district].filter(Boolean).join(' · ') || '尚未选择地址';
  const renderResultLocation = () => <section className={styles.resultLocation} aria-label="当前选择的地址">
    <div className={styles.resultLocationSummary}>
      <span>当前选择的地址</span>
      <strong>{currentResultAddress}</strong>
    </div>
    <div className={styles.resultLocationControls}>
      <label className={styles.resultLocationSelect}>
        <span>省份</span>
        <select aria-label="选择省份" value={province} onChange={(event) => selectResultProvince(event.target.value)}>
          <option value="">请选择省份</option>
          {Object.keys(LOCATION_TREE).map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
      <label className={styles.resultLocationSelect}>
        <span>城市</span>
        <select aria-label="选择城市" value={realtimeCity} onChange={(event) => selectResultCity(event.target.value)} disabled={!province}>
          <option value="">{province ? '请选择城市' : '请先选择省份'}</option>
          {cityOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
      <label className={styles.resultLocationSelect}>
        <span>区县</span>
        <select aria-label="选择区县" value={district} onChange={(event) => selectResultDistrict(event.target.value)} disabled={!realtimeCity}>
          <option value="">{realtimeCity ? '请选择区县' : '请先选择城市'}</option>
          {districtOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>
    </div>
    <label className={styles.locationPreference} htmlFor="ignore-geography">
      <input id="ignore-geography" type="checkbox" checked={ignoreGeography} onChange={(event) => {
        const nextValue = event.target.checked;
        setIgnoreGeography(nextValue);
        realtimeScopeCacheRef.current = {};
        void searchRealtime(scope, selectedDirection, true, district, realtimeCity, province, true, nextValue);
      }} />
      <span>不考虑地理位置</span>
    </label>
    {districtSelectionRequired && <p className={styles.districtSelectionNotice} role="status">请先在当前地址中选择区县，再查看区/县级医院名单。当前医院列表会保留。</p>}
  </section>;

  async function completeGuidedSearch(input: GuidedSearchInput) {
    const nextScope = input.district ? 'district' : 'city';
    setQuery(input.query);
    setRealtimeQuery(input.query);
    setProvince(input.province);
    setRealtimeCity(input.city);
    setDistrict(input.district);
    setScope(nextScope);
    setPriority(input.priority);
    setSelectedDirection(input.direction || null);
    setSelectedResultDirectionKey(input.triage.directions.find((item) => item.department === input.direction)?.key ?? null);
    setTriageResponse(input.triage);
    setSurface('results');
    pendingScopeScrollRef.current = true;
    setRealtimeError(null);
    setRealtimeLoading(true);
    try {
      const { result, scope: resolvedScope } = await searchRealtimeWithFallback({
        query: input.query,
        location: { province: input.province, city: input.city, district: input.district || input.city },
        location_level: input.district ? 'district' : 'city',
        initialScope: nextScope,
        confirmedDirection: input.direction,
        aiConsent: true,
        ignoreGeography,
      });
      setScope(resolvedScope);
      setRealtimeResponse(result);
      setDistrictSelectionRequired(false);
    } catch (requestError) {
      setRealtimeError(requestError instanceof MatchApiError && requestError.status === 503
        ? '公开资料搜索暂时不可用，请稍后重试。'
        : '医院推荐暂时失败，请检查服务是否已启动。');
      throw requestError;
    } finally {
      setRealtimeLoading(false);
    }
  }

  if (surface === 'landing') {
    return <main className={styles.landingPage}>
      <div className={styles.landingTexture} aria-hidden="true"><span /><i /><b /></div>
      <header className={styles.landingBrand}>
        <div className={styles.landingIdentity}><span className={styles.brandMark}>+</span><span>医途</span><small>医院信息导航</small></div>
        <nav className={styles.landingNav} aria-label="首页导航">
          <a href="/directory">医院目录</a>
          <a href="/guide">使用说明</a>
        </nav>
      </header>
      <section className={`${styles.landingHero} ${styles.landingHeroCentered}`} aria-labelledby="landing-title">
        <p className={styles.landingEyebrow}>把就医选择，变得清楚一点</p>
        <h1 id="landing-title">先说清楚症状<br />再找到合适的医院</h1>
        <p className={styles.landingDescription}>医途会用简单的问题帮你确认疾病方向和推荐科室，再结合所在地整理医院列表与综合评分。</p>
        <button className={styles.landingStart} type="button" onClick={() => setSurface('guided')}>开始使用</button>
      </section>
      <footer className={styles.landingFooter}><span>公开资料整理</span><span>仅供就医信息参考</span><span>不替代医生诊断</span></footer>
    </main>;
  }

  if (surface === 'guided') {
    return <GuidedIntake onComplete={completeGuidedSearch} onEmergency={(message) => setRealtimeError(message)} onBackToLanding={() => setSurface('landing')} />;
  }

  if (favoritePageOpen) {
    return <main className={styles.page}>
      <nav className={styles.nav} aria-label="主导航">
        <span className={styles.brand}>医途</span>
        <span>医院信息导航</span>
        <div className={styles.navLinks} aria-label="页面导航"><a href="#favorites">收藏医院</a></div>
        <button type="button" className={styles.feedbackNavButton} onClick={() => setFeedbackOpen(true)}>信息反馈</button>
        <button type="button" className={styles.favoriteNavButton} aria-current="page" onClick={() => setFavoriteDrawerOpen(true)}>收藏夹 <span>{favorites.length}</span></button>
        <button type="button" className={styles.clearProfile} onClick={clearLocalData}>清除本机数据</button>
      </nav>
      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
      <section id="favorites" className={styles.favoritePage} aria-labelledby="favorites-title">
        <header className={styles.favoritePageHeader}>
          <div><span>已保存医院</span><h1 id="favorites-title">收藏医院</h1><p>收藏内容仅保存在当前浏览器中。</p></div>
          <button type="button" onClick={() => setFavoritePageOpen(false)}>返回医院推荐</button>
        </header>
        <FavoriteHospitalList favorites={favoriteHospitals} variant="page" onRemove={removeFavoriteHospital} onOpenDetail={(id) => void openFavoriteDetail(id)} />
        {detail && <section className={styles.favoriteDetail} aria-label={`${detail.name}医院详情`}>
          <header><div><span>医院详情</span><h2>{detail.name}</h2></div><button type="button" aria-label="关闭医院详情" title="关闭详情" onClick={() => setDetail(null)}>×</button></header>
          <p>{detail.introduction || '暂无医院简介公开摘要。'}</p>
          {detail.departments.length ? <p><b>相关科室：</b>{detail.departments.join('、')}</p> : null}
          <div>{detail.official_website_url && <a href={detail.official_website_url} target="_blank" rel="noreferrer">前往医院官网 ↗</a>}{detail.sources?.[0]?.url && <a href={detail.sources[0].url} target="_blank" rel="noreferrer">查看公开来源 ↗</a>}</div>
        </section>}
      </section>
      <FavoriteDrawer open={favoriteDrawerOpen} favorites={favoriteHospitals} onClose={() => setFavoriteDrawerOpen(false)} onExpand={() => setFavoriteDrawerOpen(false)} onRemove={removeFavoriteHospital} onOpenDetail={(id) => void openFavoriteDetail(id)} />
    </main>;
  }

  function renderRealtimeCard(hospital: RealtimeSearchResponse['results'][number], index: number) {
    const resultScore = getDisplayedResultScore({
      ...hospital,
      score_breakdown: {
      ...(hospital.score_breakdown ?? {}),
      official_service: hospital.official_website_url || hospital.registration_url ? 100 : 60,
      },
    }, { ignoreGeography });
    const breakdown = resultScore.breakdown;
    const isExpanded = detail?.id === hospital.id;
    const evidenceItems: DisplayEvidence[] = (hospital.specialty_evidence ?? []).filter((evidence, evidenceIndex, allEvidence) => {
      const evidenceKey = [
        evidence.year ?? '', evidence.rank ?? evidence.tier ?? '',
        evidence.specialty?.trim() || evidence.department?.trim() || '',
        evidence.ranking_source_name?.trim() || evidence.ranking_name?.trim() || '',
        evidence.strength_level?.trim() || '', evidence.source?.trim() || '',
      ].join('|');
      return allEvidence.findIndex((candidate) => [
        candidate.year ?? '', candidate.rank ?? candidate.tier ?? '',
        candidate.specialty?.trim() || candidate.department?.trim() || '',
        candidate.ranking_source_name?.trim() || candidate.ranking_name?.trim() || '',
        candidate.strength_level?.trim() || '', candidate.source?.trim() || '',
      ].join('|') === evidenceKey) === evidenceIndex;
    });
    const specialtyCapabilityEvidence = mergeSpecialtyCapabilityEvidence(evidenceItems.filter((evidence) => Boolean(
      (evidence.department?.trim() || evidence.specialty?.trim()) && !evidence.rank,
    ))).slice(0, 2);
    const specialtyRankingEvidence = evidenceItems.filter((evidence) => Boolean(
      evidence.rank && (evidence.department?.trim() || evidence.specialty?.trim()),
    )).slice(0, 2);
    const hospitalStrengthEvidence = evidenceItems.filter((evidence) => Boolean(
      evidence.rank && !(evidence.department?.trim() || evidence.specialty?.trim()),
    )).slice(0, 1);
    const hasSpecialtyEvidence = resultScore.hasDirectSpecialtyEvidence;
    const sourceLabel = (source: RealtimeSearchResponse['results'][number]['sources'][number]) => {
      const title = source.title?.trim();
      if (title && title !== hospital.name) return title;
      try {
        return new URL(source.url).hostname.replace(/^www\./i, '');
      } catch {
        return '资料来源';
      }
    };
    const renderEvidenceRows = (items: typeof evidenceItems) => items.map((evidence, evidenceIndex) => {
        const evidenceSources = [...new Set([...(evidence.source_urls ?? []), evidence.source || hospital.source_urls?.[0] || ''].filter(Boolean))];
        const sourceName = evidence.ranking_source_name?.trim() || evidence.ranking_name?.trim() || '';
        const scopeName = evidence.ranking_scope?.trim() || evidence.scope?.trim() || '';
        const specialtyName = evidence.specialty?.trim() || evidence.department?.trim() || '';
        const isCapability = Boolean(specialtyName && !evidence.rank);
        const defaultTitle = specialtyName
          ? `${scopeName}${specialtyName}专科排名`
          : `${scopeName || '全国'}综合排名`;
        const titleText = sourceName || defaultTitle;
        const evidenceYear = Number(evidence.year) > 0 && !titleText.includes(String(evidence.year)) ? `${evidence.year}年` : '';
        const evidenceText = isCapability
          ? `${specialtyName} · ${evidence.strength_level?.trim() || evidence.tier || '公开能力资料'}`
          : `${evidenceYear}${titleText}${evidence.rank ? `第${evidence.rank}名` : (evidence.tier || '公开资质')}`;
        return <div key={`${titleText}-${evidence.year || ''}-${evidence.rank || evidence.tier || evidenceIndex}`}>
          <span>· {evidenceText}</span>
          {evidenceSources.filter((source) => /^https?:\/\//i.test(source)).map((source) => <a key={source} href={source} target="_blank" rel="noopener noreferrer">查看来源</a>)}
          {!evidenceSources.some((source) => /^https?:\/\//i.test(source)) && <small>来源待核验</small>}
          <small>{sourceName ? `来源：${sourceName} · ` : ''}{evidence.verification_status || '待核验'}</small>
        </div>;
      });
    const renderEvidence = (
      title: string,
      items: typeof evidenceItems,
      className = '',
    ) => items.length ? <div className={`${styles.specialtyEvidence} ${className}`.trim()}>
      <strong>{title}</strong>
      {renderEvidenceRows(items)}
    </div> : null;
    const renderSpecialtyEvidence = () => (specialtyCapabilityEvidence.length || specialtyRankingEvidence.length) ? (
      <div className={styles.specialtyEvidence} aria-label="专科依据">
        {specialtyCapabilityEvidence.length ? <div className={styles.evidenceGroup}>
          <strong>专科能力依据</strong>
          {renderEvidenceRows(specialtyCapabilityEvidence)}
        </div> : null}
        {specialtyRankingEvidence.length ? <div className={styles.evidenceGroup}>
          <strong>专科排名依据</strong>
          {renderEvidenceRows(specialtyRankingEvidence)}
        </div> : null}
      </div>
    ) : null;
    return (
      <article className={styles.card} key={hospital.id}>
        <div className={styles.cardRank}><span>第 {index + 1} 名</span><b>综合评分 {resultScore.score}</b></div>
        <div className={styles.cardIdentity}>
          <div>
            <h3>{hospital.name}</h3>
            <p className={styles.cardMeta}>{hospital.tier || '三级甲等'} · {hospital.city}</p>
          </div>
        </div>
        <dl className={styles.hospitalFacts}>
          <div><dt>核心优势</dt><dd>{hospital.core_advantages || '暂无公开资料'}</dd></div>
          <div><dt>匹配理由</dt><dd>{formatScoreText(hospital.match_reason || '根据症状、科室和地理范围综合匹配。')}</dd></div>
          <div><dt>推荐科室</dt><dd>{realtimeResponse?.directions.length ? realtimeResponse.directions.join('、') : '暂无公开科室资料'}</dd></div>
          <div><dt>医院地址</dt><dd>{hospital.address || hospital.city || '暂无公开地址资料'}</dd></div>
        </dl>
        {renderSpecialtyEvidence()}
        {renderEvidence('医院综合实力依据', hospitalStrengthEvidence, styles.hospitalStrengthEvidence)}
        <details className={styles.scoreDetails}>
          <summary><span>评分详情</span><span className={styles.scoreToggle} aria-hidden="true" /></summary>
          <dl className={styles.scoreGrid}>
            {Object.entries(breakdown).map(([key, value]) => {
              const score = Math.max(0, Math.min(100, Number(value) || 0));
              const missingSpecialtyEvidence = key === 'specialty' && !hasSpecialtyEvidence;
              const ringScore = score;
              const color = ringScore < 60 ? '#b4473d' : ringScore < 80 ? '#c27b27' : '#1b786e';
              const ringStyle = { '--score-color': color } as CSSProperties;
              const label = SCORE_LABELS[key] || '综合评分';
              const displayText = score === 0
                ? (['hospital_info', 'official_service'].includes(key) ? '暂无信息' : '0.0')
                : score.toFixed(1);
              const isEmpty = score === 0 && displayText !== '0.0';
              const evidenceState = missingSpecialtyEvidence ? '，暂无直接专科依据' : '';
              return <div key={key}><dd style={ringStyle} aria-label={`${label} ${isEmpty ? displayText : `${score.toFixed(1)} 分`}${evidenceState}`}><svg className={styles.scoreRing} viewBox="0 0 56 56" aria-hidden="true"><circle className={styles.scoreRingTrack} cx="28" cy="28" r="24" pathLength="100" /><circle className={styles.scoreRingValue} cx="28" cy="28" r="24" pathLength="100" strokeDasharray={`${ringScore} ${100 - ringScore}`} /></svg><span className={isEmpty ? styles.scoreRingEmpty : undefined}>{displayText}</span></dd><dt>{label}{missingSpecialtyEvidence ? <small className={styles.specialtyEvidenceMissing}>暂无直接专科依据</small> : null}</dt></div>;
            })}
          </dl>
          <div className={styles.sourceLinks}>
            <a href={hospital.sources?.[0]?.url || 'https://y.dxy.cn/hospital/'} target="_blank" rel="noreferrer">查看公开来源 ↗</a>
            {hospital.official_website_url && <a href={hospital.official_website_url} target="_blank" rel="noreferrer">前往医院官网 ↗</a>}
            <span className={styles.appointmentMethod}>预约挂号方式：{hospital.wechat_appointment || `${hospital.name}公众号`}</span>
          </div>
        </details>
        <div className={styles.cardActions}>
          <button type="button" className={styles.primaryAction} aria-expanded={isExpanded} onClick={() => void openDetail(hospital.id)}>{isExpanded ? '收起医院详情' : '查看医院详情'}</button>
          <button
            type="button"
            className={styles.saveAction}
            aria-pressed={favorites.includes(hospital.id)}
            aria-label={`${favorites.includes(hospital.id) ? '取消收藏' : '收藏'} ${hospital.name}`}
            onClick={() => toggleFavoriteHospital(hospital)}
          >
            {favorites.includes(hospital.id) ? '已收藏' : '收藏医院'}
          </button>
        </div>
        {isExpanded && detail && <section className={styles.inlineDetail} aria-label={`${detail.name}医院详情`}>
          <div className={styles.inlineDetailHeader}>
            <div>
              <span className={styles.detailEyebrow}>医院详情</span>
              <h4>{detail.name}</h4>
            </div>
            <span className={styles.detailUpdated}>更新于 {new Date(detail.fetched_at).toLocaleDateString('zh-CN')}</span>
          </div>
          <div className={styles.detailSummary}>
            <div><span>医院地址</span><strong>{detail.address || detail.city || '暂无公开地址'}</strong></div>
            <div><span>相关科室</span><strong>{detail.departments.length ? detail.departments.slice(0, 3).join('、') : '暂无结构化科室信息'}</strong></div>
          </div>
          <div className={styles.detailIntro}>
            <span>公开简介</span>
            <p>{detail.introduction || '暂无医院简介公开摘要。'}</p>
          </div>
          <div className={styles.detailFooter}>
            <a href={detail.sources?.[0]?.url || 'https://y.dxy.cn/hospital/'} target="_blank" rel="noreferrer">查看公开来源 ↗</a>
            {detail.official_website_url && <a href={detail.official_website_url} target="_blank" rel="noreferrer">前往医院官网 ↗</a>}
            <span className={styles.appointmentMethod}>预约挂号方式：{detail.wechat_appointment || `${detail.name}公众号`}</span>
          </div>
        </section>}
      </article>
    );
  }

  const displayedRealtimeResults = realtimeResponse?.results
    ? (ignoreGeography
      ? [...realtimeResponse.results].sort((left, right) => {
        const displayedScore = (hospital: RealtimeSearchResponse['results'][number]) => getDisplayedResultScore({
          ...hospital,
          score_breakdown: {
            ...(hospital.score_breakdown ?? {}),
            official_service: hospital.official_website_url || hospital.registration_url ? 100 : 60,
          },
        }, { ignoreGeography }).score;
        return displayedScore(right) - displayedScore(left);
      })
      : realtimeResponse.results)
    : [];

  const legacyRealtimeResponse = realtimeResponse;
  const legacyDetail = detail;
  const scopeChangeInProgress = scopeSwitching && realtimeLoading;
  const heroContext = [
    realtimeResponse?.directions?.join('、'),
    [province, realtimeCity].filter(Boolean).join(' · '),
    realtimeResponse?.scope ? SCOPE_LABELS[realtimeResponse.scope] : '',
  ].filter(Boolean);

  function renderScopeSwitchStatus() {
    if (!scopeChangeInProgress) return null;
    return <div className={styles.scopeSwitchStatus} role="status" aria-live="polite" aria-atomic="true">
      <span className={styles.scopeSwitchSpinner} aria-hidden="true" />
      <div>
        <strong>正在切换到{SCOPE_LABELS[scope]}排名</strong>
        <p>保留当前结果，新的医院范围正在刷新</p>
      </div>
    </div>;
  }

  return (
    <main className={styles.page} inert={showEmergency}>
      {triageResponse && realtimeLoading && !scopeSwitching && <div className={styles.recommendationOverlay} role="status" aria-label="正在为您匹配医院" aria-live="polite" aria-modal="true"><div className={styles.recommendationDialog}><span className={styles.loadingBars} aria-hidden="true"><i /><i /><i /></span><strong>正在为您匹配医院</strong><p>正在根据疾病方向、地区和医院资料整理推荐结果，请稍候。</p></div></div>}
      <nav className={styles.nav} aria-label="主导航">
        <span className={styles.brand}>医途</span>
        <span>医院信息导航</span>
        <div className={styles.navLinks} aria-label="页面导航"><a href="#match">智能匹配</a><a href="/directory">医院目录</a><a href="/guide">使用说明</a></div>
        <button type="button" className={styles.feedbackNavButton} onClick={() => setFeedbackOpen(true)}>信息反馈</button>
        <button type="button" className={styles.favoriteNavButton} onClick={() => setFavoriteDrawerOpen(true)}>收藏夹 <span>{favorites.length}</span></button>
        <button type="button" className={styles.clearProfile} onClick={clearLocalData}>清除本机数据</button>
      </nav>
      <FavoriteDrawer open={favoriteDrawerOpen} favorites={favoriteHospitals} onClose={() => setFavoriteDrawerOpen(false)} onExpand={() => { setFavoriteDrawerOpen(false); setFavoritePageOpen(true); }} onRemove={removeFavoriteHospital} onOpenDetail={(id) => void openFavoriteDetail(id)} />
      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />

      <section className={`${styles.hero} ${surface === 'results' ? styles.heroResults : ''}`} aria-labelledby="page-title">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>演示医院信息匹配</p>
          <h1 id="page-title">找到更适合的医院信息</h1>
          <p className={styles.disclaimer}>本工具仅供查找演示医院信息，不提供诊断、治疗或疗效建议。</p>
          {surface === 'results' && heroContext.length > 0 && <p className={styles.heroContext}>{heroContext.join('  ·  ')}</p>}
        </div>
        {surface !== 'results' && <div className={styles.heroStats} aria-label="平台数据概览"><div><strong>31</strong><span>个省级行政区覆盖规划</span></div><div><strong>3</strong><span>项核心匹配维度</span></div></div>}
        {surface !== 'results' && <div className={styles.artwork} aria-hidden="true"><i /><b /><em /></div>}
      </section>

      <section id="match" className={`${styles.search} ${styles.match}`} aria-label="医院信息匹配">
        <div className={styles.panelHeading}><span>{surface === 'results' ? '02' : '01'}</span><h2>{surface === 'results' ? '医院推荐结果' : '告诉我们你的需求'}</h2></div>
        {surface !== 'results' && <form onSubmit={submitRealtime} className={styles.form}>
          <label htmlFor="query">症状或疾病</label>
          <textarea className={styles.query} id="query" name="query" value={realtimeQuery} onChange={(event) => { realtimeScopeCacheRef.current = {}; setRealtimeQuery(event.target.value); setQuery(event.target.value); setTriageResponse(null); setClarification(null); setClarificationAnswers([]); setClarificationChoice(''); setSelectedDirection(null); setSelectedResultDirectionKey(null); setRealtimeResponse(null); }} required maxLength={500} rows={3} placeholder="例如：反复胸痛、活动后气短，或已知疾病名称" />
          <div className={styles.formGrid}>
            <label htmlFor="province-main">省份<select id="province-main" value={province} onChange={(event) => selectProvince(event.target.value)} required><option value="">请选择省份</option>{Object.keys(LOCATION_TREE).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="city-main">城市<select id="city-main" value={realtimeCity} onChange={(event) => selectCity(event.target.value)} disabled={!province} required><option value="">{province ? '请选择城市' : '请先选择省份'}</option>{cityOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="district-main">市区（可选）<select id="district-main" value={district} onChange={(event) => selectDistrict(event.target.value)} disabled={!realtimeCity}><option value="">{realtimeCity ? '请选择区县' : '请先选择城市'}</option>{districtOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="scope-main">排名范围<select id="scope-main" value={scope} onChange={(event) => setScope(event.target.value as RealtimeSearchResponse['scope'])}><option value="district">区/县级</option><option value="city">市级</option><option value="province">省级</option><option value="national">全国</option></select></label>
          </div>
          <div className={styles.locationTools}><button type="button" onClick={locateUser} disabled={locating}>{locating ? '正在定位…' : '使用当前位置'}</button>{locationNotice && <span role="status">{locationNotice}</span>}</div>
          <label htmlFor="city">所在城市</label>
          <select className={styles.city} id="city" name="city" value={city} onChange={(event) => setCity(event.target.value)}><option value="">不限城市</option><option value="上海">上海</option><option value="杭州">杭州</option></select>
          <label htmlFor="priority">匹配偏好</label>
          <select className={styles.priority} id="priority" name="priority" value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}><option value="overall">综合信息</option><option value="specialty">专科方向</option><option value="convenience">就近便利</option></select>
          <div className={styles.aiConsent}>
            <label htmlFor="ai-consent"><input id="ai-consent" type="checkbox" checked={realtimeConsent} onChange={(event) => setRealtimeConsent(event.target.checked)} />同意使用智能体整理本次就医方向</label>
            <p>智能体仅整理就医方向，不提供诊断或治疗建议。</p>
          </div>
          <fieldset className={styles.tierFilters}>
            <legend>医院等级</legend>
            <label><input type="checkbox" checked={hospitalTiers.includes('tertiary_a')} onChange={(event) => { realtimeScopeCacheRef.current = {}; setHospitalTiers(event.target.checked ? ['tertiary_a'] : []); }} />三级甲等</label>
            <label className={styles.disabledOption}><input type="checkbox" disabled />三级乙等（暂不可用）</label>
            <label className={styles.disabledOption}><input type="checkbox" disabled />二级及以下（暂不可用）</label>
          </fieldset>
          {!realtimeConsent && <p className={styles.consentRequired} role="alert">请先勾选“同意使用智能体”后再开始匹配。</p>}
          <button ref={submitButtonRef} type="submit" disabled={realtimeLoading || !realtimeConsent}>{realtimeLoading && <span className={styles.buttonSpinner} aria-hidden="true" />}{realtimeLoading ? '正在匹配…' : '开始匹配'}</button>
        </form>}
        {surface !== 'results' && <div className={styles.quickTags}><span>常见就医方向：</span><button type="button" onClick={() => useQuickQuery('冠心病')}>心血管疾病</button><button type="button" onClick={() => useQuickQuery('儿童发热咳嗽')}>儿童发热咳嗽</button><button type="button" onClick={() => useQuickQuery('肿瘤治疗')}>肿瘤治疗</button><button type="button" onClick={() => useQuickQuery('关节疼痛')}>关节疼痛</button></div>}
        {surface === 'results' && triageResponse && <section className={styles.resultDirection} aria-label="疾病方向和推荐科室">
          <div className={styles.resultDirectionHeader}><span>01</span><div><h3>你的就医方向</h3><p>{triageResponse.summary}</p>{selectedResultDirection && <p className={styles.resultDirectionSelection} aria-label={`当前选择：${selectedResultDirection.title}，推荐科室：${selectedResultDirection.department}`}>当前选择：<strong>{selectedResultDirection.title}</strong> · 推荐科室：{selectedResultDirection.department}</p>}</div></div>
          <div className={styles.resultDirectionCards} role="radiogroup" aria-label="选择疾病方向和推荐科室">{triageResponse.directions.map((item) => <button key={item.key} type="button" role="radio" aria-checked={item.key === selectedResultDirectionKey} className={item.key === selectedResultDirectionKey ? styles.resultDirectionCardSelected : ''} onClick={() => void switchResultDirection(item)}><span>疾病可能性：{formatLikelihood(item.likelihood)}</span><h4>{item.title}</h4><strong>建议就诊科室：{item.department}</strong><p>可能涉及：{item.possible_diseases?.length ? item.possible_diseases.join('、') : '暂时无法判断具体疾病'}</p></button>)}</div>
          <small>{triageResponse.disclaimer}</small>
        </section>}
        {realtimeLoading && !triageResponse && <div className={styles.loadingState} role="status" aria-live="polite"><span className={styles.loadingBars} aria-hidden="true"><i /><i /><i /></span><div><strong>正在检索公开资料</strong><p>正在根据症状、位置和排名范围整理医院信息，请稍候。</p></div></div>}
        {realtimeError && <p className={styles.notice} role="alert">{realtimeError}</p>}
        <span id="results" className={styles.resultsAnchor} aria-hidden="true" />
        {realtimeResponse && renderResultLocation()}
        {triageResponse && !realtimeResponse && (
          <section ref={triagePanelRef} className={styles.triagePanel} aria-labelledby="triage-title">
            {realtimeLoading && <div className={styles.triageLoading} role="status" aria-label="正在根据就医方向整理医院信息" aria-live="polite"><span className={styles.loadingBars} aria-hidden="true"><i /><i /><i /></span><div><strong>正在根据就医方向整理医院信息</strong><p>当前疾病方向和原有内容保持不变，医院结果返回后会自动更新。</p></div></div>}
            <div className={styles.panelHeading}><span>02</span><h2 id="triage-title">可能涉及的疾病方向</h2></div>
            <p>{triageResponse.summary}</p>
            <p className={styles.disclaimer}>{triageResponse.disclaimer}</p>
            {triageResponse.urgent_warning && <p className={styles.notice}>{triageResponse.urgent_warning}</p>}
            {clarification?.question && (
              <section className={styles.clarificationCard} aria-label="补充确认问题">
                <div className={styles.clarificationHeader}>
                  <div>
                    <span className={styles.clarificationEyebrow}>补充确认</span>
                    <h3>{clarification.question.text}</h3>
                  </div>
                  <span className={styles.clarificationProgress}>第 {clarification.progress.current} / {clarification.progress.total} 题</span>
                </div>
                <div className={styles.clarificationOptions} role="radiogroup" aria-label={clarification.question.text}>
                  {[...clarification.question.options, CUSTOM_CLARIFICATION_OPTION].map((option) => (
                    <label key={option} className={`${styles.clarificationOption} ${clarificationChoice === option ? styles.clarificationOptionSelected : ''}`}>
                      <input type="radio" name="symptom-clarification" value={option} checked={clarificationChoice === option} onChange={() => { setClarificationChoice(option); if (option !== CUSTOM_CLARIFICATION_OPTION) setClarificationCustomAnswer(''); }} />
                      <span>{option}</span>
                    </label>
                  ))}
                </div>
                {clarificationChoice === CUSTOM_CLARIFICATION_OPTION && (
                  <label className={styles.clarificationCustomField} htmlFor="clarification-custom-answer">
                    自己填写
                    <textarea id="clarification-custom-answer" value={clarificationCustomAnswer} onChange={(event) => setClarificationCustomAnswer(event.target.value)} maxLength={300} rows={3} placeholder="请用自己的话描述情况" />
                  </label>
                )}
                <div className={styles.clarificationActions}>
                  <span>可以选择“不确定”，系统会保留当前判断方向。</span>
                  <button type="button" onClick={() => void submitClarificationAnswer()} disabled={realtimeLoading || !clarificationChoice || (clarificationChoice === CUSTOM_CLARIFICATION_OPTION && !clarificationCustomAnswer.trim())}>{realtimeLoading ? '正在分析…' : '继续'}</button>
                </div>
              </section>
            )}
            <div className={styles.triageCards}>
              {triageResponse.directions.map((direction) => (
                <article className={styles.triageCard} key={direction.key}>
                  <div><span>疾病可能性：{formatLikelihood(direction.likelihood)}</span><h3>{direction.title}</h3></div>
                  <p>{direction.basis}</p>
                  <strong>建议就诊科室：{direction.department}</strong>
                  {direction.possible_diseases?.length ? <p className={styles.possibleDiseases}><b>可能涉及：</b>{direction.possible_diseases.join('、')}<small>仅作方向参考，不是医学诊断</small></p> : <p className={styles.possibleDiseases}><b>可能涉及：</b>暂时无法从当前信息判断具体疾病</p>}
                  {direction.urgent_warning && <small>{direction.urgent_warning}</small>}
                  <button type="button" onClick={() => void confirmDirection(direction)}>按此方向推荐医院</button>
                </article>
              ))}
            </div>
          </section>
        )}
        {realtimeResponse && realtimeResponse.status !== 'OK' && <>
          <div className={styles.scopeBar} aria-busy={scopeChangeInProgress}>
            <div className={styles.scopeNoteRow}><p className={styles.scopeNote}>当前排名范围：{SCOPE_LABELS[scope]}。你可以直接切换其他区域范围重新检索。</p></div>
            <div className={styles.scopeSwitcher} role="tablist" aria-label="切换排名范围">{(['district', 'city', 'province', 'national'] as const).map((level) => <button key={level} type="button" role="tab" aria-selected={scope === level} className={scope === level ? styles.scopeActive : ''} disabled={realtimeLoading} onClick={() => void switchRealtimeScope(level)}>{SCOPE_LABELS[level]}</button>)}</div>
          </div>
          {renderScopeSwitchStatus()}
          <p className={styles.notice}>{realtimeResponse.status === 'SEARCH_UNAVAILABLE' ? '暂时无法连接公开资料搜索服务，请稍后重试。你的输入没有问题。' : realtimeResponse.status === 'NO_RESULTS' ? '暂未找到符合当前范围的医院资料，请扩大排名范围或补充症状描述。' : '当前描述可能需要急诊处理，请优先联系 120。'}</p>
        </>}
        {realtimeResponse?.status === 'OK' && <>
          <div ref={scopeBarRef} className={styles.scopeBar} aria-busy={scopeChangeInProgress}>
            <div className={styles.scopeNoteRow}><p className={styles.scopeNote}>当前排名范围：{SCOPE_LABELS[realtimeResponse.scope]}。系统已按用户选择的最小地址范围检索公开资料。</p></div>
            <div className={styles.scopeSwitcher} role="tablist" aria-label="切换排名范围">{(['district', 'city', 'province', 'national'] as const).map((level) => <button key={level} type="button" role="tab" aria-selected={realtimeResponse.scope === level} className={realtimeResponse.scope === level ? styles.scopeActive : ''} disabled={realtimeLoading} onClick={() => void switchRealtimeScope(level)}>{SCOPE_LABELS[level]}</button>)}</div>
          </div>
          {renderScopeSwitchStatus()}
          {realtimeResponse.processing_notice && <p className={styles.notice}>{realtimeResponse.processing_notice}</p>}
          {realtimeResponse.fallback_message && <div className={styles.fallbackNotice}><span>{realtimeResponse.fallback_message}</span>{realtimeResponse.fallback_scope && <button type="button" onClick={() => void switchRealtimeScope(realtimeResponse.fallback_scope!)}>切换至更高一级范围</button>}</div>}
          <div className={`${styles.cards} ${scopeChangeInProgress ? styles.resultsBusy : ''}`.trim()} aria-label="实时医院排名" aria-busy={scopeChangeInProgress} inert={scopeChangeInProgress || undefined}>{displayedRealtimeResults.map(renderRealtimeCard)}</div>
        </>}
        {detail && <aside className={styles.detailPanel} aria-label="医院详情"><div className={styles.detailPanelHeader}><div><span className={styles.detailEyebrow}>医院资料</span><h3>{detail.name}</h3></div><button type="button" className={styles.detailClose} onClick={() => setDetail(null)}>关闭详情</button></div><div className={styles.detailIntro}><span>公开简介</span><p>{detail.introduction || '暂无医院简介公开摘要。'}</p></div><div className={styles.detailColumns}><section><h4>相关科室</h4><p>{detail.departments.length ? detail.departments.join('、') : '暂无结构化科室信息。'}</p></section><section><h4>主要医生</h4><p>{detail.doctors.length ? detail.doctors.join('、') : '暂无可靠的公开医生信息。'}</p></section></div><div className={styles.detailFooter}><a href={detail.sources?.[0]?.url || 'https://y.dxy.cn/hospital/'} target="_blank" rel="noreferrer">查看公开来源 ↗</a>{detail.official_website_url && <a href={detail.official_website_url} target="_blank" rel="noreferrer">前往医院官网 ↗</a>}</div></aside>}
      </section>

      {false && (() => { const realtimeResponse = legacyRealtimeResponse!; const detail = legacyDetail!; return (<section className={styles.search} aria-labelledby="realtime-title">
        <div className={styles.panelHeading}><span>实时</span><h2 id="realtime-title">公开资料医院排名</h2></div>
        <p>输入症状或疾病，检索公开资料并按综合评分返回前 10 家医院，默认按市区范围。</p>
        <form onSubmit={submitRealtime} className={styles.form}>
          <label htmlFor="realtime-query">实时症状或疾病</label>
          <textarea id="realtime-query" value={realtimeQuery} onChange={(event) => { realtimeScopeCacheRef.current = {}; setRealtimeQuery(event.target.value); setTriageResponse(null); setClarification(null); setClarificationAnswers([]); setClarificationChoice(''); setClarificationCustomAnswer(''); setSelectedDirection(null); setRealtimeResponse(null); }} required maxLength={500} rows={3} placeholder="例如：持续胸痛、膝关节疼痛" />
          <div className={styles.formGrid}>
            <label htmlFor="province">省份<input id="province" value={province} onChange={(event) => { realtimeScopeCacheRef.current = {}; setProvince(event.target.value); }} required /></label>
            <label htmlFor="realtime-city">城市<input id="realtime-city" value={realtimeCity} onChange={(event) => { realtimeScopeCacheRef.current = {}; setRealtimeCity(event.target.value); }} required /></label>
            <label htmlFor="district">市区<input id="district" value={district} onChange={(event) => { realtimeScopeCacheRef.current = {}; setDistrict(event.target.value); }} required /></label>
            <label htmlFor="scope">排名范围<select id="scope" value={scope} onChange={(event) => setScope(event.target.value as RealtimeSearchResponse['scope'])}><option value="district">区/县级</option><option value="city">市级</option><option value="province">省级</option><option value="national">全国</option></select></label>
          </div>
          <label className={styles.aiConsent} htmlFor="realtime-consent"><input id="realtime-consent" type="checkbox" checked={realtimeConsent} onChange={(event) => setRealtimeConsent(event.target.checked)} />同意使用智能体整理本次就医方向</label>
          <button type="submit" disabled={realtimeLoading || !realtimeConsent}>{realtimeLoading ? '正在检索公开资料…' : '开始实时匹配'}</button>
        </form>
        {realtimeError && !triageResponse && <p className={styles.notice} role="alert">{realtimeError}</p>}
        {realtimeResponse && realtimeResponse.status !== 'OK' && <p className={styles.notice}>{realtimeResponse.status === 'SEARCH_UNAVAILABLE' ? '暂时无法连接公开资料搜索服务，请稍后重试。你的输入没有问题。' : realtimeResponse.status === 'NO_RESULTS' ? '暂未找到符合当前范围的医院资料，请扩大排名范围或补充症状描述。' : '当前描述可能需要急诊处理，请优先联系 120。'}</p>}
        {realtimeResponse?.status === 'OK' && <div className={styles.cards} aria-label="实时医院排名">{displayedRealtimeResults.map(renderRealtimeCard)}</div>}
        {detail && <aside className={styles.detailPanel} aria-label="医院详情"><div className={styles.detailPanelHeader}><div><span className={styles.detailEyebrow}>医院资料</span><h3>{detail.name}</h3></div><button type="button" className={styles.detailClose} onClick={() => setDetail(null)}>关闭详情</button></div><div className={styles.detailIntro}><span>公开简介</span><p>{detail.introduction || '暂无医院简介公开摘要。'}</p></div><div className={styles.detailColumns}><section><h4>相关科室</h4><p>{detail.departments.length ? detail.departments.join('、') : '暂无结构化科室信息。'}</p></section><section><h4>主要医生</h4><p>{detail.doctors.length ? detail.doctors.join('、') : '暂无可靠的公开医生信息。'}</p></section></div>{detail.registration_url && <a className={styles.registrationLink} href={detail.registration_url || '#'} target="_blank" rel="noreferrer">前往官方挂号服务 <span aria-hidden="true">↗</span></a>}</aside>}
      </section>); })()}

      <section className={styles.overview} aria-label="平台信息概览">
        <div><span>覆盖规划</span><strong>31</strong><small>个省级行政区</small></div>
        <div><span>核心匹配维度</span><strong>03</strong><small>专科 · 便利 · 数据时效</small></div>
        <div><span>使用方式</span><strong>3 min</strong><small>描述情况、比较医院、保存候选</small></div>
        <aside><b>就医前建议</b><p>推荐结果仅供信息参考，请通过医院官方渠道核实门诊与服务信息。</p></aside>
      </section>

      <section id="guide" className={styles.guide} aria-labelledby="guide-title">
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
                  onClick={() => toggleFavoriteId(hospital.id)}
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
