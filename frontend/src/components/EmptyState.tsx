interface EmptyStateProps {
  title: string
  description?: string
}

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <section className="empty-state">
      <div className="empty-state__badge">Coming Soon</div>
      <h1 className="empty-state__title">{title}</h1>
      {description && <p className="empty-state__desc">{description}</p>}
    </section>
  )
}
