"use client";

import { useEffect, useRef, useState } from "react";
import type { Agent, Organization } from "@/lib/contracts";

type State = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "error";
type Line = { role: "you" | "agent"; text: string };

const processorSource = `
class VolvoxCapture extends AudioWorkletProcessor {
  constructor() { super(); this.pending = new Int16Array(512); this.used = 0; }
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (samples) for (let index = 0; index < samples.length; index++) {
      this.pending[this.used++] = Math.max(-32768, Math.min(32767, Math.round(samples[index] * 32767)));
      if (this.used === 512) {
        this.port.postMessage(this.pending.buffer, [this.pending.buffer]);
        this.pending = new Int16Array(512); this.used = 0;
      }
    }
    return true;
  }
}
registerProcessor("volvox-capture", VolvoxCapture);
`;

export function VoiceConversation({ organization, agents }: { organization: Organization; agents: Agent[] }) {
  const [agentId, setAgentId] = useState("");
  const [automatic, setAutomatic] = useState(false);
  const [muted, setMuted] = useState(false);
  const [recording, setRecording] = useState(false);
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [hasAudio, setHasAudio] = useState(false);
  const [answerUrl, setAnswerUrl] = useState("");
  const [connected, setConnected] = useState(false);
  const socket = useRef<WebSocket | null>(null);
  const media = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const wavUrl = useRef("");
  const recordingRef = useRef(false);
  const automaticRef = useRef(false);
  const mutedRef = useRef(false);
  const sessionRef = useRef(false);

  const stop = () => {
    sessionRef.current = false;
    recordingRef.current = false;
    setRecording(false);
    const active = socket.current;
    if (active?.readyState === WebSocket.OPEN) active.send(JSON.stringify({ type: "stop" }));
    active?.close(); socket.current = null;
    media.current?.getTracks().forEach((track) => track.stop()); media.current = null;
    void context.current?.close(); context.current = null;
    player.current?.pause(); player.current = null;
    if (wavUrl.current) URL.revokeObjectURL(wavUrl.current);
    wavUrl.current = "";
    setHasAudio(false);
    setAnswerUrl("");
    setConnected(false); setState("idle");
  };

  useEffect(() => () => stop(), []);
  useEffect(() => {
    if (answerUrl && player.current) {
      void player.current.play().catch(() => setError("Browser autoplay was blocked. Use the audio controls to play the answer."));
    }
  }, [answerUrl]);

  const start = async () => {
    if (!agentId || sessionRef.current) return;
    setError(""); setLines([]); setState("connecting");
    try {
      if (location.origin !== "http://127.0.0.1:3000") throw new Error("Open the dashboard at http://127.0.0.1:3000 for local microphone access.");
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 }, video: false });
      media.current = stream;
      const audioContext = new AudioContext({ sampleRate: 16000 });
      context.current = audioContext;
      if (audioContext.sampleRate !== 16000) throw new Error("This browser cannot capture 16 kHz microphone audio.");
      const moduleUrl = URL.createObjectURL(new Blob([processorSource], { type: "text/javascript" }));
      try { await audioContext.audioWorklet.addModule(moduleUrl); } finally { URL.revokeObjectURL(moduleUrl); }
      const node = new AudioWorkletNode(audioContext, "volvox-capture");
      const silent = audioContext.createGain(); silent.gain.value = 0;
      audioContext.createMediaStreamSource(stream).connect(node); node.connect(silent); silent.connect(audioContext.destination);
      node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        const active = socket.current;
        if (active?.readyState === WebSocket.OPEN && !mutedRef.current && (automaticRef.current || recordingRef.current) && active.bufferedAmount < 128000) active.send(event.data);
      };
      const response = await fetch(`/api/organizations/${encodeURIComponent(organization.id)}/voice-session`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ agent_id: agentId }) });
      const body = await response.json() as { url?: string; ticket?: string; error?: string; detail?: string };
      if (!response.ok || !body.url || !body.ticket) throw new Error(body.error ?? body.detail ?? "Could not start a voice session.");
      const ws = new WebSocket(body.url, ["volvox", `ticket.${body.ticket}`]);
      ws.binaryType = "arraybuffer";
      socket.current = ws;
      automaticRef.current = automatic;
      await new Promise<void>((resolve, reject) => {
        const timer = window.setTimeout(() => reject(new Error("Voice connection timed out.")), 8000);
        ws.onopen = () => { window.clearTimeout(timer); ws.send(JSON.stringify({ type: "mode", value: automatic ? "auto" : "manual" })); resolve(); };
        ws.onerror = () => { window.clearTimeout(timer); reject(new Error("Voice connection failed. Check the FastAPI server.")); };
      });
      sessionRef.current = true; setConnected(true); setState("listening");
      ws.onmessage = (event: MessageEvent<string | ArrayBuffer>) => {
        if (event.data instanceof ArrayBuffer) {
          player.current?.pause();
          if (wavUrl.current) URL.revokeObjectURL(wavUrl.current);
          wavUrl.current = URL.createObjectURL(new Blob([event.data], { type: "audio/wav" }));
          setHasAudio(true);
          setAnswerUrl(wavUrl.current);
          setState("speaking");
          return;
        }
        try {
          const message = JSON.parse(event.data) as { type: string; state?: State; text?: string; message?: string };
          if (message.type === "state" && message.state && message.state !== "listening") setState(message.state);
          if (message.type === "transcript" && message.text) setLines((items) => [...items, { role: "you", text: message.text! }]);
          if (message.type === "response" && message.text) setLines((items) => [...items, { role: "agent", text: message.text! }]);
          if (message.type === "interrupted") { player.current?.pause(); setState("listening"); }
          if (message.type === "error") { setError(message.message ?? "This voice turn failed."); setState("error"); }
        } catch { setError("The voice service returned an invalid message."); }
      };
      ws.onclose = () => { if (sessionRef.current) { setError("The voice connection closed. Start a new conversation to reconnect."); stop(); setState("error"); } };
    } catch (issue) {
      const message = issue instanceof DOMException && issue.name === "NotAllowedError" ? "Microphone permission was denied. Allow access in your browser and try again." : issue instanceof Error ? issue.message : "The voice session could not start.";
      stop(); setError(message); setState("error");
    }
  };

  const toggleRecording = () => {
    if (!connected || automatic) return;
    if (recordingRef.current) {
      recordingRef.current = false; setRecording(false);
      socket.current?.send(JSON.stringify({ type: "turn_end" })); setState("thinking");
    } else {
      player.current?.pause();
      socket.current?.send(JSON.stringify({ type: "interrupt" }));
      recordingRef.current = true; setRecording(true); setState("listening");
    }
  };

  return <div className="conversation-layout">
    <section className="card section-card conversation-controls">
      <h2>Talk to a saved agent</h2>
      <p>Your microphone audio stays in memory during this session. Volvox uses local Whisper, Ollama, and Kokoro.</p>
      <label className="studio-field"><span>Agent</span><select value={agentId} disabled={connected} onChange={(event) => setAgentId(event.target.value)}><option value="">Choose an agent</option>{agents.filter((agent) => agent.enabled).map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></label>
      {!agents.some((agent) => agent.enabled) && <p>Create an agent on the AI Agents page to begin.</p>}
      <label className="conversation-check"><input type="checkbox" checked={automatic} disabled={connected} onChange={(event) => { setAutomatic(event.target.checked); automaticRef.current = event.target.checked; }} /> Automatic turn detection (Silero VAD)</label>
      <div className="conversation-actions"><button className="btn btn-primary" disabled={connected || state === "connecting" || !agentId} onClick={() => void start()} type="button">Start Conversation</button><button className="btn" disabled={!connected} onClick={stop} type="button">Stop Conversation</button></div>
      {connected && <div className="conversation-actions"><button className="btn" disabled={automatic || muted} onClick={toggleRecording} type="button">{recording ? "Finish turn" : "Record turn"}</button><button className="btn" onClick={() => { mutedRef.current = !mutedRef.current; setMuted(mutedRef.current); }} type="button">{muted ? "Unmute microphone" : "Mute microphone"}</button><button className="btn" disabled={!hasAudio} onClick={() => void player.current?.play().catch(() => setError("Audio playback failed."))} type="button">Play answer</button></div>}
      <p className="conversation-state" role="status">{connected ? "Connected · " : "Disconnected · "}{state}</p>
      {answerUrl && <audio ref={player} className="conversation-audio" controls src={answerUrl} onEnded={() => setState("listening")}><track kind="captions" /></audio>}
      {!automatic && connected && <p>Click Record turn, speak, then click Finish turn. Repeat for another turn.</p>}
      {error && <div className="studio-error" role="alert">{error}</div>}
    </section>
    <section className="card section-card conversation-transcript"><h2>Conversation</h2>{lines.length ? <div aria-live="polite">{lines.map((line, index) => <article key={index} className={`conversation-line ${line.role}`}><b>{line.role === "you" ? "You" : "Agent"}</b><p>{line.text}</p></article>)}</div> : <p>Your transcript and responses will appear here after you speak.</p>}</section>
  </div>;
}
