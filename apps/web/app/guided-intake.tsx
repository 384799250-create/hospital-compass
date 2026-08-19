'use client';

import { FormEvent, useMemo, useState } from 'react';

import {
  clarifySymptoms,
  MatchApiError,
  SymptomClarificationAnswer,
  SymptomClarificationResponse,
  TriageDirection,
  TriageResponse,
  triageSymptoms,
} from '../lib/api';
import { formatLikelihood } from '../lib/formatters';
import provinceData from '../data/province.json';
import cityData from '../data/city.json';
import areaData from '../data/area.json';
import styles from './page.module.css';

type RegionRow = { code: string; name: string; province: string; city?: string; area?: string };
type LocationTree = Record<string, Record<string, string[]>>;

const LOCATION_TREE: LocationTree = (provinceData as RegionRow[]).reduce((tree, provinceRow) => {
  const cities = (cityData as RegionRow[]).filter((row) => row.province === provinceRow.province);
  const cityRows = cities.length ? cities : [{ name: provinceRow.name, province: provinceRow.province, code: provinceRow.code }];
  tree[provinceRow.name] = Object.fromEntries(cityRows.map((cityRow) => [
    cityRow.name,
    (areaData as RegionRow[])
      .filter((areaRow) => areaRow.province === provinceRow.province && areaRow.city === (cityRow.city ?? '01'))
      .map((areaRow) => areaRow.name),
  ]));
  return tree;
}, {} as LocationTree);

const CUSTOM_OPTION = '以上都不符合，我自己填写';
const MAX_CLARIFICATION_QUESTIONS = 10;

function estimateQuestionRange(progress: SymptomClarificationResponse['progress']) {
  const minimum = Math.min(MAX_CLARIFICATION_QUESTIONS, Math.max(1, progress.current, progress.total));
  return { minimum, maximum: Math.min(MAX_CLARIFICATION_QUESTIONS, minimum + 2) };
}

function questionEstimateText(response: SymptomClarificationResponse) {
  if (typeof response.estimated_total === 'number') return String(response.estimated_total);
  const estimate = estimateQuestionRange(response.progress);
  return estimate.minimum === estimate.maximum ? String(estimate.minimum) : `${estimate.minimum}-${estimate.maximum}`;
}

export type GuidedSearchInput = {
  query: string;
  province: string;
  city: string;
  district: string;
  scope: 'district' | 'city' | 'province' | 'national';
  priority: 'overall' | 'specialty' | 'convenience';
  direction: string;
  triage: TriageResponse;
};

type GuidedIntakeProps = {
  onComplete: (input: GuidedSearchInput) => void | Promise<void>;
  onEmergency?: (message: string) => void;
  onBackToLanding?: () => void;
};

function needsClarification(response: TriageResponse) {
  if (response.explicit_disease_input) return false;
  return response.directions.length !== 1 || response.directions[0]?.likelihood === '待评估';
}

function directionTriage(response: SymptomClarificationResponse): TriageResponse {
  return {
    summary: '根据你补充的信息，当前更符合以下就医方向。',
    directions: response.directions,
    urgent_warning: response.urgent_warning,
    disclaimer: '以上是健康信息整理，不是医学诊断。',
    is_diagnosis: false,
    ai_used: response.ai_used ?? true,
  };
}

