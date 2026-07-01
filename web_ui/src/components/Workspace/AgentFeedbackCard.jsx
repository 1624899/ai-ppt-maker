import { useId, useState } from 'react';
import { Bot, ChevronDown } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

import { StaggerContainer, StaggerItem, ScaleButton } from '../Motion/MotionUI';
import { getPageTitle } from '../../utils/jobPresentation';import { uiClassName } from "../../utils/uiClassName";

const AgentFeedbackCard = ({
  summary,
  pages,
  selectedPageIndex,
  onSelectPage
}) => {
  const [collapsed, setCollapsed] = useState(false);
  const contentId = useId();
  const hasPages = pages.length > 0;

  return (
    <section className={uiClassName('agent-card agent-card--hero agent-feedback-card', collapsed && 'is-collapsed')}>
      <div className={uiClassName("agent-avatar")}>
        <Bot size={22} />
      </div>
      <div className={uiClassName("agent-feedback-card__main")}>
        <div className={uiClassName("agent-feedback-card__head")}>
          <div>
            <span className={uiClassName("agent-card__label")}>Agent 反馈</span>
            <h3>{summary.title}</h3>
          </div>
          <ScaleButton
            className={uiClassName("agent-feedback-card__toggle")}
            onClick={() => setCollapsed((current) => !current)}
            aria-expanded={!collapsed}
            aria-controls={contentId}
            aria-label={collapsed ? '展开 Agent 反馈' : '收起 Agent 反馈'}
            title={collapsed ? '展开' : '收起'}>
            
            <ChevronDown size={17} />
          </ScaleButton>
        </div>

        <AnimatePresence initial={false}>
          {!collapsed &&
          <motion.div
            id={contentId}
            className={uiClassName("agent-feedback-card__content")}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
            
              <p>{summary.body}</p>
              {hasPages &&
            <StaggerContainer className={uiClassName("page-outline")} itemCount={pages.length}>
                  {pages.map((page, index) => {
                const selected = index === selectedPageIndex;
                return (
                  <StaggerItem key={page.page_no}>
                        <ScaleButton
                      className={uiClassName(selected && 'is-active')}
                      aria-pressed={selected}
                      onClick={() => onSelectPage(index)}>
                      
                          <span>{page.page_no}</span>
                          {getPageTitle(page)}
                        </ScaleButton>
                      </StaggerItem>);

              })}
                </StaggerContainer>
            }
            </motion.div>
          }
        </AnimatePresence>
      </div>
    </section>);

};

export default AgentFeedbackCard;
