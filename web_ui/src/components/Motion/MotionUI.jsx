import { motion, useReducedMotion } from 'framer-motion';
import { forwardRef } from 'react';

const DEFAULT_STAGGER_LIMIT = 16;

// 基础淡入滑动效果
export const FadeIn = ({ children, delay = 0, className = '', duration = 0.4, ...props }) => {
  const shouldReduceMotion = useReducedMotion();
  const enabled = !shouldReduceMotion;

  return (
    <motion.div
      initial={enabled ? { opacity: 0, y: 8 } : false}
      animate={{ opacity: 1, y: 0 }}
      exit={enabled ? { opacity: 0, y: -8 } : undefined}
      transition={{ duration: enabled ? duration : 0, delay: enabled ? delay : 0, ease: 'easeOut' }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
};

// 列表容器：设置子元素的交错显示
export const StaggerContainer = ({
  children,
  className = '',
  delayChildren = 0.02,
  staggerChildren = 0.035,
  itemCount = 0,
  maxAnimatedItems = DEFAULT_STAGGER_LIMIT,
  disabled = false,
  ...props
}) => {
  const shouldReduceMotion = useReducedMotion();
  const shouldAnimate = !disabled && !shouldReduceMotion && (!itemCount || itemCount <= maxAnimatedItems);

  return (
    <motion.div
      variants={{
        hidden: { opacity: 1 },
        show: {
          opacity: 1,
          transition: {
            delayChildren,
            staggerChildren
          }
        }
      }}
      initial={shouldAnimate ? 'hidden' : false}
      animate="show"
      data-motion={shouldAnimate ? 'stagger' : 'static'}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
};

// 列表项：配合 StaggerContainer 使用
export const StaggerItem = ({ children, className = '', ...props }) => {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 8 },
        show: { opacity: 1, y: 0, transition: { duration: 0.22, ease: [0.22, 1, 0.36, 1] } }
      }}
      className={className}
      {...props}
    >
      {children}
    </motion.div>
  );
};

// 物理反馈按钮
export const ScaleButton = forwardRef(({ children, className = '', onClick, disabled, type = 'button', ...props }, ref) => {
  const shouldReduceMotion = useReducedMotion();
  const canAnimate = !disabled && !shouldReduceMotion;

  return (
    <motion.button
      ref={ref}
      type={type}
      className={className}
      onClick={onClick}
      disabled={disabled}
      whileHover={canAnimate ? { scale: 1.01 } : undefined}
      whileTap={canAnimate ? { scale: 0.98 } : undefined}
      transition={{ type: 'spring', stiffness: 420, damping: 28, mass: 0.45 }}
      {...props}
    >
      {children}
    </motion.button>
  );
});

ScaleButton.displayName = 'ScaleButton';
