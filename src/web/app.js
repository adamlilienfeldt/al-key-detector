const NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
const player = document.getElementById("player");
let ws, segments = [];

function connectWS() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onclose = () => setTimeout(connectWS, 1000);
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data);
    if (d.type === "state") {
      document.getElementById("key").textContent = d.pc == null ? "—" : NOTES[d.pc];
      document.getElementById("rt").textContent = d.retune ? "PÅ" : "FRA";
    }
  };
}
connectWS();

function parseVideoId(s) {
  const m = s.match(/(?:v=|youtu\.be\/|\/watch\?.*v=)([\w-]{11})/);
  return m ? m[1] : null;
}

async function search() {
  const q = document.getElementById("q").value.trim();
  const vid = parseVideoId(q);
  if (vid) { load(vid); return; }
  const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  const d = await r.json();
  const box = document.getElementById("results");
  box.innerHTML = "";
  if (d.error) { box.textContent = d.error; return; }
  for (const it of d.items) {
    const el = document.createElement("div");
    el.className = "result";
    el.innerHTML = `<img src="${it.thumbnail}"/><span>${it.title}</span><small>${it.channel}</small>`;
    el.onclick = () => load(it.videoId);
    box.appendChild(el);
  }
}

function clearStage() {
  player.pause();
  player.removeAttribute("src");
  player.load();              // toem den gamle video
  player.classList.add("hidden");
  segments = [];
  document.getElementById("timeline").innerHTML = "";
  document.getElementById("loading").classList.remove("hidden");
}

async function load(vid) {
  clearStage();
  document.getElementById("tl").textContent = "henter + analyserer…";
  document.getElementById("results").innerHTML = "";
  const r = await fetch("/api/load", {method:"POST", headers:{"Content-Type":"application/json"},
                                       body: JSON.stringify({videoId: vid})});
  const d = await r.json();
  document.getElementById("loading").classList.add("hidden");
  if (d.status !== "ready") {
    document.getElementById("tl").textContent = d.error || "fejl";
    return;
  }
  segments = d.segments;
  const changes = new Set(segments.map(s => s.relative_major_pc)).size;
  document.getElementById("tl").textContent =
    `${segments.length} segment(er), ${changes} toneart(er)`;
  renderTimeline();
  player.src = `/media/${vid}`;
  player.classList.remove("hidden");
  player.play().catch(() => {});
}

function renderTimeline() {
  const box = document.getElementById("timeline");
  box.innerHTML = "";
  if (!segments.length) return;
  const total = segments[segments.length - 1].end || 1;
  segments.forEach((s, i) => {
    const div = document.createElement("div");
    div.className = "seg";
    div.dataset.i = i;
    div.style.flexGrow = Math.max(0.01, (s.end - s.start) / total);
    const note = s.relative_major_pc == null ? "?" : NOTES[s.relative_major_pc];
    div.innerHTML = `<b>${note}</b><small>${fmt(s.start)}</small>`;
    box.appendChild(div);
  });
}

function fmt(sec) {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function highlight(t) {
  const segs = document.querySelectorAll("#timeline .seg");
  segments.forEach((s, i) => {
    if (segs[i]) segs[i].classList.toggle("active", t >= s.start && t < s.end);
  });
}

// position-stream + tidslinje-highlight 4x/sek
setInterval(() => {
  if (!player.paused && player.src) {
    const t = player.currentTime;
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({type:"position", t}));
    highlight(t);
  }
}, 250);

// manuelle knapper
const man = document.getElementById("manual");
NOTES.forEach((n, pc) => {
  const b = document.createElement("button");
  b.textContent = n;
  b.onclick = () => ws.send(JSON.stringify({type:"manual", pc}));
  man.appendChild(b);
});
document.getElementById("auto").onclick = () => ws.send(JSON.stringify({type:"auto"}));
document.getElementById("go").onclick = search;
document.getElementById("q").addEventListener("keydown", e => { if (e.key === "Enter") search(); });
