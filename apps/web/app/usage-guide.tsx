import styles from './usage-guide.module.css';

const sections = [
  ['使用流程', 'flow'],
  ['输入疾病或症状', 'input'],
  ['选择地区范围', 'location'],
  ['评分逻辑', 'score'],
  ['专科证据', 'evidence'],
  ['查看结果', 'results'],
  ['信息反馈', 'feedback'],
  ['安全边界', 'safety'],
] as const;

export default function UsageGuidePage() {
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <a className={styles.brand} href="/" aria-label="返回医途首页">医途</a>
        <nav className={styles.headerLinks} aria-label="使用说明导航">
          <span>医院信息导航</span>
          <a className={styles.backLink} href="/">返回首页</a>
        </nav>
      </header>

      <div className={styles.content}>
        <section className={styles.intro} aria-labelledby="usage-guide-title">
          <div>
            <h1 id="usage-guide-title">如何使用医途</h1>
            <p>医途把“我应该去哪家医院”拆成几个容易回答的步骤：先整理疾病方向，再按你的地区和偏好比较公开医院资料。</p>
          </div>
          <aside className={styles.introAside}>
            <strong>先记住一件事</strong>
            <p>医途整理的是就医信息，不是诊断工具。结果中的医院、科室和服务信息，请在就诊前通过官方渠道再次确认。</p>
          </aside>
        </section>

        <section id="flow" className={styles.steps} aria-label="使用流程">
          <article className={styles.step}><span className={styles.stepNumber}>01</span><h2>描述情况</h2><p>输入明确疾病名、疾病别名，或用日常语言描述症状。</p></article>
          <article className={styles.step}><span className={styles.stepNumber}>02</span><h2>设定范围</h2><p>选择省、市、区县和排名范围，也可以选择不考虑地理位置。</p></article>
          <article className={styles.step}><span className={styles.stepNumber}>03</span><h2>比较医院</h2><p>查看评分拆解、专科证据、来源日期和官方服务入口。</p></article>
        </section>

        <div className={styles.body}>
          <div className={styles.sections}>
            <section id="input" className={styles.section} aria-labelledby="input-title">
              <h2 id="input-title">输入疾病或症状</h2>
              <p>在首页的输入框中写下你目前最想解决的问题。内容越具体，系统越容易判断疾病方向和推荐科室。</p>
              <h3>可以这样输入</h3>
              <ul>
                <li>明确疾病名称，例如“脑梗死”“腰椎间盘突出症”。</li>
                <li>常用别名、英文缩写或患者熟悉的说法，词库会帮助系统识别。</li>
                <li>症状、持续时间、诱因和检查报告中的关键结论。</li>
              </ul>
              <p className={styles.note}>如果已经明确写出疾病名称，系统会尽量减少不必要的补充提问；症状描述不等于医学诊断，仍需由医生面诊判断。</p>
            </section>

            <section id="location" className={styles.section} aria-labelledby="location-title">
              <h2 id="location-title">选择地区范围</h2>
              <p>地区既影响医院列表的范围，也会影响“地理位置”这一项评分。你可以按实际出行计划选择范围。</p>
              <ul>
                <li><strong>区县级：</strong>优先查看同区县医院。</li>
                <li><strong>市级：</strong>查看同市不同区县的医院。</li>
                <li><strong>省级：</strong>查看同省不同城市的医院。</li>
                <li><strong>全国：</strong>在全国范围比较公开资料。</li>
                <li><strong>不考虑地理位置：</strong>所有医院的地理位置评分按 100 处理，只比较其他维度。</li>
              </ul>
            </section>

            <section id="score" className={styles.section} aria-labelledby="score-title">
              <h2 id="score-title">评分逻辑</h2>
              <p>综合评分由多个维度组成，结果卡片会列出分数来源。不同偏好会改变排序重点，但不会隐藏证据不足的情况。</p>
              <dl className={styles.scoreList}>
                <div><dt>专科实力</dt><dd>比较国家级专科依据、官网已验证专科依据和全国专科排名。</dd></div>
                <div><dt>医院综合实力</dt><dd>参考医院等级、公开能力信息和可核验的医院资料。</dd></div>
                <div><dt>地理位置</dt><dd>按同区县 100、同市不同区县 85、同省不同城市 70 的规则计算。</dd></div>
                <div><dt>资料与服务</dt><dd>参考官方服务信息、资料时效和公开信息完整度。</dd></div>
              </dl>
              <h3>专科分如何避免重复加分</h3>
              <p>国家级专科依据和专科排名可能来自同一项能力，因此两者不会简单相加，而是只采用专科依据分与排名分中较高的一个。</p>
              <p>全国专科排名分最高为 40 分：第 1 至 20 名的权重由 1 逐步降至 0.7；第 20 至 100 名的权重由 0.7 逐步降至 0.25。排名越靠后，分数越低。</p>
            </section>

            <section id="evidence" className={styles.section} aria-labelledby="evidence-title">
              <h2 id="evidence-title">专科证据</h2>
              <p>专科分数必须能说明“依据从哪里来”。医院卡片中的专科信息按证据类型展示，并区分已验证内容和待核验内容。</p>
              <ul>
                <li><strong>国家级专科依据：</strong>国家级临床重点专科等公开名单或官方文件。</li>
                <li><strong>官网专科依据：</strong>医院官网明确列出的重点科室、专科中心或相关建设信息。</li>
                <li><strong>全国专科排名：</strong>有明确排名来源和名次时，按排名权重计算。</li>
                <li><strong>待核验内容：</strong>没有可靠来源时不会伪装成已验证证据，查看详情时会明确提示。</li>
              </ul>
            </section>

            <section id="results" className={styles.section} aria-labelledby="results-title">
              <h2 id="results-title">查看结果</h2>
              <p>结果页会保留你当前所在的位置，不会因为生成正文或图片而自动跳转。切换区县级、市级、省级和全国范围时，当前内容会保留到新结果完成。</p>
              <ul>
                <li>打开评分拆解，查看每个维度的分数和说明。</li>
                <li>查看专科证据来源、验证状态和数据日期。</li>
                <li>通过医院官网或官方挂号入口核实门诊时间、地址和预约方式。</li>
                <li>使用收藏夹保存候选医院；收藏数据保存在当前浏览器中。</li>
              </ul>
            </section>

            <section id="feedback" className={styles.section} aria-labelledby="feedback-title">
              <h2 id="feedback-title">信息反馈</h2>
              <p>点击顶部的“信息反馈”，可以提交使用中遇到的问题、需要改进的地方或数据纠错建议。</p>
              <ul>
                <li>描述问题出现在哪个页面、哪家医院或哪个评分维度。</li>
                <li>可以上传截图或其他图片，帮助后台复现问题。</li>
                <li>提交后，反馈会进入后台记录，便于后续核查和改进。</li>
              </ul>
            </section>

            <section id="safety" className={styles.section} aria-labelledby="safety-title">
              <h2 id="safety-title">安全边界</h2>
              <p>医途只做公开医院信息整理和就医方向参考，不提供诊断、处方、治疗方案或疗效承诺。</p>
              <p className={styles.note}>出现胸痛、呼吸困难、意识改变、大出血等紧急情况时，请立即前往急诊或拨打 120，不要等待页面推荐结果。</p>
            </section>
          </div>

          <aside className={styles.side} aria-label="本页目录">
            <h2>本页内容</h2>
            <ol>
              {sections.map(([label, id]) => <li key={id}><a href={`#${id}`}>{label}</a></li>)}
            </ol>
            <p>回到首页即可开始一次新的医院信息匹配。</p>
          </aside>
        </div>

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
