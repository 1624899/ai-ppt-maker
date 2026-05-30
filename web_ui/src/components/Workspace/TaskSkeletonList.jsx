const TaskSkeletonList = ({ count = 4 }) => (
  <div className="task-skeleton-list" aria-hidden="true">
    {Array.from({ length: count }, (_, index) => (
      <div className="task-skeleton-card" key={index}>
        <span className="task-skeleton-card__thumb skeleton-block" />
        <span className="task-skeleton-card__content">
          <span className="skeleton-block skeleton-line skeleton-line--title" />
          <span className="skeleton-block skeleton-line skeleton-line--meta" />
        </span>
        <span className="task-skeleton-card__action skeleton-block" />
      </div>
    ))}
  </div>
);

export default TaskSkeletonList;
