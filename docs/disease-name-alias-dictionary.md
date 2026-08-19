# 疾病名称和别名词库

> 版本：v1.0  
> 用途：用于就医推荐流程中的疾病名称识别、疾病别名归一化和科室方向匹配。  
> 说明：本文件是文本匹配词库，不构成医学诊断。仅当用户输入命中“明确疾病词”时，才可跳过疾病补充提问；单独出现的症状、检查结果或身体部位不能当作确诊疾病。

## 1. 数据字段

| 字段 | 含义 |
| --- | --- |
| `key` | 稳定的英文内部标识，创建后不要随意修改 |
| `canonical_name` | 展示和归一化使用的标准疾病名称 |
| `aliases` | 中文简称、俗称、旧称、常见写法 |
| `english_aliases` | 英文全称、缩写、常见大小写写法 |
| `departments` | 推荐优先匹配的科室方向 |
| `explicit_terms` | 可直接视为明确疾病的词；应比普通关键词更严格 |
| `notes` | 消歧或维护说明 |

## 2. 词库条目

### 2.1 神经系统

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `amyotrophic_lateral_sclerosis` | 肌萎缩侧索硬化 | 渐冻症、运动神经元病、卢伽雷病、路格里克病 | ALS、amyotrophic lateral sclerosis、Lou Gehrig disease | 神经内科、神经外科、康复医学科 | 渐冻症、肌萎缩侧索硬化、运动神经元病、ALS |
| `parkinsons_disease` | 帕金森病 | 帕金森、震颤麻痹 | Parkinson、Parkinson disease、Parkinson's disease | 神经内科、神经外科、康复医学科 | 帕金森病、帕金森、震颤麻痹、Parkinson |
| `alzheimers_disease` | 阿尔茨海默病 | 老年痴呆、阿尔茨海默症；认知症仅作为广义认知障碍方向 | Alzheimer、Alzheimer disease、Alzheimer's disease、AD | 神经内科、精神科、老年医学科 | 阿尔茨海默病、阿尔茨海默症、老年痴呆、Alzheimer |
| `epilepsy` | 癫痫 | 羊癫疯、羊角风 | epilepsy | 神经内科、神经外科 | 癫痫、羊癫疯、羊角风、epilepsy |
| `stroke` | 脑卒中 | 中风、卒中 | stroke、cerebrovascular accident、CVA | 神经内科、神经外科、康复医学科 | 脑卒中、中风、卒中、stroke |
| `cerebral_infarction` | 脑梗死 | 脑梗、缺血性脑卒中、脑血栓 | cerebral infarction、ischemic stroke | 神经内科、神经外科、康复医学科 | 脑梗死、脑梗、缺血性脑卒中、脑血栓 |
| `cerebral_hemorrhage` | 脑出血 | 出血性脑卒中、脑溢血 | intracerebral hemorrhage、hemorrhagic stroke | 神经内科、神经外科、康复医学科 | 脑出血、脑溢血、出血性脑卒中 |
| `myasthenia_gravis` | 重症肌无力 | 肌无力（仅在“重症肌无力”语境中） | myasthenia gravis、MG | 神经内科、胸外科 | 重症肌无力、myasthenia gravis、MG |
| `multiple_sclerosis` | 多发性硬化 | 多发性硬化症 | multiple sclerosis、MS | 神经内科、康复医学科 | 多发性硬化、多发性硬化症、multiple sclerosis |
| `migraine` | 偏头痛 | 偏头痛症 | migraine | 神经内科 | 偏头痛、偏头痛症、migraine |
| `meningitis` | 脑膜炎 | 病毒性脑膜炎、细菌性脑膜炎（命中具体词时保留原词） | meningitis | 神经内科、感染科、儿科 | 脑膜炎、病毒性脑膜炎、细菌性脑膜炎 |

