'use client';

import { ClipboardEvent, DragEvent, FormEvent, useEffect, useState } from 'react';

import { FeedbackAttachment, FeedbackCategory, submitFeedback } from '../lib/api';
import styles from './page.module.css';

const CATEGORY_LABELS: Record<FeedbackCategory, string> = {
  bug: '遇到问题',
  improvement: '改进建议',
  other: '其他反馈',
};

const MAX_ATTACHMENTS = 5;
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const ACCEPTED_IMAGE_TYPES = new Set<FeedbackAttachment['content_type']>(['image/jpeg', 'image/png', 'image/webp']);

type DraftAttachment = FeedbackAttachment & { preview: string };

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error || new Error('读取图片失败'));
    reader.readAsDataURL(file);
  });
}

export default function FeedbackDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [category, setCategory] = useState<FeedbackCategory>('improvement');
  const [message, setMessage] = useState('');
  const [contact, setContact] = useState('');
  const [attachments, setAttachments] = useState<DraftAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState('');
  const [state, setState] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');

  useEffect(() => {
    if (open) {
      setState('idle');
      setAttachmentError('');
    }
  }, [open]);

  if (!open) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (message.trim().length < 10) {
      setState('error');
      return;
    }
    setState('submitting');
    try {
      const payload = { category, message: message.trim(), contact: contact.trim() } as Parameters<typeof submitFeedback>[0];
      if (attachments.length) {
        payload.attachments = attachments.map(({ preview: _preview, ...attachment }) => attachment);
      }
      await submitFeedback(payload);
      setMessage('');
      setContact('');
      setAttachments([]);
      setState('success');
    } catch {
      setState('error');
    }
  }

  async function addFiles(fileList: FileList | File[]) {
    setAttachmentError('');
    const files = Array.from(fileList);
    if (attachments.length + files.length > MAX_ATTACHMENTS) {
      setAttachmentError(`最多添加 ${MAX_ATTACHMENTS} 张图片。`);
      return;
    }
    const next: DraftAttachment[] = [];
    for (const file of files) {
      if (!ACCEPTED_IMAGE_TYPES.has(file.type as FeedbackAttachment['content_type'])) {
        setAttachmentError('仅支持 JPG、PNG 或 WebP 图片。');
        continue;
      }
      if (file.size > MAX_ATTACHMENT_BYTES) {
        setAttachmentError('单张图片不能超过 5MB。');
        continue;
      }
      try {
        const preview = await fileToDataUrl(file);
        next.push({
          filename: file.name,
          content_type: file.type as FeedbackAttachment['content_type'],
          data: preview.split(',', 2)[1] || '',
          preview,
        });
      } catch {
        setAttachmentError('读取图片失败，请重试。');
      }
    }
    if (next.length) setAttachments((current) => [...current, ...next]);
  }

  function handleDrop(event: DragEvent<HTMLFormElement>) {
    event.preventDefault();
    void addFiles(event.dataTransfer.files);
  }

  function handlePaste(event: ClipboardEvent<HTMLFormElement>) {
    if (event.clipboardData.files.length) void addFiles(event.clipboardData.files);
  }

  return <div className={styles.feedbackBackdrop} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={styles.feedbackDialog} role="dialog" aria-modal="true" aria-labelledby="feedback-title">
      <header className={styles.feedbackDialogHeader}>
        <div><span>帮助我们改进</span><h2 id="feedback-title">信息反馈</h2></div>
        <button type="button" className={styles.feedbackClose} aria-label="关闭反馈" onClick={onClose}>×</button>
      </header>
      {state === 'success' ? <div className={styles.feedbackSuccess} role="status"><strong>反馈已提交</strong><p>感谢你的反馈，我们会在后台查看。</p><button type="button" onClick={onClose}>关闭</button></div> : <form className={styles.feedbackForm} onSubmit={handleSubmit} onDrop={handleDrop} onDragOver={(event) => event.preventDefault()} onPaste={handlePaste}>
        <label><span>反馈类型</span><select aria-label="反馈类型" value={category} onChange={(event) => setCategory(event.target.value as FeedbackCategory)}><option value="improvement">改进建议</option><option value="bug">遇到问题</option><option value="other">其他反馈</option></select></label>
        <label><span>反馈内容</span><textarea aria-label="反馈内容" value={message} onChange={(event) => setMessage(event.target.value)} minLength={10} maxLength={2000} rows={6} placeholder="请描述需要改进的地方或遇到的问题" required /></label>
        <div className={styles.feedbackAttachmentField}><div className={styles.feedbackAttachmentHeader}><span>问题截图（可选）</span><span>{attachments.length}/{MAX_ATTACHMENTS}</span></div><label className={styles.feedbackUploadLabel}><input aria-label="添加图片" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => { if (event.target.files) void addFiles(event.target.files); event.currentTarget.value = ''; }} /><span>选择图片</span><small>也可以直接粘贴或拖拽图片</small></label>{attachments.length > 0 && <div className={styles.feedbackAttachmentGrid}>{attachments.map((attachment, index) => <div className={styles.feedbackAttachment} key={`${attachment.filename}-${index}`}><img src={attachment.preview} alt={attachment.filename} /><div><span title={attachment.filename}>{attachment.filename}</span><button type="button" aria-label={`移除图片 ${attachment.filename}`} onClick={() => setAttachments((current) => current.filter((_, itemIndex) => itemIndex !== index))}>移除</button></div></div>)}</div>}{attachmentError && <p className={styles.feedbackError} role="alert">{attachmentError}</p>}</div>
        <label><span>联系方式（可选）</span><input aria-label="联系方式（可选）" value={contact} onChange={(event) => setContact(event.target.value)} maxLength={200} placeholder="邮箱或其他联系方式" /></label>
        {state === 'error' && <p className={styles.feedbackError} role="alert">请至少填写 10 个字，提交失败时请稍后重试。</p>}
        <div className={styles.feedbackActions}><button type="button" onClick={onClose}>取消</button><button type="submit" className={styles.feedbackSubmit} disabled={state === 'submitting'}>{state === 'submitting' ? '提交中…' : '提交反馈'}</button></div>
      </form>}
    </section>
  </div>;
}

export { CATEGORY_LABELS };
