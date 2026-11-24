// Stored frames from GET /frames, shown left (oldest) to right (newest).
// Images come from GET /frames/{id}/image. Faces in them are already blurred by the backend.
import { useEffect, useRef, useState } from 'react'
import { frameImageUrl } from '../api.js'
import { USE_MOCK } from '../config.js'

const time = (iso) => new Date(iso).toLocaleTimeString()

// One frame image. If it can't be loaded (e.g. retention just deleted it: HTTP 404),
// show a grey box with the reason instead of a broken-image icon.
function FrameImage({ frame }) {
  const [failed, setFailed] = useState(false)
  if (USE_MOCK || failed) {
    return (
      <div className="frame-placeholder">
        {USE_MOCK ? `Frame #${frame.id}` : 'Image no longer available'}
      </div>
    )
  }
  return (
    <img
      src={frameImageUrl(frame.id)}
      alt={frame.caption || `Frame ${frame.id}`}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

export default function FrameTimeline({ frames }) {
  const listRef = useRef(null)
  const newestId = frames.length ? frames[frames.length - 1].id : null

  // When a new frame arrives, scroll the timeline to the right end (the newest frame).
  useEffect(() => {
    const list = listRef.current
    if (list) list.scrollLeft = list.scrollWidth
  }, [newestId])

  return (
    <section className="panel timeline-panel" aria-label="Frame timeline">
      <h2>Frame timeline</h2>
      {frames.length === 0 && <p>No frames stored.</p>}
      <ol className="timeline" ref={listRef}>
        {frames.map((frame) => (
          <li key={frame.id} className="frame-card">
            <FrameImage frame={frame} />
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
