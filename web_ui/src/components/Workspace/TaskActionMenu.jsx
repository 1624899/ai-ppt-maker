import { useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';

const VIEWPORT_GAP = 8;
const ANCHOR_GAP = 8;
const FALLBACK_MENU_WIDTH = 184;
const FALLBACK_MENU_HEIGHT = 198;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

const getViewportSize = () => ({
  width: window.innerWidth || document.documentElement.clientWidth,
  height: window.innerHeight || document.documentElement.clientHeight,
});

const getMenuPosition = (anchorEl, menuEl) => {
  const anchorRect = anchorEl.getBoundingClientRect();
  const menuWidth = menuEl?.offsetWidth || FALLBACK_MENU_WIDTH;
  const menuHeight = menuEl?.offsetHeight || FALLBACK_MENU_HEIGHT;
  const viewport = getViewportSize();
  const maxLeft = Math.max(VIEWPORT_GAP, viewport.width - menuWidth - VIEWPORT_GAP);
  const maxTop = Math.max(VIEWPORT_GAP, viewport.height - menuHeight - VIEWPORT_GAP);
  const preferredLeft = anchorRect.right - menuWidth;
  const belowTop = anchorRect.bottom + ANCHOR_GAP;
  const aboveTop = anchorRect.top - menuHeight - ANCHOR_GAP;
  const hasRoomBelow = belowTop + menuHeight <= viewport.height - VIEWPORT_GAP;

  return {
    left: clamp(preferredLeft, VIEWPORT_GAP, maxLeft),
    top: clamp(hasRoomBelow ? belowTop : aboveTop, VIEWPORT_GAP, maxTop),
  };
};

const TaskActionMenu = ({ open, anchorEl, onClose, children }) => {
  const menuRef = useRef(null);

  const updatePosition = useCallback(() => {
    if (!open || !anchorEl) return;
    if (!anchorEl.isConnected) {
      onClose();
      return;
    }
    if (!menuRef.current) return;

    const nextPosition = getMenuPosition(anchorEl, menuRef.current);
    menuRef.current.style.left = `${nextPosition.left}px`;
    menuRef.current.style.top = `${nextPosition.top}px`;
    menuRef.current.style.visibility = 'visible';
  }, [anchorEl, onClose, open]);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open, updatePosition, children]);

  useEffect(() => {
    if (!open) return undefined;

    let frameId = 0;
    const scheduleUpdate = () => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(updatePosition);
    };

    window.addEventListener('resize', scheduleUpdate);
    window.addEventListener('scroll', scheduleUpdate, true);

    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener('resize', scheduleUpdate);
      window.removeEventListener('scroll', scheduleUpdate, true);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return undefined;

    const closeFromOutside = (event) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target)) return;
      if (anchorEl?.contains(target)) return;
      onClose();
    };

    document.addEventListener('pointerdown', closeFromOutside);
    return () => document.removeEventListener('pointerdown', closeFromOutside);
  }, [anchorEl, onClose, open]);

  if (!anchorEl) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          ref={menuRef}
          className="task-action-menu"
          role="menu"
          initial={{ opacity: 0, scale: 0.95, y: -5 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -5 }}
          transition={{ type: 'spring', stiffness: 420, damping: 32, mass: 0.55 }}
          style={{ visibility: 'hidden', transformOrigin: 'top right' }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
};

export default TaskActionMenu;
