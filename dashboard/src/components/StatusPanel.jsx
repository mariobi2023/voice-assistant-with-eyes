// System status.
// - Backend:      can the dashboard reach the FastAPI server right now?
// - Stream:       the REAL state of the dashboard's WHEP connection (from LiveVideo).
// - Backend reads stream / fps / frames / model: from GET /status.

// Turn the detailed LiveVideo text into a short label.
function streamLabel(videoState) {
  if (videoState === 'Live') return 'Live'
  if (videoState.startsWith('Connecting')) return 'Connecting…'
  return 'Retrying'
}

export default function StatusPanel({ status, videoState, backendOk }) {
  return (
    <section className="panel" aria-label="Status">
      <h2>Status</h2>
      <dl className="status-list">
        <dt>Backend</dt>
        <dd className={backendOk ? 'ok' : 'warn'}>{backendOk ? 'Connected' : 'Not reachable'}</dd>
        <dt>Stream</dt>
        <dd className={videoState === 'Live' ? 'ok' : 'warn'}>{streamLabel(videoState)}</dd>
        {status && (
          <>
            <dt>Backend reads stream</dt>
            <dd className={status.stream_connected ? 'ok' : 'warn'}>
              {status.stream_connected ? 'Yes' : 'No'}
            </dd>
            <dt>Frames per second</dt>
            <dd>{status.fps}</dd>
            <dt>Frames stored</dt>
            <dd>{status.frames_stored}</dd>
            <dt>Model</dt>
            <dd>{status.model}</dd>
          </>
        )}
      </dl>
      {/* Values from the last successful refresh stay visible while the backend is down. */}
      {!status && <p>{backendOk ? 'Loading…' : 'No data from the backend yet.'}</p>}
    </section>
  )
}
