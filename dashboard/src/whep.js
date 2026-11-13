// Minimal WHEP client: asks MediaMTX for the live stream over WebRTC.
// 1) Create a peer connection that only RECEIVES video/audio.
// 2) Make an SDP "offer" and POST it to the WHEP URL.
// 3) MediaMTX replies with an SDP "answer" → the video starts flowing.

export async function startWhep(url, videoElement) {
  const pc = new RTCPeerConnection()

  // We only want to receive, not send.
  pc.addTransceiver('video', { direction: 'recvonly' })
  pc.addTransceiver('audio', { direction: 'recvonly' })

  // When the tracks arrive, show them in the <video> element.
  pc.ontrack = (event) => {
    videoElement.srcObject = event.streams[0]
  }

  // Create the offer and wait until our network addresses (ICE candidates) are in it.
  await pc.setLocalDescription(await pc.createOffer())
  await waitForIce(pc)

  // Send the offer to MediaMTX.
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/sdp' },
    body: pc.localDescription.sdp,
  })
  if (!response.ok) {
    pc.close()
    // 404 means nobody is publishing to "cam" yet.
    throw new Error(response.status === 404 ? 'No stream published yet' : `WHEP error ${response.status}`)
  }

  // Apply MediaMTX's answer → the connection starts.
  await pc.setRemoteDescription({ type: 'answer', sdp: await response.text() })
  return pc
}

// Wait for ICE gathering to finish (or give up after 2 seconds).
function waitForIce(pc) {
  return new Promise((resolve) => {
    if (pc.iceGatheringState === 'complete') return resolve()
    const timer = setTimeout(resolve, 2000)
    pc.onicegatheringstatechange = () => {
      if (pc.iceGatheringState === 'complete') {
        clearTimeout(timer)
        resolve()
      }
    }
  })
}
