"""Disease-to-specialty adapters used by the stable five-dimension scorer.

The profiles describe care directions, not diagnoses. A term in
``explicit_disease_terms`` can skip symptom clarification; a keyword only
helps choose a department direction.
"""

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class DiseaseProfile:
    key: str
    departments: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    explicit_disease_terms: tuple[str, ...] = ()
    ranking_terms: tuple[str, ...] = ()
    urgent_terms: tuple[str, ...] = ()


PROFILES = (
    DiseaseProfile(
        key='cardiovascular',
        departments=('心血管内科', '心脏外科', '胸痛中心'),
        keywords=('心绞痛', '冠心病', '冠状动脉', '心肌梗死', '心梗', '心力衰竭', '心衰', '房颤', '心房颤动', '高血压', '主动脉夹层', '胸痛', '心慌', '心内科', 'coronary artery disease', 'CAD', 'angina', 'myocardial infarction', 'MI', 'heart failure', 'HF', 'atrial fibrillation', 'AFib', 'hypertension', 'HTN'),
        explicit_disease_terms=('心绞痛', '冠心病', '冠状动脉粥样硬化性心脏病', '心肌梗死', '急性心肌梗死', '心力衰竭', '充血性心力衰竭', '房颤', '心房颤动', '高血压', '原发性高血压', '主动脉夹层', 'coronary artery disease', 'CAD', 'angina pectoris', 'angina', 'myocardial infarction', 'MI', 'heart failure', 'HF', 'atrial fibrillation', 'AFib', 'hypertension', 'HTN'),
        ranking_terms=('心血管重点专科', '心血管区域医疗中心', 'PCI', '搭桥'),
        urgent_terms=('剧烈胸痛', '胸痛持续不缓解', '突发单侧无力'),
    ),
    DiseaseProfile(
        key='neurology',
        departments=('神经内科', '神经外科', '康复医学科'),
        keywords=('渐冻症', '肌萎缩侧索硬化', '运动神经元病', '卢伽雷病', '路格里克病', '帕金森病', '帕金森', '震颤麻痹', '阿尔茨海默病', '阿尔茨海默症', '老年痴呆', '认知症', '癫痫', '羊癫疯', '羊角风', '脑卒中', '中风', '脑梗死', '脑梗', '脑出血', '脑溢血', '重症肌无力', '多发性硬化', '偏头痛', '脑膜炎', 'ALS', 'amyotrophic lateral sclerosis', 'Parkinson', 'Alzheimer', 'epilepsy', 'stroke', 'cerebral infarction', 'myasthenia gravis', 'MG', 'multiple sclerosis', 'MS', 'migraine', 'meningitis'),
        explicit_disease_terms=('渐冻症', '肌萎缩侧索硬化', '运动神经元病', '卢伽雷病', '路格里克病', '帕金森病', '帕金森', '震颤麻痹', '阿尔茨海默病', '阿尔茨海默症', '老年痴呆', '癫痫', '羊癫疯', '羊角风', '脑卒中', '中风', '脑梗死', '脑梗', '缺血性脑卒中', '脑出血', '脑溢血', '出血性脑卒中', '重症肌无力', '多发性硬化', '偏头痛', '脑膜炎', 'ALS', 'amyotrophic lateral sclerosis', 'Parkinson', 'Parkinson disease', "Parkinson's disease", 'Alzheimer', 'Alzheimer disease', "Alzheimer's disease", 'AD', 'epilepsy', 'stroke', 'cerebral infarction', 'ischemic stroke', 'myasthenia gravis', 'MG', 'multiple sclerosis', 'MS', 'migraine', 'meningitis'),
        ranking_terms=('神经内科重点专科', '神经外科重点专科', '卒中中心', '癫痫中心'),
        urgent_terms=('突发单侧无力', '突发言语不清', '意识障碍', '抽搐持续不缓解'),
    ),
    DiseaseProfile(
        key='oncology',
        departments=('肿瘤内科', '肿瘤科', '放疗科', '胸外科', '呼吸科'),
        keywords=('肺癌', '乳腺癌', '结直肠癌', '肝癌', '胃癌', '恶性肿瘤', '肿瘤', '癌症', '肺部结节', 'cancer'),
        explicit_disease_terms=('肺癌', '乳腺癌', '乳癌', '结直肠癌', '大肠癌', '结肠癌', '直肠癌', '肝癌', '肝细胞癌', '胃癌', '恶性肿瘤', '癌症', 'malignant tumor', 'cancer', 'malignancy'),
        ranking_terms=('肿瘤重点专科', '肿瘤中心', '放化疗', '临床试验'),
    ),
    DiseaseProfile(
        key='respiratory',
        departments=('呼吸内科', '感染科', '胸外科', '儿科'),
        keywords=('支气管哮喘', '哮喘', '慢性阻塞性肺疾病', '慢阻肺', '肺炎', '肺结核', '肺痨', '阻塞性睡眠呼吸暂停', '睡眠呼吸暂停', '气短', '咳嗽', 'asthma', 'COPD', 'pneumonia', 'pulmonary tuberculosis', 'OSA', 'sleep apnea'),
        explicit_disease_terms=('支气管哮喘', '哮喘', '过敏性哮喘', '慢性阻塞性肺疾病', '慢阻肺', '肺炎', '社区获得性肺炎', '病毒性肺炎', '细菌性肺炎', '肺结核', '肺痨', '阻塞性睡眠呼吸暂停', '睡眠呼吸暂停', 'asthma', 'COPD', 'pneumonia', 'pulmonary tuberculosis', 'obstructive sleep apnea', 'OSA', 'sleep apnea'),
        ranking_terms=('呼吸科重点专科', '肺部疾病中心', '肺癌中心'),
    ),
    DiseaseProfile(
        key='digestive',
        departments=('消化内科', '胃肠外科', '肝胆胰外科'),
        keywords=('胃食管反流病', '胃食管反流', '反流性食管炎', '消化性溃疡', '胃溃疡', '十二指肠溃疡', '慢性胃炎', '肝硬化', '胆石症', '胆结石', '胰腺炎', '炎症性肠病', '溃疡性结肠炎', '克罗恩病', '腹痛', '腹泻', 'GERD', 'peptic ulcer', 'cirrhosis', 'pancreatitis'),
        explicit_disease_terms=('胃食管反流病', '胃食管反流', '反流性食管炎', 'GERD', '消化性溃疡', '胃溃疡', '十二指肠溃疡', '慢性胃炎', '萎缩性胃炎', '浅表性胃炎', '肝硬化', '胆石症', '胆结石', '胆囊结石', '胆管结石', '胰腺炎', '急性胰腺炎', '慢性胰腺炎', '炎症性肠病', '溃疡性结肠炎', '克罗恩病', 'peptic ulcer', 'cirrhosis', 'pancreatitis'),
        ranking_terms=('消化内科重点专科', '肝胆胰中心', '内镜中心'),
    ),
    DiseaseProfile(
        key='renal_urology',
        departments=('肾内科', '泌尿外科'),
        keywords=('慢性肾脏病', '慢性肾病', '肾功能不全', '肾功能衰竭', '尿路结石', '肾结石', '输尿管结石', '泌尿系结石', '前列腺增生', '尿路感染', '泌尿道感染', '膀胱炎', 'CKD', 'renal insufficiency', 'kidney stones', 'BPH', 'UTI'),
        explicit_disease_terms=('慢性肾脏病', '慢性肾病', '肾功能不全', '肾功能衰竭', '尿路结石', '肾结石', '输尿管结石', '泌尿系结石', '良性前列腺增生', '前列腺增生', '前列腺肥大', '尿路感染', '泌尿道感染', '膀胱炎', 'chronic kidney disease', 'CKD', 'renal insufficiency', 'renal failure', 'kidney stones', 'urolithiasis', 'benign prostatic hyperplasia', 'BPH', 'urinary tract infection', 'UTI'),
        ranking_terms=('肾内科重点专科', '泌尿外科重点专科', '透析中心'),
    ),
    DiseaseProfile(
        key='endocrine',
        departments=('内分泌科', '甲状腺外科', '风湿免疫科'),
        keywords=('糖尿病', '糖尿病足', '甲状腺功能亢进症', '甲亢', 'Graves病', '甲状腺功能减退症', '甲减', '甲状腺结节', '痛风', '高尿酸血症', '骨质疏松症', '骨质疏松', '血糖高', 'diabetes mellitus', 'DM', 'hyperthyroidism', 'hypothyroidism', 'gout', 'osteoporosis'),
        explicit_disease_terms=('糖尿病', '糖尿病足', '1型糖尿病', '2型糖尿病', '妊娠期糖尿病', '甲状腺功能亢进症', '甲亢', 'Graves病', '甲状腺功能减退症', '甲减', '甲状腺结节', '痛风', '高尿酸血症', '骨质疏松症', '骨质疏松', 'diabetes mellitus', 'DM', 'hyperthyroidism', 'hypothyroidism', 'gout', 'osteoporosis'),
        ranking_terms=('内分泌科重点专科', '糖尿病中心', '甲状腺中心'),
    ),
    DiseaseProfile(
        key='dermatology_rheumatology',
        departments=('皮肤科', '风湿免疫科', '变态反应科', '骨科', '康复医学科'),
        keywords=('银屑病', '牛皮癣', '湿疹', '特应性皮炎', '荨麻疹', '类风湿关节炎', '类风湿', '强直性脊柱炎', '强直', '腰椎间盘突出症', '腰椎间盘突出', '骨关节炎', '膝骨关节炎', '皮疹', '瘙痒', '关节痛', 'psoriasis', 'eczema', 'urticaria', 'rheumatoid arthritis', 'ankylosing spondylitis', 'osteoarthritis'),
        explicit_disease_terms=('银屑病', '牛皮癣', '湿疹', '特应性皮炎', '荨麻疹', '风疹块', '风团', '类风湿关节炎', '类风湿', '强直性脊柱炎', '强直', '腰椎间盘突出症', '腰椎间盘突出', '腰突', '骨关节炎', '退行性关节炎', '膝骨关节炎', 'psoriasis', 'eczema', 'urticaria', 'rheumatoid arthritis', 'ankylosing spondylitis', 'osteoarthritis'),
        ranking_terms=('皮肤科重点专科', '风湿免疫科重点专科', '关节置换', '脊柱手术'),
    ),
    DiseaseProfile(
        key='mental_health',
        departments=('精神科', '心理医学科'),
        keywords=('抑郁障碍', '抑郁症', '焦虑障碍', '焦虑症', '双相情感障碍', '双相障碍', '躁郁症', '精神分裂症', 'depression', 'anxiety', 'bipolar', 'schizophrenia'),
        explicit_disease_terms=('抑郁障碍', '抑郁症', '重性抑郁障碍', '焦虑障碍', '焦虑症', '广泛性焦虑障碍', '双相情感障碍', '双相障碍', '躁郁症', '精神分裂症', 'depression', 'anxiety', 'bipolar', 'schizophrenia'),
        ranking_terms=('精神科重点专科', '心理医学中心'),
    ),
    DiseaseProfile(
        key='orthopedics',
        departments=('骨科', '脊柱外科', '康复医学科'),
        keywords=('腰椎间盘突出', '关节疼痛', '骨折', '关节置换', '腰痛'),
        explicit_disease_terms=('腰椎间盘突出症', '腰椎间盘突出', '骨折'),
        ranking_terms=('骨科重点专科', '关节置换', '脊柱手术', '创伤急救'),
    ),
    DiseaseProfile(
        key='diabetes',
        departments=('内分泌科', '血管外科', '骨科'),
        keywords=('糖尿病', '糖尿病足', '血糖高'),
        explicit_disease_terms=('糖尿病', '糖尿病足'),
        ranking_terms=('血糖控制', '血运重建', '创面修复'),
    ),
)


