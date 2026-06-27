const NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
const player = document.getElementById("player");
let ws;

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

async function load(vid) {
  document.getElementById("tl").textContent = "henter + analyserer…";
  document.getElementById("results").innerHTML = "";
  const r = await fetch("/api/load", {method:"POST", headers:{"Content-Type":"application/json"},
                                       body: JSON.stringify({videoId: vid})});
  const d = await r.json();
  if (d.status !== "ready") {
    document.getElementById("tl").textContent = d.error || "fejl";
    return;
  }
  document.getElementById("tl").textContent = `${d.segments.length} segment(er)`;
  player.src = `/media/${vid}`;   // server vores lokale fil — ingen embed-spaerre
  player.play().catch(() => {});  // autoplay kan kraeve klik; controls er der
}

// position-stream 4x/sek
setInterval(() => {
  if (!player.paused && ws && ws.readyState === 1) {
    ws.send(JSON.stringify({type:"position", t: player.currentTime}));
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
