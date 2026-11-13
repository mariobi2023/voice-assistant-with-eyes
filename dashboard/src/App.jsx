// Main page: loads the data and places the four panels.
import { useEffect, useState } from 'react'
import { getStatus, getFrames, getQa } from './api.js'
import { REFRESH_MS, USE_MOCK } from './config.js'
import LiveVideo from './components/LiveVideo.jsx'
import StatusPanel from './components/StatusPanel.jsx'
import QaHistory from './components/QaHistory.jsx'
import FrameTimeline from './components/FrameTimeline.jsx'

export default function App() {
  const [status, setStatus] = useState(null)
  const [frames, setFrames] = useState([])
  const [qa, setQa] = useState([])
  const [error, setError] = useState('')
  // Real state of the WHEP video connection (set by LiveVideo, shown by StatusPanel).
  const [videoState, setVideoState] = useState('Connecting…')

  // Load all data now, then again every REFRESH_MS.
  useEffect(() => {
    async function load() {
      try {
        const [s, f, q] = await Promise.all([getStatus(), getFrames(), getQa()])
        setStatus(s)
        setFrames(f)
        setQa(q)
        setError('')
      } catch (err) {
        setError(err.message)
      }
    }
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => clearInterval(timer) // stop refreshing when the page closes
  }, [])

  return (
    <div className="page">
      <header className="header">
        <h1>Voice Assistant With Eyes</h1>
        {USE_MOCK && <span className="badge">MOCK DATA</span>}
      </header>

      {error && <p className="error" role="alert">Backend error: {error}</p>}

      <main className="grid">
        <LiveVideo state={videoState} onStateChange={setVideoState} />
        <QaHistory items={qa} />
        <StatusPanel status={status} videoState={videoState} />
        <FrameTimeline frames={frames} />
      </main>
    </div>
  )
}
