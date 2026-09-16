export default function PageHeader({ eyebrow, title, description, aside }) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {aside ? <div>{aside}</div> : null}
    </header>
  )
}
