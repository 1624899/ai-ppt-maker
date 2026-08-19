import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { collectJobImages } from './jobImages';
import { getJobProgress, isJobActive } from './jobProgress';
import './styles.css';

const api = async (url, options) => {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || '请求失败');
  return payload;
};

const MobileApp = () => {
  const [jobs, setJobs] = useState([]), [error, setError] = useState('');
  const [content, setContent] = useState(''), [pageCount, setPageCount] = useState(5);
  const [selectedJob, setSelectedJob] = useState(null), [plan, setPlan] = useState(null), [busy, setBusy] = useState('');
  const refreshJobs = async () => { setBusy('history'); setError(''); try { const data = await api('/api/jobs'); setJobs(Array.isArray(data.items) ? data.items : []); } finally { setBusy(''); } };
  useEffect(() => { refreshJobs().catch((reason) => setError(reason.message)); }, []);
  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const data = await api('/api/jobs');
        const nextJobs = Array.isArray(data.items) ? data.items : [];
        setJobs(nextJobs);
        if (selectedJob?.job_id && (isJobActive(selectedJob) || nextJobs.some((job) => job.job_id === selectedJob.job_id && isJobActive(job)))) {
          setSelectedJob(await api(`/api/jobs/${selectedJob.job_id}`));
        }
      } catch {
        // 自动刷新失败时保留当前页面状态，用户仍可手动刷新。
      }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [selectedJob?.job_id, selectedJob?.status]);
  const openJob = async (jobId) => { setBusy('open'); setError(''); setPlan(null); try { const detail = await api(`/api/jobs/${jobId}`); setSelectedJob(detail); const planResult = await Promise.allSettled([api(`/api/jobs/${jobId}/plan`)]); if (planResult[0].status === 'fulfilled') { const data = planResult[0].value; setPlan(data.plan || data); } requestAnimationFrame(() => document.getElementById('mobile-job-detail')?.scrollIntoView({ behavior: 'smooth' })); } catch (reason) { setError(`打开历史任务失败：${reason.message}`); } finally { setBusy(''); } };
  const createJob = async (event) => { event.preventDefault(); if (!content.trim()) return setError('请输入 PPT 内容'); setBusy('create'); try { const body = new FormData(); body.append('content', content); body.append('page_count', String(pageCount)); body.append('workflow_mode', 'guided'); body.append('job_target', 'editable_ppt'); const data = await api('/api/jobs', { method: 'POST', body }); setContent(''); await refreshJobs(); await openJob(data.job_id); } catch (reason) { setError(reason.message); } finally { setBusy(''); } };
  const savePlan = async () => { if (!selectedJob || !plan) return; setBusy('save'); try { await api(`/api/jobs/${selectedJob.job_id}/plan`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(plan) }); setError('规划已保存'); } catch (reason) { setError(reason.message); } finally { setBusy(''); } };
  const deliver = async (mode) => { if (!selectedJob) return; setBusy('deliver'); try { await api(`/api/jobs/${selectedJob.job_id}/deliver`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ delivery_key: 'editable_ppt', layer_mode: mode }) }); await openJob(selectedJob.job_id); } catch (reason) { setError(reason.message); } finally { setBusy(''); } };
  const jobImages = collectJobImages(selectedJob);
  const selectedProgress = getJobProgress(selectedJob);
  return <main className="mobile-shell">
    <header className="mobile-header"><span>AI PPT Maker</span><strong>移动工作台</strong></header>
    <section className="mobile-hero"><h1>创建和管理 PPT</h1><p>手机和平板端完整支持任务创建、规划编辑和 PPT 导出。</p><form onSubmit={createJob}><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="粘贴汇报大纲、会议纪要或 PPT 内容" /><label>页数 <input type="number" min="1" max="30" value={pageCount} onChange={(event) => setPageCount(event.target.value)} /></label><button type="submit" disabled={busy === 'create'}>{busy === 'create' ? '提交中...' : '新建 PPT 任务'}</button></form></section>
    <section className="mobile-section"><div className="section-title"><h2>历史任务</h2><div className="history-tools"><span>{jobs.length} 条</span><button type="button" onClick={() => refreshJobs().catch((reason) => setError(reason.message))} disabled={busy === 'history'}>{busy === 'history' ? '刷新中' : '刷新'}</button></div></div>{error && <p className="error">{error}</p>}<div className="job-list">{jobs.map((job) => { const progress = getJobProgress(job); return <button className="job-item" type="button" key={job.job_id} onClick={() => openJob(job.job_id)} disabled={busy === 'open'}><strong>{job.title || '未命名 PPT 任务'}</strong><span>{progress.statusLabel} · {job.page_count || 0} 页 · {progress.percent}%</span><span className="progress-track"><span style={{ width: `${progress.percent}%` }} /></span>{progress.stageLabel && <small>{progress.stageLabel}</small>}</button>; })}</div></section>
    {selectedJob && <section className="mobile-section" id="mobile-job-detail"><div className="section-title"><h2>{selectedJob.title || '任务详情'}</h2><button type="button" onClick={() => setSelectedJob(null)}>关闭</button></div><div className="detail-progress"><div><strong>{selectedProgress.statusLabel}</strong><span>{selectedProgress.percent}%</span></div><span className="progress-track"><span style={{ width: `${selectedProgress.percent}%` }} /></span>{selectedProgress.stageLabel && <small>{selectedProgress.stageLabel}</small>}</div><p>{selectedJob.job_id}</p>{jobImages.length > 0 ? <div className="preview-list">{jobImages.map((item) => <figure className="preview-item" key={`${item.pageNo}-${item.label}-${item.url}`}><a href={item.url} target="_blank" rel="noreferrer"><img src={item.url} alt={`第 ${item.pageNo} 页${item.label}`} loading="lazy" /></a><figcaption>第 {item.pageNo} 页 · {item.label}</figcaption></figure>)}</div> : <p className="empty-plan">该任务暂未生成图片。</p>}{plan?.pages?.map((page, index) => <div className="plan-item" key={page.page_no}><input value={page.title || ''} onChange={(event) => setPlan({ ...plan, pages: plan.pages.map((item, itemIndex) => itemIndex === index ? { ...item, title: event.target.value } : item) })} /><textarea value={(page.bullets || []).join('\n')} onChange={(event) => setPlan({ ...plan, pages: plan.pages.map((item, itemIndex) => itemIndex === index ? { ...item, bullets: event.target.value.split('\n').filter(Boolean) } : item) })} /><small>{page.layout_family || '未选择版式'}</small></div>)}{!plan?.pages?.length && <p className="empty-plan">该任务暂无可编辑规划，仍可查看任务状态和已有结果。</p>}{plan?.pages?.length > 0 && <div className="actions"><button type="button" onClick={savePlan}>保存规划</button><button type="button" onClick={() => deliver('separate_slides')}>生成拆分版</button></div>}</section>}
  </main>;
};

createRoot(document.getElementById('root')).render(<StrictMode><MobileApp /></StrictMode>);
if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));
