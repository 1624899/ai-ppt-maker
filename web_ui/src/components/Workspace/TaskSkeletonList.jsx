import { uiClassName } from "../../utils/uiClassName";const TaskSkeletonList = ({ count = 4 }) =>
<div className={uiClassName("task-skeleton-list")} aria-hidden="true">
    {Array.from({ length: count }, (_, index) =>
  <div className={uiClassName("task-skeleton-card")} key={index}>
        <span className={uiClassName("task-skeleton-card__thumb skeleton-block")} />
        <span className={uiClassName("task-skeleton-card__content")}>
          <span className={uiClassName("skeleton-block skeleton-line skeleton-line--title")} />
          <span className={uiClassName("skeleton-block skeleton-line skeleton-line--meta")} />
        </span>
        <span className={uiClassName("task-skeleton-card__action skeleton-block")} />
      </div>
  )}
  </div>;


export default TaskSkeletonList;
