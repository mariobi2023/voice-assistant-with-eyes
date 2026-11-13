// System status.
// - Stream: the REAL state of the dashboard's WHEP connection (from LiveVideo).
// - The other rows come from GET /status (mock data for now).

// Turn the detailed LiveVideo text into a short label.
function streamLabel(videoState) {
  if (videoState === 'Live') return 'Live'
  if (videoState.startsWith('Connecting')) return 'Connecting…'
  return 'Retrying'
}

export default function StatusPanel({ status, videoState }) {
  return (
    <section className="panel" aria-label="Status">
      <h2>Status</h2>
      <dl className="status-list">
        <dt>Stream</dt>
        <dd className={videoState === 'Live' ? 'ok' : 'warn'}>{streamLabel(videoState)}</dd>
        {status && (
          <>
            <dt>Frames per second</dt>
            <dd>{status.fps}</dd>
            <dt>Frames stored</dt>
            <dd>{status.frames_stored}</dd>
            <dt>Model</dt>
            <dd>{status.model}</dd>
          </>
        )}
      </dl>
      {!status && <p>Loading…</p>}
    </section>
  )
}
