"use client";

import { useEffect, useRef, useState } from "react";
import { AudioLines, Download, LoaderCircle, MessageCircle, Play, RefreshCw, Save, Sparkles, Volume2 } from "lucide-react";
import type { Organization } from "@/lib/contracts";

type Voice = { id: string; language: string };
type VoiceSetting = { voice_id: string; language: string; speed: number; agent_id: string | null };
type Turn = { role: "user" | "assistant"; content: string; audioUrl?: string };
const samples: Record<string, string> = { "en-us": "Hello! I’m your Volvox voice preview. What can I help you with today?", "en-gb": "Hello, it’s lovely to meet you. How may I help today?", es: "Hola, me alegra conocerte. ¿En qué puedo ayudarte?", "fr-fr": "Bonjour, ravi de vous rencontrer. Comment puis-je vous aider ?", hi: "नमस्ते, आपसे मिलकर खुशी हुई। मैं आपकी क्या मदद कर सकता हूँ?", it: "Ciao, è un piacere conoscerti. Come posso aiutarti?", ja: "こんにちは。今日はどのようなお手伝いをしましょうか。", "pt-br": "Olá! Que bom falar com você. Como posso ajudar hoje?", zh: "你好，很高兴认识你。今天有什么可以帮忙的吗？" };
const titles: Record<string, string> = { "en-us": "English · US", "en-gb": "English · UK", es: "Español", "fr-fr": "Français", hi: "हिन्दी", it: "Italiano", ja: "日本語", "pt-br": "Português · Brasil", zh: "中文" };

