import { CheckCircle2, LoaderCircle, RotateCcw, X } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

const UnsavedPlanConfirmModal = ({
  open,
  pending,
  onSaveAndConfirm,
  onDiscardAndConfirm,
  onCancel,
}) => (
  <AnimatePresence>
    {open && (
      <motion.div
        className="unsaved-plan-modal"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <button type="button" className="unsaved-plan-modal__backdrop" aria-label="继续编辑" onClick={onCancel} />
        <motion.section
          className="unsaved-plan-modal__shell"
          initial={{ scale: 0.97, y: 14 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.97, y: 14 }}
          role="dialog"
          aria-modal="true"
          aria-label="检测到未保存修改"
        >
          <header className="unsaved-plan-modal__head">
            <div>
              <h2>检测到未保存修改</h2>
              <p>你刚才修改了规划内容。开始生成前，可以先保存这些修改，或放弃修改并使用上一次保存的规划。</p>
            </div>
            <button type="button" className="icon-button" onClick={onCancel} title="继续编辑" aria-label="继续编辑">
              <X size={18} />
            </button>
          </header>

          <div className="unsaved-plan-modal__actions">
            <button type="button" className="btn btn-primary" onClick={onSaveAndConfirm} disabled={Boolean(pending)}>
              {pending === 'save' ? <LoaderCircle className="spin" size={16} /> : <CheckCircle2 size={16} />}
              {pending === 'save' ? '保存并提交中...' : '保存修改并开始生成'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={onDiscardAndConfirm} disabled={Boolean(pending)}>
              {pending === 'discard' ? <LoaderCircle className="spin" size={16} /> : <RotateCcw size={16} />}
              {pending === 'discard' ? '提交中...' : '放弃修改，按已保存规划生成'}
            </button>
            <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={Boolean(pending)}>
              继续编辑
            </button>
          </div>
        </motion.section>
      </motion.div>
    )}
  </AnimatePresence>
);

export default UnsavedPlanConfirmModal;