_ASCII_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9 +'_-]*")
_NEGATION_TERMS = ('没有', '否认', '排除', '未见', '不是', '并非', '未诊断', '未确诊')
_AMBIGUOUS_SHORT_TOKENS = {
    'AD', 'AF', 'AS', 'BD', 'CAD', 'CKD', 'DM', 'HF', 'HTN', 'IBD', 'MI', 'MG',
    'MS', 'OA', 'RA', 'TB', 'UTI',
}
_PROFILE_PRIORITY = {
    'diabetes': 0,
    'orthopedics': 1,
    'cardiovascular': 2,
    'neurology': 3,
    'oncology': 4,
    'respiratory': 5,
    'digestive': 6,
    'renal_urology': 7,
    'endocrine': 8,
    'dermatology_rheumatology': 9,
    'mental_health': 10,
}


def _normalize(text: str) -> str:
    return unicodedata.normalize('NFKC', text or '')


def _is_negated(text: str, start: int) -> bool:
    prefix = text[:start].casefold()
    return any(prefix.endswith(term.casefold()) or prefix.endswith(f'{term}的') for term in _NEGATION_TERMS)


def _term_matches(text: str, term: str) -> list[int]:
    normalized_text = _normalize(text)
    normalized_term = _normalize(term)
    if not normalized_term:
        return []
    if _ASCII_TERM_RE.fullmatch(normalized_term):
        pattern = re.compile(rf'(?<![A-Za-z0-9]){re.escape(normalized_term)}(?![A-Za-z0-9])', re.IGNORECASE)
        matches = list(pattern.finditer(normalized_text))
        if normalized_term.upper() in _AMBIGUOUS_SHORT_TOKENS:
            matches = [
                match for match in matches
                if match.group(0) == normalized_term.upper()
                and not (normalized_term.upper() == 'MS' and re.match(r'\s+office\b', normalized_text[match.end():], re.IGNORECASE))
            ]
        return [match.start() for match in matches]
    lowered_text = normalized_text.casefold()
    lowered_term = normalized_term.casefold()
    starts: list[int] = []
    cursor = 0
    while True:
        start = lowered_text.find(lowered_term, cursor)
        if start < 0:
            return starts
        starts.append(start)
        cursor = start + max(1, len(lowered_term))


