import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, GitBranch } from 'lucide-react';
import clsx from 'clsx';
import { WORKFLOW_MODE_OPTIONS, normalizeWorkflowMode } from '../../utils/workflowMode';

const MODE_ICONS = {
  auto: CheckCircle2,
  guided: GitBranch,
};

const WorkflowModeSwitch = ({ value, onChange, disabled = false }) => {
  const currentValue = normalizeWorkflowMode(value);
  const previousValueRef = useRef(currentValue);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    if (previousValueRef.current === currentValue) return undefined;
    previousValueRef.current = currentValue;
    setSwitching(true);
    const timer = window.setTimeout(() => setSwitching(false), 320);
    return () => window.clearTimeout(timer);
  }, [currentValue]);

  return (
    <div
      className={clsx(
        'workflow-mode-switch',
        `workflow-mode-switch--${currentValue}`,
        switching && 'is-switching',
      )}
      role="radiogroup"
      aria-label="生成工作流"
    >
      {WORKFLOW_MODE_OPTIONS.map((option) => {
        const Icon = MODE_ICONS[option.value] || CheckCircle2;
        const active = option.value === currentValue;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            className={clsx(`workflow-mode-switch__option--${option.value}`, active && 'is-active')}
            onClick={() => onChange?.(option.value)}
            disabled={disabled}
          >
            <Icon size={16} />
            <span>
              <strong>{option.label}</strong>
              <small>{option.description}</small>
            </span>
          </button>
        );
      })}
    </div>
  );
};

export default WorkflowModeSwitch;