### 2.2 心血管系统

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `coronary_artery_disease` | 冠心病 | 冠状动脉粥样硬化性心脏病、缺血性心脏病 | coronary artery disease、CAD、ischemic heart disease | 心血管内科、心脏外科 | 冠心病、冠状动脉粥样硬化性心脏病、CAD |
| `angina_pectoris` | 心绞痛 | 劳力性心绞痛、稳定型心绞痛 | angina pectoris、angina | 心血管内科、胸痛中心 | 心绞痛、劳力性心绞痛、angina |
| `myocardial_infarction` | 心肌梗死 | 心梗、急性心肌梗死 | myocardial infarction、MI、heart attack | 心血管内科、胸痛中心、心脏外科 | 心肌梗死、心梗、急性心肌梗死、MI |
| `heart_failure` | 心力衰竭 | 心衰、充血性心力衰竭 | heart failure、HF、congestive heart failure | 心血管内科 | 心力衰竭、心衰、充血性心力衰竭、HF |
| `atrial_fibrillation` | 心房颤动 | 房颤 | atrial fibrillation、AF、AFib | 心血管内科 | 心房颤动、房颤、atrial fibrillation、AFib |
| `hypertension` | 高血压 | 原发性高血压 | hypertension、HTN | 心血管内科、内分泌科 | 高血压、原发性高血压、hypertension、HTN |
| `aortic_dissection` | 主动脉夹层 | 主动脉夹层动脉瘤 | aortic dissection | 心血管外科、急诊科 | 主动脉夹层、主动脉夹层动脉瘤、aortic dissection |

### 2.3 呼吸系统

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `asthma` | 支气管哮喘 | 哮喘、过敏性哮喘 | asthma、bronchial asthma | 呼吸内科、儿科 | 支气管哮喘、哮喘、过敏性哮喘、asthma |
| `copd` | 慢性阻塞性肺疾病 | 慢阻肺、慢性阻塞性肺气肿 | COPD、chronic obstructive pulmonary disease | 呼吸内科 | 慢性阻塞性肺疾病、慢阻肺、COPD |
| `pneumonia` | 肺炎 | 社区获得性肺炎、病毒性肺炎、细菌性肺炎 | pneumonia | 呼吸内科、感染科、儿科 | 肺炎、社区获得性肺炎、病毒性肺炎、细菌性肺炎 |
| `pulmonary_tuberculosis` | 肺结核 | 肺痨、结核病（需有肺部语境） | pulmonary tuberculosis、TB | 感染科、呼吸内科 | 肺结核、肺痨、pulmonary tuberculosis |
| `lung_cancer` | 肺癌 | 肺部恶性肿瘤、支气管肺癌 | lung cancer、lung carcinoma | 肿瘤科、呼吸内科、胸外科 | 肺癌、肺部恶性肿瘤、支气管肺癌、lung cancer |
| `sleep_apnea` | 阻塞性睡眠呼吸暂停 | 睡眠呼吸暂停、打鼾呼吸暂停 | obstructive sleep apnea、OSA、sleep apnea | 呼吸内科、耳鼻喉科、睡眠医学科 | 阻塞性睡眠呼吸暂停、睡眠呼吸暂停、OSA |

