# Backend package for "Voice Assistant With Eyes".

# Make Python trust the same HTTPS certificates as Windows (and Chrome).
# Without this, model downloads (YOLO-World, EasyOCR, CLIP, Gemini API...) can fail with
# "CERTIFICATE_VERIFY_FAILED" on PCs where an antivirus or proxy inspects HTTPS traffic.
import truststore

truststore.inject_into_ssl()
