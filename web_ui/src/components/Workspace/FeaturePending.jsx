import { Wrench } from 'lucide-react';
import clsx from 'clsx';

const FeaturePending = ({ title = '功能待接入', children, compact = false }) => (
  <div className={clsx('feature-pending', compact && 'feature-pending--compact')}>
    <Wrench size={compact ? 15 : 17} />
    <span>
      <strong>{title}</strong>
      {children && <small>{children}</small>}
    </span>
  </div>
);

export default FeaturePending;