### 2.4 消化、肝胆和胰腺

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `gastroesophageal_reflux` | 胃食管反流病 | 胃食管反流、反流性食管炎、GERD | GERD、gastroesophageal reflux disease | 消化内科、胃食管外科 | 胃食管反流病、胃食管反流、反流性食管炎、GERD |
| `peptic_ulcer` | 消化性溃疡 | 胃溃疡、十二指肠溃疡、胃十二指肠溃疡 | peptic ulcer、gastric ulcer、duodenal ulcer | 消化内科、胃肠外科 | 消化性溃疡、胃溃疡、十二指肠溃疡 |
| `chronic_gastritis` | 慢性胃炎 | 萎缩性胃炎、浅表性胃炎 | chronic gastritis | 消化内科 | 慢性胃炎、萎缩性胃炎、浅表性胃炎 |
| `cirrhosis` | 肝硬化 | 乙肝肝硬化、丙肝肝硬化、失代偿期肝硬化 | cirrhosis | 肝病科、消化内科、感染科 | 肝硬化、乙肝肝硬化、丙肝肝硬化 |
| `gallstones` | 胆石症 | 胆结石、胆囊结石、胆管结石 | gallstones、cholelithiasis | 肝胆外科、消化内科 | 胆石症、胆结石、胆囊结石、胆管结石 |
| `pancreatitis` | 胰腺炎 | 急性胰腺炎、慢性胰腺炎 | pancreatitis | 消化内科、肝胆胰外科 | 胰腺炎、急性胰腺炎、慢性胰腺炎 |
| `inflammatory_bowel_disease` | 炎症性肠病 | 溃疡性结肠炎、克罗恩病 | inflammatory bowel disease、IBD、ulcerative colitis、Crohn disease | 消化内科、胃肠外科 | 炎症性肠病、溃疡性结肠炎、克罗恩病、IBD |

### 2.5 肾脏、泌尿和男性疾病

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `chronic_kidney_disease` | 慢性肾脏病 | 慢性肾病、CKD | chronic kidney disease、CKD | 肾内科 | 慢性肾脏病、慢性肾病、CKD |
| `renal_insufficiency` | 肾功能不全 | 肾功能衰竭（需按原词保留严重程度） | renal insufficiency、renal failure | 肾内科 | 肾功能不全、肾功能衰竭、renal insufficiency |
| `kidney_stones` | 尿路结石 | 肾结石、输尿管结石、泌尿系结石 | kidney stones、urolithiasis | 泌尿外科 | 尿路结石、肾结石、输尿管结石、泌尿系结石 |
| `benign_prostatic_hyperplasia` | 良性前列腺增生 | 前列腺增生、前列腺肥大、BPH | benign prostatic hyperplasia、BPH | 泌尿外科 | 良性前列腺增生、前列腺增生、BPH |
| `urinary_tract_infection` | 尿路感染 | 泌尿道感染、膀胱炎（命中具体词时保留） | urinary tract infection、UTI | 泌尿外科、肾内科、妇科 | 尿路感染、泌尿道感染、膀胱炎、UTI |

### 2.6 内分泌、代谢和骨代谢

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `diabetes_mellitus` | 糖尿病 | 1型糖尿病、2型糖尿病、妊娠期糖尿病 | diabetes mellitus、DM、type 1 diabetes、type 2 diabetes | 内分泌科 | 糖尿病、1型糖尿病、2型糖尿病、妊娠期糖尿病、DM |
| `hyperthyroidism` | 甲状腺功能亢进症 | 甲亢、Graves病、毒性弥漫性甲状腺肿 | hyperthyroidism、Graves disease | 内分泌科 | 甲状腺功能亢进症、甲亢、Graves病、hyperthyroidism |
| `hypothyroidism` | 甲状腺功能减退症 | 甲减、甲状腺功能低下 | hypothyroidism | 内分泌科 | 甲状腺功能减退症、甲减、甲状腺功能低下、hypothyroidism |
| `thyroid_nodule` | 甲状腺结节 | 甲状腺肿物、甲状腺占位 | thyroid nodule | 甲状腺外科、内分泌科 | 甲状腺结节、甲状腺肿物、甲状腺占位、thyroid nodule |
| `gout` | 痛风 | 不将高尿酸血症直接当作痛风别名 | gout | 风湿免疫科、内分泌科 | 痛风、gout |
| `osteoporosis` | 骨质疏松症 | 骨质疏松 | osteoporosis | 骨科、内分泌科、老年医学科 | 骨质疏松症、骨质疏松、osteoporosis |

