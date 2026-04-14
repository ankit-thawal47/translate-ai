import { useEffect, useRef, useState } from "react";

type UIState =
  | "idle"
  | "listening"
  | "processing"
  | "speaking"
  | "interrupted"
  | "completed"
  | "error";

const WS_URL = "ws://localhost:8000/ws";
const MAX_DURATION_SECONDS = 240; // 4 minutes — must match backend

export function App() {
  const [status, setStatus] = useState<UIState>("idle");
  const [error, setError] = useState<string>("");
  const [sessionId, setSessionId] = useState<string>("");
  const [hasSessionAudio, setHasSessionAudio] = useState(false);
  const [isReplaying, setIsReplaying] = useState(false);
  const [dominantTone, setDominantTone] = useState<string | null>(null);
  const toneCountsRef = useRef<Record<string, number>>({});
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const sequenceRef = useRef(0);
  const isStoppingRef = useRef(false);
  const isPlayingRef = useRef(false);
  const sessionAudioRef = useRef<Blob[]>([]);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hardStopRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      mediaRecorderRef.current?.stop();
      clearCountdown();
    };
  }, []);

  function startCountdown() {
    setSecondsLeft(MAX_DURATION_SECONDS);
    countdownRef.current = setInterval(() => {
      setSecondsLeft((s) => {
        if (s === null || s <= 1) { clearCountdown(); return 0; }
        return s - 1;
      });
    }, 1000);
    // Hard stop at the limit
    hardStopRef.current = setTimeout(() => {
      stopSession();
    }, MAX_DURATION_SECONDS * 1000);
  }

  function clearCountdown() {
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
    if (hardStopRef.current) { clearTimeout(hardStopRef.current); hardStopRef.current = null; }
    setSecondsLeft(null);
  }

  function formatTime(s: number) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${String(sec).padStart(2, "0")}`;
  }

  function resolveDominantTone() {
    const counts = toneCountsRef.current;
    const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    if (top) setDominantTone(top[0]);
  }

  function playBlobs(blobs: Blob[], onDone?: () => void) {
    if (blobs.length === 0) { onDone?.(); return; }
    const [head, ...tail] = blobs;
    const url = URL.createObjectURL(head);
    const audio = new Audio(url);
    isPlayingRef.current = true;
    setStatus("speaking");
    audio.onended = () => {
      URL.revokeObjectURL(url);
      if (tail.length > 0) { playBlobs(tail, onDone); }
      else { isPlayingRef.current = false; onDone?.(); }
    };
    audio.onerror = () => { URL.revokeObjectURL(url); isPlayingRef.current = false; playBlobs(tail, onDone); };
    audio.play().catch(() => { URL.revokeObjectURL(url); isPlayingRef.current = false; playBlobs(tail, onDone); });
  }

  async function startSession() {
    setError("");
    setHasSessionAudio(false);
    setIsReplaying(false);
    setDominantTone(null);
    toneCountsRef.current = {};
    isStoppingRef.current = false;
    isPlayingRef.current = false;
    sessionAudioRef.current = [];
    const id = crypto.randomUUID();
    setSessionId(id);

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data as string) as Record<string, unknown>;
      if (payload.event_type === "tts.chunk") {
        const bytes = Uint8Array.from(atob(payload.audio_b64 as string), (c) => c.charCodeAt(0));
        sessionAudioRef.current.push(new Blob([bytes], { type: "audio/mpeg" }));
        setHasSessionAudio(true);
        const tone = payload.detected_tone as string | undefined;
        if (tone && tone !== "unknown") {
          toneCountsRef.current[tone] = (toneCountsRef.current[tone] ?? 0) + 1;
        }
      } else if (payload.event_type === "session.processing") {
        setStatus("processing");
      } else if (payload.event_type === "session.completed") {
        clearCountdown();
        resolveDominantTone();
        if (sessionAudioRef.current.length > 0) {
          playBlobs([...sessionAudioRef.current], () => setStatus("completed"));
        } else {
          setStatus("completed");
        }
      } else if (payload.event_type === "session.limit_reached") {
        clearCountdown();
        resolveDominantTone();
        setError("4-minute session limit reached. Playing what was translated.");
        if (sessionAudioRef.current.length > 0) {
          playBlobs([...sessionAudioRef.current], () => setStatus("completed"));
        } else {
          setStatus("completed");
        }
      } else if (payload.event_type === "error") {
        clearCountdown();
        setStatus("error");
        setError((payload.code as string) ?? "Unknown error");
      }
    };

    ws.onopen = async () => {
      ws.send(JSON.stringify({ event_type: "session.start", session_id: id, sequence_id: nextSequence(), timestamp: new Date().toISOString() }));
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (evt) => {
        if (!evt.data.size || ws.readyState !== WebSocket.OPEN) return;
        const reader = new FileReader();
        reader.onloadend = () => {
          if (ws.readyState !== WebSocket.OPEN) return;
          ws.send(JSON.stringify({
            event_type: "audio.chunk", session_id: id,
            sequence_id: nextSequence(), timestamp: new Date().toISOString(),
            payload_b64: (reader.result as string).split(",")[1],
            mime_type: "audio/webm;codecs=opus", chunk_duration_ms: 1000,
          }));
        };
        reader.readAsDataURL(evt.data);
      };
      recorder.start(1000);
      setStatus("listening");
      startCountdown();
    };

    ws.onclose = () => {
      clearCountdown();
      setStatus((cur) => (["error", "speaking", "completed"].includes(cur) ? cur : "completed"));
    };
    ws.onerror = () => { clearCountdown(); setStatus("error"); setError("Connection failed"); };
  }

  function stopSession() {
    if (isStoppingRef.current) return;
    isStoppingRef.current = true;
    clearCountdown();
    setStatus("processing");
    mediaRecorderRef.current?.stop();
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN && sessionId) {
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ event_type: "session.stop", session_id: sessionId, sequence_id: nextSequence(), timestamp: new Date().toISOString() }));
        }
      }, 120);
    }
  }

  function interruptPlayback() {
    isPlayingRef.current = false;
    setStatus("interrupted");
  }

  function replaySession() {
    if (isReplaying || sessionAudioRef.current.length === 0) return;
    setIsReplaying(true);
    playBlobs([...sessionAudioRef.current], () => {
      setIsReplaying(false);
      setStatus((s) => (s === "speaking" ? "completed" : s));
    });
  }

  function nextSequence() { return ++sequenceRef.current; }

  // Stop is available the entire time the user is recording (listening OR processing a window)
  const isRecording = status === "listening" || status === "processing";
  const isActive = isRecording || status === "speaking";
  const isStopping = isStoppingRef.current;
  const isWarning = secondsLeft !== null && secondsLeft <= 30;

  return (
    <main className="shell">
      <div className="card">

        {/* Header */}
        <div className="card-top">
          <p className="eyebrow brandmark" aria-label="translate.ai">translate.ai</p>
          <h1>English <span className="arrow">→</span> Hindi</h1>
          <p className="sub">Speak in English. Hear Hindi back.</p>
        </div>

        {/* Status row */}
        <div className="status-row">
          <span className={`dot dot--${status}`} />
          <span className={`status-text status-text--${status}`}>
            {{
              idle: "Ready",
              listening: "Listening…",
              processing: isStopping ? "Finishing up…" : "Translating segment…",
              speaking: "Playing Hindi audio",
              interrupted: "Interrupted",
              completed: "Done",
              error: "Error",
            }[status]}
          </span>
          {status === "listening" && <span className="live-badge">LIVE</span>}
          {secondsLeft !== null && (
            <span className={`timer ${isWarning ? "timer--warn" : ""}`}>
              {formatTime(secondsLeft)}
            </span>
          )}
        </div>

        {/* Tone badge — shown after session with audio */}
        {dominantTone && !isActive && (
          <div className={`tone-badge tone-badge--${dominantTone}`}>
            <span className="tone-dot" />
            {dominantTone.charAt(0).toUpperCase() + dominantTone.slice(1)} tone detected
          </div>
        )}

        {/* Wave — visible while speaking */}
        {status === "speaking" && (
          <div className="wave">
            {[...Array(9)].map((_, i) => (
              <span key={i} style={{ animationDelay: `${i * 0.07}s` }} />
            ))}
          </div>
        )}

        {error && <p className="error-banner">{error}</p>}

        {/* Primary buttons */}
        <div className="btn-row">
          <button
            className="btn btn--primary"
            onClick={() => void startSession()}
            disabled={isActive || isStopping}
          >
            Start
          </button>
          <button
            className="btn btn--stop"
            onClick={stopSession}
            disabled={!isRecording || isStopping}
          >
            Stop
          </button>
          <button
            className="btn btn--ghost"
            onClick={interruptPlayback}
            disabled={status !== "speaking"}
          >
            Interrupt
          </button>
        </div>

        {/* Replay */}
        {hasSessionAudio && !isActive && (
          <button
            className="btn btn--replay"
            onClick={replaySession}
            disabled={isReplaying}
          >
            {isReplaying ? "Playing…" : "▶  Replay Hindi audio"}
          </button>
        )}
      </div>
    </main>
  );
}