def _best_profile_match(query: str, field: str) -> DiseaseProfile | None:
    text = _normalize(query or '')
    candidates: list[tuple[int, int, int, DiseaseProfile]] = []
    for profile in PROFILES:
        for term in getattr(profile, field):
            for start in _term_matches(text, term):
                if not _is_negated(text, start):
                    candidates.append((start, -len(term), _PROFILE_PRIORITY.get(profile.key, 99), profile))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3]


def profile_for_query(query: str) -> DiseaseProfile:
    return _best_profile_match(query, 'keywords') or DiseaseProfile(key='general')


def has_explicit_disease(query: str) -> bool:
    return _best_profile_match(query, 'explicit_disease_terms') is not None


def matched_explicit_disease_terms(query: str) -> tuple[str, ...]:
    """Return only explicit disease names that actually occur in the query.

    A profile's keyword list also contains related diseases used for symptom
    routing. It must not be used as a list of diagnoses when the user has
    already supplied a concrete disease name.
    """
    text = _normalize(query or '')
    candidates: list[tuple[int, int, str]] = []
    for profile in PROFILES:
        for term in profile.explicit_disease_terms:
            for start in _term_matches(text, term):
                if not _is_negated(text, start):
                    candidates.append((start, -len(term), term))
    candidates.sort(key=lambda item: (item[0], item[1], item[2].casefold()))
    matched: list[str] = []
    seen: set[str] = set()
    for _, _, term in candidates:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            matched.append(term)
    return tuple(matched)