### 2.7 肿瘤

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `malignant_tumor` | 恶性肿瘤 | 癌症、恶性肿瘤；“癌”过于宽泛，不作为独立明确词 | malignant tumor、cancer、malignancy | 肿瘤科 | 恶性肿瘤、癌症、cancer |
| `breast_cancer` | 乳腺癌 | 乳癌、乳腺恶性肿瘤 | breast cancer | 乳腺外科、肿瘤科 | 乳腺癌、乳癌、乳腺恶性肿瘤 |
| `colorectal_cancer` | 结直肠癌 | 大肠癌、结肠癌、直肠癌 | colorectal cancer、colon cancer、rectal cancer | 胃肠外科、肿瘤科 | 结直肠癌、大肠癌、结肠癌、直肠癌 |
| `liver_cancer` | 肝癌 | 肝细胞癌、原发性肝癌 | liver cancer、hepatocellular carcinoma、HCC | 肝胆外科、肿瘤科 | 肝癌、肝细胞癌、原发性肝癌、HCC |
| `gastric_cancer` | 胃癌 | 胃部恶性肿瘤 | gastric cancer | 胃肠外科、肿瘤科 | 胃癌、胃部恶性肿瘤、gastric cancer |

### 2.8 皮肤、骨科和风湿免疫

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `psoriasis` | 银屑病 | 牛皮癣 | psoriasis | 皮肤科 | 银屑病、牛皮癣、psoriasis |
| `eczema` | 湿疹 | 特应性皮炎（命中具体词时保留） | eczema、atopic dermatitis | 皮肤科、变态反应科 | 湿疹、特应性皮炎、eczema |
| `urticaria` | 荨麻疹 | 风疹块、风团 | urticaria、hives | 皮肤科、变态反应科 | 荨麻疹、风疹块、风团、urticaria |
| `rheumatoid_arthritis` | 类风湿关节炎 | 类风湿 | rheumatoid arthritis、RA | 风湿免疫科 | 类风湿关节炎、类风湿、rheumatoid arthritis、RA |
| `ankylosing_spondylitis` | 强直性脊柱炎 | 强直、AS | ankylosing spondylitis、AS | 风湿免疫科、脊柱外科 | 强直性脊柱炎、强直、ankylosing spondylitis |
| `lumbar_disc_herniation` | 腰椎间盘突出症 | 腰突、腰椎间盘突出 | lumbar disc herniation | 骨科、脊柱外科、康复医学科 | 腰椎间盘突出症、腰椎间盘突出、腰突 |
| `osteoarthritis` | 骨关节炎 | 退行性关节炎、膝骨关节炎 | osteoarthritis、OA | 骨科、关节外科、康复医学科 | 骨关节炎、退行性关节炎、膝骨关节炎、osteoarthritis |

### 2.9 精神心理

| key | 标准疾病名 | 中文别名 | 英文别名 | 关联科室 | 明确疾病词 |
| --- | --- | --- | --- | --- | --- |
| `depressive_disorder` | 抑郁障碍 | 抑郁症、重性抑郁障碍 | depressive disorder、depression、MDD | 精神科、心理医学科 | 抑郁障碍、抑郁症、重性抑郁障碍、depression |
| `anxiety_disorder` | 焦虑障碍 | 焦虑症、广泛性焦虑障碍 | anxiety disorder、anxiety、GAD | 精神科、心理医学科 | 焦虑障碍、焦虑症、广泛性焦虑障碍、anxiety |
| `bipolar_disorder` | 双相情感障碍 | 双相障碍、躁郁症 | bipolar disorder、bipolar、BD | 精神科 | 双相情感障碍、双相障碍、躁郁症、bipolar |
| `schizophrenia` | 精神分裂症 | （不建议使用带污名化的俗称） | schizophrenia | 精神科 | 精神分裂症、schizophrenia |

## 3. 不应直接判定为明确疾病的词

这些词可以用于辅助推断科室或继续提问，但不能单独使 `has_explicit_disease()` 返回 `True`：

### 症状词

`头痛`、`头晕`、`手脚无力`、`肢体麻木`、`胸痛`、`心慌`、`气短`、`咳嗽`、`发热`、`腹痛`、`腹泻`、`便血`、`恶心`、`呕吐`、`腰痛`、`关节痛`、`皮疹`、`瘙痒`、`失眠`、`记忆力下降`、`抽搐`、`震颤`、`走路不稳`。

