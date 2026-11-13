// Live camera view from MediaMTX (WHEP). Retries every 3 s until a stream exists.
// The connection state lives in App so the Status panel can show it too:
//   state         = current text, e.g. "Live" or "Stream lost — retrying…"
//   onStateChange = function to update it
import { useEffect, useRef } from 'react'
import { startWhep } from '../whep.js'
import { WHEP_URL } from '../config.js'

export default function LiveVideo({ state, onStateChange: setState }) {
  const videoRef = useRef(null)

  useEffect(() => {
    let pc = null
    let retryTimer = null
    let stopped = false

    async function connect() {
      try {
        pc = await startWhep(WHEP_URL, videoRef.current)
        if (stopped) return pc.close()
        setState('Live')
        // If the connection drops later (e.g. the publisher left), try again.
        pc.onconnectionstatechange = () => {
          if (['failed', 'disconnected', 'closed'].includes(pc.connectionState)) retry('Stream lost')
        }
      } catch (err) {
        retry(err.message)
      }
    }

    function retry(message) {
      if (stopped) return
      setState(`${message} — retrying…`)
      if (pc) pc.close()
      pc = null
      clearTimeout(retryTimer)
      retryTimer = setTimeout(connect, 3000)
    }

    connect()

    // Cleanup when the component is removed.
    return () => {
      stopped = true
      clearTimeout(retryTimer)
      if (pc) pc.close()
    }
  }, [])

  return (
    <section className="panel video-panel" aria-label="Live video">
      <h2>Live camera</h2>
      <video ref={videoRef} autoPlay muted playsInline />
      <p className={state === 'Live' ? 'ok' : 'warn'} role="status">{state}</p>
    </section>
  )
}
