// Past questions and answers from GET /qa (newest first).
const time = (iso) => new Date(iso).toLocaleTimeString()

export default function QaHistory({ items }) {
  return (
    <section className="panel qa-panel" aria-label="Questions and answers">
      <h2>Q&amp;A history</h2>
      {items.length === 0 && <p>No questions yet.</p>}
      <ul className="qa-list">
        {items.map((item) => (
          <li key={item.id} className="qa-item">
            <p className="meta">
              {time(item.asked_at)} · {item.language.toUpperCase()} · confidence{' '}
              {Math.round(item.confidence * 100)}% · {item.latency_ms} ms · frames{' '}
              {item.frame_ids.join(', ')}
            </p>
            {/* <bdi> isolates the text so Arabic (right-to-left) displays correctly
                without moving the "Q:" / "A:" labels or the quotes. */}
            <p><strong>Q:</strong> <bdi>{item.question}</bdi></p>
            <p><strong>A:</strong> <bdi>{item.answer}</bdi></p>
          </li>
        ))}
      </ul>
    </section>
  )
}