### 检查结果或风险因素

`血糖高`、`血压高`、`尿酸高`、`血脂高`、`转氨酶高`、`肺部结节`、`甲状腺抗体阳性`、`核磁异常`、`CT异常`、`心电图异常`、`体检发现`、`家族史`。

### 不完整或容易歧义的短词

`肌无力`、`结节`、`肿块`、`肿瘤待排`、`感染`、`炎症`、`贫血`、`过敏`。这些词需要上下文或检查结果，不应直接当成已确诊疾病。

## 4. 识别与归一化规则

1. **先标准化文本**：去除首尾空格，统一大小写，兼容全角/半角标点；英文缩写按大小写不敏感匹配。
2. **优先匹配更长词**：例如先匹配“急性心肌梗死”，再匹配“心肌梗死”；避免短词覆盖更具体疾病。
3. **明确词和辅助词分离**：`keywords` 可用于科室方向推断，`explicit_terms` 才能用于跳过补充提问。
4. **保留原始严重程度**：如“急性脑梗死”“失代偿期肝硬化”命中标准疾病后，原始输入仍应保留给后续提示词和安全提示。
5. **同句多病并存时**：保留所有命中的疾病，按用户明确提到的疾病顺序记录；推荐主科室时可优先使用首个明确疾病，或交给多疾病规则处理。
6. **否定语句需拦截**：`没有糖尿病`、`排除脑梗死`、`不是帕金森` 不应判定为用户患有对应疾病。当前实现会检查“没有、否认、排除、未见、不是、并非、未诊断、未确诊”等否定词的局部窗口。
7. **不把医院专科名当疾病**：`神经内科`、`心血管中心`、`肿瘤中心` 等只用于科室/机构匹配，不作为明确疾病。
8. **英文缩写边界**：`ALS`、`COPD`、`GERD` 等按独立词匹配；`AD`、`MS`、`MI` 等短缩写要求用户使用大写，且会排除已知非医学语境（例如 `MS Office`）。
9. **安全边界**：识别到明确疾病也只代表用户输入了一个疾病名称，不代表系统完成了诊断或判断病情严重程度。

## 5.1 当前已接入的运行时画像

当前后端已经接入以下画像键：

`cardiovascular`、`neurology`、`oncology`、`respiratory`、`digestive`、`renal_urology`、`endocrine`、`dermatology_rheumatology`、`mental_health`、`orthopedics`、`diabetes`。

其中 `diabetes` 和 `orthopedics` 保留原有内部键，避免影响既有评分和检索逻辑；新增疾病会归入相应系统画像，而不是为每个别名创建新的画像键。

## 6. 维护流程

新增词条时至少补充：

- 一个稳定的 `key`；
- 一个标准疾病名；
- 至少一个中文别名或英文写法；
- 关联科室；
- 明确疾病词与普通辅助词的区分；
- 一个正例和一个不应误判的反例测试。

建议每次新增别名后同步更新自动化测试，至少覆盖：

```text
正例：渐冻症、肌萎缩侧索硬化、ALS -> amyotrophic_lateral_sclerosis
正例：帕金森、Parkinson -> parkinsons_disease
反例：手脚无力、头晕、血糖高 -> general / 非明确疾病
反例：没有糖尿病、排除脑梗死 -> 不判定为已患病
```

## 7. 当前词库的使用边界

本词库用于：

- 判断用户是否已经明确输入疾病名称；
- 为推荐流程提供初始科室方向；
- 统一疾病名称，便于后续专科证据和医院匹配；
- 减少同一疾病因简称、俗称或英文缩写造成的重复提问。

本词库不用于：

- 自动诊断；
- 判断疾病分期、严重程度或治疗方案；
- 替代医生问诊、检查和急诊分诊；
- 仅凭症状给出确定疾病结论。