export function VoiceStudio({ organization, agents, initialTab = "studio" }: { organization: Organization; agents: { id: string; name: string }[]; initialTab?: "studio" | "chat" | "presets" }) {
  const tab = initialTab;
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState("af_sarah");
  const [language, setLanguage] = useState("en-us");
  const [speed, setSpeed] = useState(1);
  const [text, setText] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [chatText, setChatText] = useState("");
  const [autoSpeak, setAutoSpeak] = useState(false);
  const [conversationId, setConversationId] = useState(() => typeof crypto !== "undefined" ? crypto.randomUUID() : "studio-session");
  const [agentId, setAgentId] = useState("");
  const [presetAgentId, setPresetAgentId] = useState("");
  const [voiceSettings, setVoiceSettings] = useState<VoiceSetting[]>([]);
  const [duration, setDuration] = useState(0);
  const [saved, setSaved] = useState(false);
  const [previewUrl, setPreviewUrl] = useState("");
  const audioRef = useRef<HTMLAudioElement>(null);
  const audioUrls = useRef<string[]>([]);

  useEffect(() => { return () => { if (audioUrl) URL.revokeObjectURL(audioUrl); if (previewUrl) URL.revokeObjectURL(previewUrl); }; }, [audioUrl, previewUrl]);
  useEffect(() => () => { for (const url of audioUrls.current) URL.revokeObjectURL(url); }, []);
  const orgPath = `/api/organizations/${encodeURIComponent(organization.id)}`;
  useEffect(() => {
    let active = true;
    fetch(`${orgPath}/voices`, { cache: "no-store" }).then(async (response) => {
      if (!response.ok) throw new Error("Could not load your saved voice settings.");
      const items = await response.json() as VoiceSetting[];
      if (!active) return;
      setVoiceSettings(items);
      const setting = items.find((item) => item.agent_id === null);
      if (setting) { setVoice(setting.voice_id); setLanguage(setting.language); setSpeed(setting.speed); }
    }).catch((issue: unknown) => active && setError(issue instanceof Error ? issue.message : "Could not load voice settings."));
    return () => { active = false; };
  }, [orgPath]);

  useEffect(() => { fetch("/api/voices", { cache: "no-store" }).then((r) => r.json()).then((data: { voices?: Voice[]; error?: string }) => { if (!data.voices?.length) throw new Error(data.error ?? "Kokoro voices could not be loaded."); setVoices(data.voices); }).catch((issue: unknown) => setError(issue instanceof Error ? issue.message : "Could not load Kokoro voices.")); }, []);

  const synthesize = async (spoken: string, useVoice = voice, useLanguage = language, useSpeed = speed) => {
    const response = await fetch(`${orgPath}/studio`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: spoken, voice_id: useVoice, language: useLanguage, speed: useSpeed }) });
    if (!response.ok) { const body = await response.json().catch(() => ({})) as { detail?: string; error?: string }; throw new Error(body.detail ?? body.error ?? `Speech generation failed (${response.status}).`); }
    if (!response.headers.get("content-type")?.includes("audio/wav")) throw new Error("The speech service returned an unexpected audio format.");
    const url = URL.createObjectURL(await response.blob());
    audioUrls.current.push(url);
    return url;
  };
  const generate = async (spoken = text, target?: (url: string) => void) => {
    setBusy(true); setError(""); setDuration(0);
    try {
      const next = await synthesize(spoken);
      if (target) target(next); else { setAudioUrl((old) => { if (old) URL.revokeObjectURL(old); return next; }); }
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Speech generation failed."); }
    finally { setBusy(false); }
  };
  const speakResponse = async (index: number, spoken: string) => {
    setBusy(true); setError("");
    try {
      const setting = voiceSettings.find((item) => item.agent_id === agentId);
      const url = await synthesize(spoken, setting?.voice_id ?? voice, setting?.language ?? language, setting?.speed ?? speed);
      setTurns((old) => old.map((turn, row) => row === index ? { ...turn, audioUrl: url } : turn));
      window.setTimeout(() => {
        const player = document.querySelector<HTMLAudioElement>(`#chat-audio-${index}`);
        player?.play().catch(() => setError("Your browser blocked autoplay. Use the audio controls to start playback."));
      }, 120);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Speech generation failed."); }
    finally { setBusy(false); }
  };
  const sendChat = async (event: React.FormEvent) => {
    event.preventDefault(); const message = chatText.trim(); if (!message || busy) return;
    setChatText(""); setError(""); setTurns((old) => [...old, { role: "user", content: message }]); setBusy(true);
    try {
      const response = await fetch(`${orgPath}/chat`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message, conversation_id: conversationId, agent_id: agentId || null }) });
      const body = await response.json() as { response?: string; error?: string; detail?: string };
      if (!response.ok || !body.response) throw new Error(body.detail ?? body.error ?? "Ollama could not answer.");
      const index = turns.length + 1; setTurns((old) => [...old, { role: "assistant", content: body.response! }]);
      if (autoSpeak) {
        const setting = voiceSettings.find((item) => item.agent_id === agentId);
        const url = await synthesize(body.response, setting?.voice_id ?? voice, setting?.language ?? language, setting?.speed ?? speed);
        setTurns((old) => old.map((turn, i) => i === index ? { ...turn, audioUrl: url } : turn));
        window.setTimeout(() => { const player = document.querySelector<HTMLAudioElement>(`#chat-audio-${index}`); player?.play().catch(() => setError("Your browser blocked autoplay. Use the audio controls to start playback.")); }, 100);
      }
    } catch (issue) { setError(issue instanceof Error ? issue.message : "The chat request failed."); }
    finally { setBusy(false); }
  };
  const choosePresetAgent = (id: string) => {
    setPresetAgentId(id);
    const setting = voiceSettings.find((item) => item.agent_id === (id || null));
    if (setting) { setVoice(setting.voice_id); setLanguage(setting.language); setSpeed(setting.speed); }
  };
  const saveVoice = async () => {
    setError(""); setSaved(false);
    try {
      const response = await fetch(`${orgPath}/voices`, { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ voice_id: voice, language, speed, agent_id: presetAgentId || null }) });
      const body = await response.json() as { detail?: string; error?: string };
      if (!response.ok) throw new Error(body.detail ?? body.error ?? "Could not save your voice settings.");
      setVoiceSettings((items) => [...items.filter((item) => item.agent_id !== (presetAgentId || null)), { voice_id: voice, language, speed, agent_id: presetAgentId || null }]);
      setSaved(true);
    } catch (issue) { setError(issue instanceof Error ? issue.message : "Could not save your voice settings."); }
  };
  const voiceOptions = voices.filter((item) => item.language === language);
  const changeLanguage = (next: string) => { setLanguage(next); const nextVoice = voices.find((item) => item.language === next); if (nextVoice) setVoice(nextVoice.id); };
  const previewVoice = (id: string) => { const item = voices.find((candidate) => candidate.id === id); if (!item) return; setBusy(true); setError(""); void synthesize(samples[item.language] ?? samples["en-us"], id, item.language).then((url) => { setPreviewUrl((old) => { if (old) URL.revokeObjectURL(old); return url; }); if (audioRef.current) { audioRef.current.src = url; void audioRef.current.play().catch(() => undefined); } }).catch((issue: unknown) => setError(issue instanceof Error ? issue.message : "Voice preview failed.")).finally(() => setBusy(false)); };

  return <div className="voice-studio">
    {error && <div className="studio-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}>×</button></div>}
    {tab === "studio" && <div className="studio-grid" id="panel-studio" role="tabpanel" aria-labelledby="tab-studio"><section className="card studio-compose"><div className="studio-section-heading"><div><span className="eyebrow">TEXT TO SPEECH</span><h2>Give your words a voice</h2><p>Write or paste up to 5,000 characters to create your audio.</p></div><span className="studio-count">{text.length.toLocaleString()} / 5,000</span></div><label className="sr-only" htmlFor="speech-text">Text to speak</label><textarea id="speech-text" className="studio-textarea" maxLength={5000} placeholder="Once upon a time… or paste a message, script, or idea here." value={text} onChange={(event) => setText(event.target.value)} /><div className="studio-controls"><div className="studio-field"><label htmlFor="studio-language">Language</label><select id="studio-language" value={language} onChange={(event) => changeLanguage(event.target.value)}>{[...new Set(voices.map((item) => item.language))].sort().map((code) => <option key={code} value={code}>{titles[code] ?? code}</option>)}</select></div><div className="studio-field"><label htmlFor="studio-voice">Voice</label><select id="studio-voice" value={voice} onChange={(event) => setVoice(event.target.value)}>{voiceOptions.map((item) => <option key={item.id} value={item.id}>{item.id.replaceAll("_", " ")}</option>)}</select></div><div className="studio-field studio-speed"><label htmlFor="studio-speed">Speed <b>{speed.toFixed(1)}×</b></label><input id="studio-speed" type="range" min="0.5" max="2" step="0.1" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} /></div></div><button className="btn btn-primary studio-generate" disabled={busy || !text.trim() || !voices.length} onClick={() => void generate()} type="button">{busy ? <><LoaderCircle className="spin" size={17} />Making your audio…</> : <><Sparkles size={16} />Generate speech</>}</button></section>
      <aside className="card studio-result"><div className="studio-result-top"><span className="result-orb"><AudioLines size={25} /></span><span className="pill">YOUR AUDIO</span></div><h3>{audioUrl ? "Ready to listen" : "Your next favorite voice"}</h3><p>{audioUrl ? "Your speech is ready. Listen here or download the WAV." : "Your generated audio will appear here once it’s ready."}</p>{audioUrl ? <><audio ref={audioRef} className="studio-audio" controls src={audioUrl} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}><track kind="captions" /></audio><div className="studio-audio-actions"><span>{duration ? `${Math.floor(duration / 60)}:${String(Math.floor(duration % 60)).padStart(2, "0")}` : "WAV · 24 kHz"}</span><button className="btn" onClick={() => { if (audioRef.current) { audioRef.current.currentTime = 0; void audioRef.current.play(); } }} type="button"><RefreshCw size={13} /> Replay</button><a className="btn" href={audioUrl} download="volvox-speech.wav"><Download size={13} /> Download WAV</a></div></> : <div className="studio-empty-state">Generate speech and your WAV player will appear here.</div>}<div className="studio-quality"><Volume2 size={14} /><span>Natural-sounding · No cloud API · Locally generated</span></div></aside></div>}
    {tab === "chat" && <section className="card chat-panel" id="panel-chat" role="tabpanel" aria-labelledby="tab-chat"><div className="studio-section-heading"><div><span className="eyebrow">LOCAL AI · LLAMA 3.2</span><h2>Chat with Volvox</h2><p>Type to ask Ollama. Speak any answer with Kokoro.</p></div><div className="chat-options"><label htmlFor="chat-agent">Agent</label><select id="chat-agent" value={agentId} onChange={(event) => { setAgentId(event.target.value); setConversationId(crypto.randomUUID()); setTurns([]); }}><option value="">Volvox default</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select><label className="auto-speak"><input type="checkbox" checked={autoSpeak} onChange={(event) => setAutoSpeak(event.target.checked)} /> Auto-speak replies</label></div></div><div className="chat-transcript" aria-live="polite">{turns.length ? turns.map((turn, index) => <article className={`chat-bubble ${turn.role}`} key={`${index}-${turn.role}`}><span>{turn.role === "user" ? "You" : "Volvox"}</span><p>{turn.content}</p>{turn.role === "assistant" && <div className="chat-actions"><button className="btn" onClick={() => void speakResponse(index, turn.content)} disabled={busy} type="button"><Play size={13} />Speak response</button>{turn.audioUrl && <audio id={`chat-audio-${index}`} controls src={turn.audioUrl}><track kind="captions" /></audio>}</div>}</article>) : <div className="chat-empty"><span><MessageCircle size={22} /></span><b>Your conversation starts here</b><p>Ask a question and your local AI will answer in text.</p></div>}</div><form className="chat-form" onSubmit={(event) => void sendChat(event)}><label className="sr-only" htmlFor="chat-message">Your message</label><textarea id="chat-message" maxLength={4000} value={chatText} onChange={(event) => setChatText(event.target.value)} placeholder="Ask Volvox anything…" rows={2} /><button className="btn btn-primary" disabled={busy || !chatText.trim()} type="submit">{busy ? <LoaderCircle className="spin" size={15} /> : <MessageCircle size={15} />}Send</button></form></section>}
    {tab === "presets" && <section className="card presets-panel" id="panel-presets" role="tabpanel" aria-labelledby="tab-presets"><div className="studio-section-heading"><div><span className="eyebrow">KOKORO VOICE PACK</span><h2>Find your voice</h2><p>Every voice below comes from the voice pack installed on this machine.</p></div><span className="pill">{voices.length} available</span></div><div className="preset-grid">{voices.map((item) => <article className={`preset-card${item.id === voice ? " chosen" : ""}`} key={item.id}><div className="preset-avatar"><AudioLines size={17} /></div><div className="preset-copy"><b>{item.id.replaceAll("_", " ")}</b><small>{titles[item.language] ?? item.language}</small></div><button className="preset-play" aria-label={`Preview ${item.id.replaceAll("_", " ")}`} disabled={busy} onClick={() => { setLanguage(item.language); setVoice(item.id); void previewVoice(item.id); }} type="button"><Play size={14} /></button><button className="preset-select visible" aria-label={`Select ${item.id.replaceAll("_", " ")}`} onClick={() => { setLanguage(item.language); setVoice(item.id); }} type="button">{item.id === voice ? "Selected" : "Use voice"}</button></article>)}</div><div className="preset-save"><div className="studio-controls"><div className="studio-field"><label htmlFor="preset-agent">Default for agent</label><select id="preset-agent" value={presetAgentId} onChange={(event) => choosePresetAgent(event.target.value)}><option value="">Workspace default</option>{agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}</select></div><div className="studio-field studio-speed"><label htmlFor="preset-speed">Speaking speed <b>{speed.toFixed(1)}×</b></label><input id="preset-speed" type="range" min="0.5" max="2" step="0.1" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} /></div><button className="btn btn-primary" onClick={() => void saveVoice()} type="button"><Save size={14} />{saved ? "Saved" : "Save voice settings"}</button></div></div></section>}
    <audio ref={audioRef} hidden />
  </div>;
}
