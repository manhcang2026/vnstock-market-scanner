export default function PlaceholderPanel({ title, children }) {
  return (
    <section className="panel">
      <header className="panel-header">
        <h2>{title}</h2>
      </header>
      <div className="panel-body">{children}</div>
    </section>
  )
}
