import styles from './legal-footer.module.css';

type LegalFooterProps = {
  showHomeLink?: boolean;
};

export default function LegalFooter({ showHomeLink = false }: LegalFooterProps) {
  return (
    <footer className={styles.footer}>
      <span>公开资料整理</span>
      <span>仅供就医信息参考</span>
      <span>不替代医生诊断</span>
      <a href="https://beian.miit.gov.cn/" target="_blank" rel="noreferrer">
        粤ICP备2026127500号
      </a>
      {showHomeLink && <a href="/">返回首页</a>}
    </footer>
  );
}
