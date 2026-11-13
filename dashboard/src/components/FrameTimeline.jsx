// Stored frames from GET /frames, shown left (oldest) to right (newest).
import { frameImageUrl } from '../api.js'
import { USE_MOCK } from '../config.js'

const time = (iso) => new Date(iso).toLocaleTimeString()

export default function FrameTimeline({ frames }) {
  return (
    <section className="panel timeline-panel" aria-label="Frame timeline">
      <h2>Frame timeline</h2>
      {frames.length === 0 && <p>No frames stored.</p>}
      <ol className="timeline">
        {frames.map((frame) => (
          <li key={frame.id} className="frame-card">
            {/* Mock data has no real images, so show a placeholder box instead. */}
            {USE_MOCK ? (
              <div className="frame-placeholder">Frame #{frame.id}</div>
            ) : (
              <img src={frameImageUrl(frame.id)} alt={frame.caption || `Frame ${frame.id}`} />
            )}
            <p className="meta">
              #{frame.id} · {time(frame.captured_at)}
              {frame.enhanced && ' · enhanced'}
            </p>
            <p>{frame.caption}</p>
            {/* <bdi> keeps Arabic OCR text right-to-left without moving the label. */}
            {frame.ocr_text && <p><strong>Text:</strong> <bdi>{frame.ocr_text}</bdi></p>}
            {frame.objects.length > 0 && (
              <p><strong>Objects:</strong> {frame.objects.map((o) => o.label).join(', ')}</p>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