export default function GuidedIntake({ onComplete, onEmergency, onBackToLanding }: GuidedIntakeProps) {
  const [stage, setStage] = useState<'symptom' | 'clarification' | 'direction' | 'preferences'>('symptom');
  const [query, setQuery] = useState('');
  const [triage, setTriage] = useState<TriageResponse | null>(null);
  const [clarification, setClarification] = useState<SymptomClarificationResponse | null>(null);
  const [answers, setAnswers] = useState<SymptomClarificationAnswer[]>([]);
  const [questionHistory, setQuestionHistory] = useState<SymptomClarificationResponse[]>([]);
  const [pendingAnswer, setPendingAnswer] = useState<SymptomClarificationAnswer | null>(null);
  const [choice, setChoice] = useState('');
  const [customAnswer, setCustomAnswer] = useState('');
  const [selectedDirectionKey, setSelectedDirectionKey] = useState<string | null>(null);
  const [province, setProvince] = useState('');
  const [city, setCity] = useState('');
  const [district, setDistrict] = useState('');
  const [priority, setPriority] = useState<GuidedSearchInput['priority']>('overall');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cityOptions = useMemo(() => Object.keys(LOCATION_TREE[province] ?? {}), [province]);
  const districtOptions = useMemo(() => LOCATION_TREE[province]?.[city] ?? [], [province, city]);
  const direction = triage?.directions.find((item) => item.key === selectedDirectionKey) ?? null;
  const questionEstimate = clarification ? questionEstimateText(clarification) : null;

  function renderThinkingStatus(message: string) {
    return <div className={styles.guidedThinking} role="status" aria-live="polite" aria-label={message}>
      <span className={styles.guidedThinkingMark} aria-hidden="true"><i /><i /><i /></span>
      <span>{message}</span>
    </div>;
  }

  async function beginTriage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) return;
    setError(null);
    setSelectedDirectionKey(null);
    setAnswers([]);
    setQuestionHistory([]);
    setClarification(null);
    setPendingAnswer(null);
    setChoice('');
    setCustomAnswer('');
    setLoading(true);
    try {
      const nextTriage = await triageSymptoms({ query: cleanQuery, ai_consent: true });
      setTriage(nextTriage);
      if (nextTriage.urgent_warning) onEmergency?.(nextTriage.urgent_warning);
      if (needsClarification(nextTriage)) {
        try {
          const nextQuestion = await clarifySymptoms({ query: cleanQuery, answers: [], ai_consent: true });
          if (nextQuestion.status === 'EMERGENCY') {
            setError(nextQuestion.urgent_warning);
            setStage('symptom');
            onEmergency?.(nextQuestion.urgent_warning);
            return;
          }
          if (nextQuestion.status === 'NEEDS_CLARIFICATION' && nextQuestion.question) {
            setClarification(nextQuestion);
            setStage('clarification');
          } else {
            setTriage(directionTriage(nextQuestion));
            setStage('direction');
          }
        } catch {
          setClarification(null);
          setStage('direction');
          setError('智能整理暂时未能继续出题，已保留当前就医方向。');
        }
      } else {
        setStage('direction');
      }
    } catch (requestError) {
      setError(requestError instanceof MatchApiError && requestError.status === 503
        ? '智能整理服务暂时不可用，请稍后重试。'
        : '暂时无法整理症状，请检查服务是否已启动。');
    } finally {
      setLoading(false);
    }
  }

  async function continueClarification(answer: SymptomClarificationAnswer) {
    if (!clarification?.question) return;
    const currentQuestion = clarification;
    setPendingAnswer(answer);
    setError(null);
    setLoading(true);
    try {
      const nextAnswers = [...answers, answer];
      const askedQuestions = [...questionHistory, currentQuestion].flatMap((response) => response.question ? [{
        id: response.question.id,
        text: response.question.text,
        options: response.question.options,
      }] : []);
      const next = await clarifySymptoms({
        query: query.trim(), answers: nextAnswers, asked_questions: askedQuestions, ai_consent: true,
      });
      setAnswers(nextAnswers);
      setQuestionHistory([...questionHistory, currentQuestion]);
      setPendingAnswer(null);
      setChoice('');
      setCustomAnswer('');
      if (next.status === 'EMERGENCY') {
        setError(next.urgent_warning);
        setStage('symptom');
        onEmergency?.(next.urgent_warning);
        setClarification(null);
        setAnswers([]);
        setQuestionHistory([]);
      } else if (next.status === 'COMPLETE') {
        setClarification(null);
        setSelectedDirectionKey(null);
        setTriage(directionTriage(next));
        setStage('direction');
      } else {
        setClarification(next);
      }
    } catch (requestError) {
      setError(requestError instanceof MatchApiError && requestError.status === 503
        ? '智能整理服务暂时不可用，请重试。'
        : '暂时无法继续整理，请稍后重试。');
    } finally {
      setLoading(false);
    }
  }

  async function answerClarification() {
    if (!clarification?.question || !choice) return;
    const value = choice === CUSTOM_OPTION ? customAnswer.trim() : choice;
    if (!value) return;
    await continueClarification({ question_id: clarification.question.id, value });
  }

  function selectProvince(value: string) {
    setProvince(value);
    setCity('');
    setDistrict('');
  }

  function selectCity(value: string) {
    setCity(value);
    setDistrict('');
  }

  async function submitPreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!triage || !direction || !province || !city) return;
    setError(null);
    setLoading(true);
    try {
      await onComplete({
        query: query.trim(),
        province,
        city,
        district,
        scope: district ? 'district' : 'city',
        priority,
        direction: direction?.department ?? '',
        triage,
      });
    } catch {
      setError('医院推荐暂时不可用，请稍后重试。');
      setLoading(false);
    }
  }

  function restorePreviousQuestion() {
    const previousQuestion = questionHistory.at(-1);
    const previousAnswer = answers.at(-1);
    if (!previousQuestion?.question || !previousAnswer) return false;

    const isListedAnswer = previousQuestion.question.options.includes(previousAnswer.value);
    setAnswers(answers.slice(0, -1));
    setQuestionHistory(questionHistory.slice(0, -1));
    setClarification(previousQuestion);
    setPendingAnswer(null);
    setChoice(isListedAnswer ? previousAnswer.value : CUSTOM_OPTION);
    setCustomAnswer(isListedAnswer ? '' : previousAnswer.value);
    setSelectedDirectionKey(null);
    setStage('clarification');
    return true;
  }

  function back() {
    setError(null);
    if (stage === 'symptom') {
      onBackToLanding?.();
    } else if (stage === 'clarification') {
      if (restorePreviousQuestion()) return;
      setStage('symptom');
      setClarification(null);
      setPendingAnswer(null);
      setAnswers([]);
      setQuestionHistory([]);
      setChoice('');
      setCustomAnswer('');
    } else if (stage === 'direction') {
      if (!restorePreviousQuestion()) setStage('symptom');
    } else {
      setStage('direction');
    }
  }

  const canReturnToQuestion = (stage === 'clarification' || stage === 'direction') && answers.length > 0 && questionHistory.length > 0;

  return (
    <main className={styles.guidedPage}>
      <div className={styles.guidedBackdrop} aria-hidden="true"><span /><i /><b /></div>
      <section className={styles.guidedDialog} role="dialog" aria-modal="true" aria-labelledby="guided-title">
        <header className={styles.guidedHeader}>
          <div><span className={styles.guidedBrand}>医途</span><span className={styles.guidedStep}>陪你把就医方向理清楚</span></div>
          <button type="button" className={styles.guidedBack} onClick={back} disabled={loading} aria-label={canReturnToQuestion ? '返回上一题' : '返回上一步'}>{canReturnToQuestion ? '上一题' : '返回'}</button>
        </header>

        {stage === 'symptom' && <form onSubmit={beginTriage} className={styles.guidedStage}>
          <span className={styles.guidedKicker}>先从症状开始</span>
          <h1 id="guided-title">先告诉我，你哪里不舒服？</h1>
          <p className={styles.guidedLead}>不用想专业名称，用你平时说话的方式描述就好。</p>
          <label className={styles.guidedFieldLabel} htmlFor="guided-query">症状或疾病</label>
          <textarea id="guided-query" aria-label="症状或疾病" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => {
            if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }} placeholder="例如：这两天总是头晕，走快一点就心慌" maxLength={500} autoFocus rows={5} />
          <div className={styles.guidedExamples} aria-label="快速示例"><span>可以这样说：</span>{['头疼伴随恶心', '膝盖上下楼疼', '孩子发热咳嗽'].map((example) => <button type="button" key={example} onClick={() => setQuery(example)}>{example}</button>)}</div>
          {loading && renderThinkingStatus('AI 正在理解你的描述，请稍候')}
          {error && <p className={styles.guidedError} role="alert">{error}</p>}
          <button className={styles.guidedPrimary} type="submit" disabled={loading || !query.trim()}>{loading ? '正在理解你的描述…' : error ? '重试理解' : '继续'}</button>
        </form>}

        {stage === 'clarification' && clarification?.question && <section className={styles.guidedStage} aria-label="补充确认问题">
          <span className={styles.guidedKicker}>再确认一件事</span>
          <h1 id="guided-title">{clarification.question.text}</h1>
          <p className={styles.guidedLead}>选最接近的情况就好，不确定也可以告诉我。</p>
          {questionEstimate && <div className={styles.guidedProgressRow}>
            <span className={styles.guidedProgress}>第 {clarification.progress.current} 题 · 预计共 {questionEstimate} 个问题</span>
            <small>AI 会根据你的回答动态调整</small>
          </div>}
          {loading && renderThinkingStatus('AI 正在根据你的回答调整问题，请稍候')}
          <div className={styles.guidedOptions} role="radiogroup" aria-label={clarification.question.text}>
            {[...clarification.question.options, CUSTOM_OPTION].map((option) => <label key={option} className={choice === option ? styles.guidedOptionSelected : styles.guidedOption}>
              <input type="radio" name="guided-clarification" value={option} checked={choice === option} onChange={() => { setPendingAnswer(null); setChoice(option); if (option !== CUSTOM_OPTION) setCustomAnswer(''); }} />
              <span>{option}</span>
            </label>)}
          </div>
          {choice === CUSTOM_OPTION && <label className={styles.guidedCustom} htmlFor="guided-custom">自己填写<textarea id="guided-custom" aria-label="自己填写" value={customAnswer} onChange={(event) => { setPendingAnswer(null); setCustomAnswer(event.target.value); }} rows={3} placeholder="用一句话补充你的情况" /></label>}
          {error && <p className={styles.guidedError} role="alert">{error}</p>}
          <button className={styles.guidedPrimary} type="button" onClick={() => void (pendingAnswer ? continueClarification(pendingAnswer) : answerClarification())} disabled={loading || !choice || (choice === CUSTOM_OPTION && !customAnswer.trim())}>{loading ? '正在整理…' : error ? '重试' : '继续'}</button>
        </section>}

        {stage === 'direction' && triage && <section className={styles.guidedStage} aria-label="疾病方向和推荐科室">
          <span className={styles.guidedKicker}>先看懂方向，再找医院</span>
          <h1 id="guided-title">我先帮你整理出就医方向</h1>
          <p className={styles.guidedLead}>{triage.summary}</p>
          <p className={styles.guidedDirectionHint}>请选择一个方向，医院将按对应科室为你推荐。</p>
          <div className={styles.guidedDirectionList} role="radiogroup" aria-label="选择就医方向">{triage.directions.map((item: TriageDirection) => {
            const selected = item.key === selectedDirectionKey;
            return <article
              className={selected ? `${styles.guidedDirection} ${styles.guidedDirectionSelected}` : styles.guidedDirection}
              key={item.key}
              role="radio"
              aria-checked={selected}
              tabIndex={0}
              onClick={() => setSelectedDirectionKey(item.key)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setSelectedDirectionKey(item.key);
                }
              }}
            >
            <div><span>疾病可能性：{formatLikelihood(item.likelihood)}</span><h2>{item.title}</h2></div>
            <p>{item.basis}</p>
            <strong>建议就诊科室：{item.department}</strong>
            <p className={styles.guidedDiseases}><b>可能涉及：</b>{item.possible_diseases?.length ? item.possible_diseases.join('、') : '暂时无法判断具体疾病'}</p>
            <span className={styles.guidedDirectionChoice}>{selected ? '已选择此方向' : '选择此方向'}</span>
          </article>;
          })}</div>
          <p className={styles.guidedDisclaimer}>{triage.disclaimer}</p>
          {error && <p className={styles.guidedError} role="alert">{error}</p>}
          <button className={styles.guidedPrimary} type="button" onClick={() => setStage('preferences')} disabled={!direction}>{direction ? '按所选科室继续' : '请选择一个就医方向'}</button>
        </section>}

        {stage === 'preferences' && <form onSubmit={submitPreferences} className={styles.guidedStage}>
          <span className={styles.guidedKicker}>最后一步</span>
          <h1 id="guided-title">告诉我你的所在位置和就医偏好</h1>
          <p className={styles.guidedLead}>我会按你的地点和偏好整理医院列表，先给方向，再给综合评分。</p>
          <div className={styles.guidedLocationGrid}>
            <label htmlFor="guided-province">省份<select id="guided-province" value={province} onChange={(event) => selectProvince(event.target.value)} required><option value="">请选择省份</option>{Object.keys(LOCATION_TREE).map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="guided-city">城市<select id="guided-city" value={city} onChange={(event) => selectCity(event.target.value)} disabled={!province} required><option value="">{province ? '请选择城市' : '请先选择省份'}</option>{cityOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
            <label htmlFor="guided-district">区县（可选）<select id="guided-district" value={district} onChange={(event) => setDistrict(event.target.value)} disabled={!city}><option value="">{city ? '不限区县' : '请先选择城市'}</option>{districtOptions.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          </div>
          <fieldset className={styles.guidedPreference}><legend>匹配偏好</legend><label><input type="radio" name="guided-priority" value="overall" checked={priority === 'overall'} onChange={() => setPriority('overall')} />综合信息</label><label><input type="radio" name="guided-priority" value="specialty" checked={priority === 'specialty'} onChange={() => setPriority('specialty')} />专科方向</label><label><input type="radio" name="guided-priority" value="convenience" checked={priority === 'convenience'} onChange={() => setPriority('convenience')} />就近便利</label></fieldset>
          {error && <p className={styles.guidedError} role="alert">{error}</p>}
          <button className={styles.guidedPrimary} type="submit" disabled={loading || !direction || !province || !city}>{loading ? '正在推荐医院…' : '开始推荐医院'}</button>
        </form>}
      </section>
    </main>
  );
}
