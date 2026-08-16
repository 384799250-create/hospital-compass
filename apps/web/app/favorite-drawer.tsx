import { FavoriteHospital } from '../lib/local-profile';
import styles from './page.module.css';

type FavoriteHospitalListProps = {
  favorites: FavoriteHospital[];
  onRemove: (hospitalId: string) => void;
  onOpenDetail: (hospitalId: string) => void;
  variant?: 'drawer' | 'page';
};

type FavoriteDrawerProps = FavoriteHospitalListProps & {
  open: boolean;
  onClose: () => void;
  onExpand: () => void;
};

export function FavoriteHospitalList({
  favorites,
  onRemove,
  onOpenDetail,
  variant = 'drawer',
}: FavoriteHospitalListProps) {
  if (!favorites.length) {
    return <div className={styles.favoriteEmpty} role="status">
      <strong>暂未收藏医院</strong>
      <p>在医院推荐结果中点击“收藏医院”，即可在这里集中查看。</p>
    </div>;
  }

  return <ul className={`${styles.favoriteList} ${variant === 'page' ? styles.favoriteListPage : ''}`}>
    {favorites.map((hospital) => <li key={hospital.id} className={styles.favoriteItem}>
      <div className={styles.favoriteItemMain}>
        <div>
          <h3>{hospital.name}</h3>
          <p>{[hospital.tier, hospital.city].filter(Boolean).join(' · ') || '医院信息待补充'}</p>
        </div>
        <span className={styles.favoriteScore}>{hospital.score === null ? '暂无保存评分' : `综合评分 ${hospital.score.toFixed(1)}`}</span>
      </div>
      <p className={styles.favoriteAddress}>{hospital.address || '地址信息待补充'}</p>
      {hospital.department && <p className={styles.favoriteDepartment}>推荐科室：{hospital.department}</p>}
      <div className={styles.favoriteItemActions}>
        <button type="button" onClick={() => onOpenDetail(hospital.id)}>查看详情</button>
        <button type="button" className={styles.favoriteRemove} aria-label={`取消收藏 ${hospital.name}`} title="取消收藏" onClick={() => onRemove(hospital.id)}>×</button>
      </div>
    </li>)}
  </ul>;
}

export function FavoriteDrawer({
  open,
  favorites,
  onClose,
  onExpand,
  onRemove,
  onOpenDetail,
}: FavoriteDrawerProps) {
  if (!open) return null;

  return <>
    <button type="button" className={styles.favoriteBackdrop} aria-label="关闭收藏夹" onClick={onClose} />
    <aside className={styles.favoriteDrawer} aria-label="收藏夹" aria-modal="true" role="dialog">
      <header className={styles.favoriteDrawerHeader}>
        <div><span>我的收藏</span><h2>收藏夹</h2><p>已收藏 {favorites.length} 家医院</p></div>
        <div className={styles.favoriteDrawerTools}>
          <button type="button" aria-label="放大查看收藏夹" title="放大查看" onClick={onExpand}>⤢</button>
          <button type="button" aria-label="关闭收藏夹" title="关闭" onClick={onClose}>×</button>
        </div>
      </header>
      <FavoriteHospitalList favorites={favorites} onRemove={onRemove} onOpenDetail={onOpenDetail} />
    </aside>
  </>;
}
