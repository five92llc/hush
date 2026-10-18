/* Hush web client — no build step, no dependencies. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v; // only used with static icon markup
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
};

const ICONS = {
  dir: '<path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  video: '<path d="M4 5h16v14H4zM6 7v2h2V7zm0 4v2h2v-2zm0 4v2h2v-2zm10-8v2h2V7zm0 4v2h2v-2zm0 4v2h2v-2zM10 7v10h4V7z"/>',
  audio: '<path d="M10 4v10.5A3.5 3.5 0 1 0 12 17V8h6V4z"/>',
  local: '<path d="M4 4h16v6H4zm0 10h16v6H4zm12-8v2h2V6zm0 10v2h2v-2z"/>',
  smb: '<path d="M4 4h16v6H4zm0 10h16v6H4zm12-8v2h2V6zm0 10v2h2v-2z"/>',
  dlna: '<path d="M12 18a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm-5-3 1.4 1.4a5 5 0 0 1 7.2 0L17 15a7 7 0 0 0-10 0zm-3-3 1.4 1.4a9 9 0 0 1 13.2 0L20 12a11 11 0 0 0-16 0z"/>',
  jellyfin: '<path d="M12 3 2 20h20zm0 6 4.5 8h-9z"/>',
  plex: '<path d="M7 3h5l6 9-6 9H7l6-9z"/>',
  http: '<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm6.9 6h-3a15 15 0 0 0-1.3-3.9A8 8 0 0 1 18.9 8zM12 4c.8 1.1 1.5 2.5 1.9 4h-3.8c.4-1.5 1.1-2.9 1.9-4zM4.3 14a8 8 0 0 1 0-4h3.4a16 16 0 0 0 0 4zm.8 2h3a15 15 0 0 0 1.3 3.9A8 8 0 0 1 5.1 16zm3-8h-3a8 8 0 0 1 4.3-3.9A15 15 0 0 0 8.1 8zM12 20c-.8-1.1-1.5-2.5-1.9-4h3.8c-.4 1.5-1.1 2.9-1.9 4zm2.3-6H9.7a14 14 0 0 1 0-4h4.6a14 14 0 0 1 0 4zm.3 5.9a15 15 0 0 0 1.3-3.9h3a8 8 0 0 1-4.3 3.9zm1.7-5.9a16 16 0 0 0 0-4h3.4a8 8 0 0 1 0 4z"/>',
  hush: '<path d="M3 9h4l5-4v14l-5-4H3z"/><path d="M15 9l6 6M21 9l-6 6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/>',
  trash: '<path d="M6 7h12l-1 13H7zM9 4h6l1 2H8z"/>',
};
const icon = (name, cls = "ico") => {
  const t = document.createElement("template");   // parsed by the HTML parser, so the SVG namespace is right
  t.innerHTML = `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.video}</svg>`;
  return t.content.firstChild;
};

const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const s = Math.floor(t % 60), m = Math.floor(t / 60) % 60, hr = Math.floor(t / 3600);
  return (hr ? `${hr}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(s).padStart(2, "0")}`;
};
const fmtPrecise = (t) => fmt(t) + "." + String(Math.floor((t % 1) * 10));
const fmtSize = (b) => b == null ? "" : b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : b > 1e6 ? Math.round(b / 1e6) + " MB" : Math.max(1, Math.round(b / 1e3)) + " KB";
const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const store = {
  get(k, d) { try { const v = localStorage.getItem("hush." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("hush." + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 3200);
}

class ApiError extends Error { constructor(status, msg) { super(msg); this.status = status; } }
async function api(path, opts = {}) {
  const init = { credentials: "same-origin", ...opts, headers: { ...(opts.headers || {}) } };
  if (opts.body && typeof opts.body !== "string") { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, init);
  if (r.status === 401 && !path.startsWith("/api/login")) { showLogin(); throw new ApiError(401, "Sign in to continue"); }
  const data = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new ApiError(r.status, (data && data.detail) || `Request failed (${r.status})`);
  return data;
}

/* ===================================================== state */
const S = {
  config: null, sources: [], source: null,
  dirNames: { "": null }, dirParent: {}, entries: [],
};

/* ===================================================== login */
function showLogin() {
  $("#app").hidden = true; $("#login").hidden = false; $("#password").focus();
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: { password: $("#password").value } });
    $("#password").value = "";
    start();
  } catch (err) { $("#login-error").textContent = err.message; }
});
$("#logout-btn").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showLogin(); });

$("#password-btn").addEventListener("click", () => {
  $("#password-form").reset(); $("#pw-error").textContent = "";
  $("#pw-current-row").hidden = !S.authRequired;
  $("#password-dialog").showModal();
});
$("#password-form").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "save") return;
  e.preventDefault();
  if ($("#pw-new").value !== $("#pw-again").value) { $("#pw-error").textContent = "The new passwords don't match"; return; }
  try {
    await api("/api/password", { method: "POST", body: { current: $("#pw-current").value, new: $("#pw-new").value } });
    S.authRequired = true; $("#logout-btn").hidden = false;
    $("#password-dialog").close();
    toast("Password changed");
  } catch (err) { $("#pw-error").textContent = err.message; }
});

/* ===================================================== library */
async function loadSources() {
  S.sources = await api("/api/sources");
  const ul = $("#source-list");
  ul.replaceChildren(...S.sources.map((s) => h("li", {},
    s.error
      ? h("div", { class: "err", title: s.error }, `${s.name}: ${s.error}`)
      : h("button", { type: "button", "aria-current": String(S.source === s.id), onclick: () => go(`#/b/${s.id}`) },
          icon(s.type, "kind"), h("span", {}, s.name),
          s.editable ? h("span", { class: "remove", role: "button", tabindex: "0", "aria-label": `Remove ${s.name}`,
            onclick: (e) => { e.stopPropagation(); removeSource(s); } }, "×") : null),
  )));
}

async function removeSource(s) {
  if (!confirm(`Remove "${s.name}" from Hush? Your files are not touched.`)) return;
  await api(`/api/sources/${s.id}`, { method: "DELETE" });
  if (S.source === s.id) go("#/");
  loadSources();
}

async function browse(sourceId, dirId = "") {
  S.source = sourceId;
  $$("#source-list li").forEach((li, i) => {
    const btn = li.querySelector("button");
    if (btn) btn.setAttribute("aria-current", String(S.sources[i]?.id === sourceId));
  });
  const src = S.sources.find((s) => s.id === sourceId) || { name: sourceId === "url" ? "Opened links" : sourceId };
  renderCrumbs(src, dirId);
  const list = $("#entries"), empty = $("#browser-empty");
  list.replaceChildren(h("li", { class: "entry" }, h("span"), h("span", { class: "meta" }, "Loading…")));
  empty.hidden = true;
  try {
    S.entries = await api(`/api/browse/${sourceId}?dir=${encodeURIComponent(dirId)}`);
  } catch (err) {
    list.replaceChildren();
    showEmpty("This folder couldn't be opened", err.message);
    return;
  }
  for (const e of S.entries) if (e.kind === "dir") { S.dirNames[e.id] = e.name; S.dirParent[e.id] = dirId; }
  S.currentDir = dirId;
  $("#scan-all-btn").hidden = sourceId === "url";
  $("#filter-input").value = "";
  renderEntries();
}

function renderCrumbs(src, dirId) {
  const trail = [];
  for (let d = dirId; d; d = S.dirParent[d]) { trail.unshift(d); if (trail.length > 30) break; }
  const ol = $("#crumbs");
  ol.replaceChildren(
    h("li", {}, h("button", { type: "button", onclick: () => go(`#/b/${src.id || S.source}`) }, src.name)),
    ...trail.map((d) => h("li", {}, h("button", { type: "button", onclick: () => go(`#/b/${S.source}/${d}`) }, S.dirNames[d] || "…"))),
  );
}

function showEmpty(title, body) {
  const empty = $("#browser-empty");
  empty.replaceChildren(h("h2", {}, title), h("p", {}, body));
  empty.hidden = false;
}

function renderEntries() {
  const q = $("#filter-input").value.trim().toLowerCase();
  const items = S.entries.filter((e) => !q || e.name.toLowerCase().includes(q));
  Queue.set(items.filter((e) => e.kind !== "dir").map((e) => ({ src: e.source_id || S.source, item: e.id, title: e.name })));
  const list = $("#entries");
  list.replaceChildren(...items.map((e) => {
    const isDir = e.kind === "dir";
    const target = isDir ? `#/b/${S.source}/${e.id}` : `#/p/${e.source_id || S.source}/${e.id}`;
    return h("li", { class: `entry ${e.kind}` },
      icon(isDir ? "dir" : e.kind),
      h("a", { class: "name", href: target, title: e.name }, e.name),
      h("span", { class: "meta" }, isDir ? "" : [e.meta?.year, fmtSize(e.size)].filter(Boolean).join("  ")),
      isDir ? h("span") : e.filtered
        ? h("span", { class: "badge", title: "Language filter is ready" }, icon("hush", ""), "Filter ready")
        : h("button", { class: "btn subtle scan-btn", type: "button", onclick: (ev) => scanFromList(ev, e) }, "Scan"),
    );
  }));
  if (!items.length) {
    S.source === "url"
      ? showEmpty("No links yet", "Paste a link to a video or song in the box on the left and press Play.")
      : showEmpty(q ? "Nothing matches" : "This folder is empty", q ? "Try a shorter search." : "Hush shows folders, videos and music here. Other files are hidden.");
  } else $("#browser-empty").hidden = true;
}
$("#filter-input").addEventListener("input", renderEntries);

$("#scan-all-btn").addEventListener("click", async (ev) => {
  const btn = ev.currentTarget;
  if (!confirm("Scan every title in this folder, and the folders inside it, that hasn't been scanned yet? "
               + "Scans run one after another in the background, so a big library takes a while.")) return;
  btn.disabled = true;
  try {
    const r = await api("/api/scan-folder", { method: "POST", body: { source_id: S.source, dir_id: S.currentDir || "" } });
    toast(r.queued ? `Queued ${plural(r.queued, "title")} to scan` : "Everything here is already scanned");
    Jobs.poll();
  } catch (err) { toast(err.message); }
  btn.disabled = false;
});

async function scanFromList(ev, e) {
  const btn = ev.currentTarget;
  btn.disabled = true; btn.textContent = "Queued";
  try {
    await api("/api/analyze", { method: "POST", body: { source_id: e.source_id || S.source, item_id: e.id, title: e.name } });
    toast(`Scanning ${e.name}`);
    Jobs.poll();
  } catch (err) { btn.disabled = false; btn.textContent = "Scan"; toast(err.message); }
}

$("#url-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const r = await api("/api/open-url", { method: "POST", body: { url: $("#url-input").value.trim() } });
    $("#url-input").value = "";
    go(r.kind === "dir" ? `#/b/${r.source_id}/${r.item_id}` : `#/p/${r.source_id}/${r.item_id}`);
  } catch (err) { toast(err.message); }
});

/* ===================================================== add source */
const SOURCE_FIELDS = {
  smb: [["server", "Server", "nas.local or 192.168.1.20"], ["share", "Share", "Movies"], ["path", "Folder inside the share (optional)", "Family/Films"],
        ["username", "User name", ""], ["password", "Password", "", "password"]],
  local: [["path", "Folder path on the server", "/media/movies"]],
  dlna: [["location", "Server description URL", "http://192.168.1.20:8200/rootDesc.xml"]],
  jellyfin: [["url", "Server address", "http://192.168.1.20:8096"], ["api_key", "API key", "Dashboard → API Keys", "password"],
             ["username", "User (optional)", "Leave blank for the first user"]],
  plex: [["url", "Server address", "http://192.168.1.20:32400"], ["token", "Plex token", "", "password"]],
  http: [["url", "Web folder or link", "http://192.168.1.20:8080/movies/"]],
  ftp: [["host", "Server", "192.168.1.20"], ["port", "Port (optional)", "21"], ["path", "Folder (optional)", "/movies"],
        ["username", "User name (blank for anonymous)", ""], ["password", "Password", "", "password"]],
  sftp: [["host", "Server", "192.168.1.20"], ["port", "Port (optional)", "22"], ["path", "Folder (optional)", "/home/me/movies"],
         ["username", "User name", ""], ["password", "Password", "", "password"]],
};
const SOURCE_HINTS = {
  smb: "Works with Windows shares, Synology, QNAP and TrueNAS. Nothing needs to be mounted.",
  local: "Any folder the Hush server can read, including NAS shares mounted with NFS or CIFS.",
  plex: "To find your token, open any item in Plex Web, choose Get Info → View XML, and copy the X-Plex-Token value from the address.",
  ftp: "Plain FTP. Files play and scan like any other.",
  sftp: "Any server you can log in to over SSH. Password login; blank password uses the server's SSH keys.",
  http: "End a folder address with / to browse it. Works with nginx, Apache and Caddy file listings.",
};

function renderSourceFields() {
  const type = $("#src-type").value;
  const box = $("#src-fields");
  box.replaceChildren(...SOURCE_FIELDS[type].map(([name, label, ph, kind]) =>
    h("label", {}, label, h("input", { name, type: kind || "text", placeholder: ph, autocomplete: kind === "password" ? "new-password" : "off",
      required: !/optional/i.test(label) && name !== "username" && name !== "password" }))));
  if (SOURCE_HINTS[type]) box.prepend(h("p", { class: "hint" }, SOURCE_HINTS[type]));
  if (["smb", "ftp", "sftp", "jellyfin", "plex"].includes(type)) {
    const found = h("div", { class: "found" });
    box.append(h("button", { class: "btn subtle", type: "button", onclick: async (e) => {
      const btn = e.currentTarget; btn.disabled = true; btn.textContent = "Scanning…";
      try {
        const r = await api("/api/network/scan");
        const rows = r.servers.flatMap((s) => s.services.map((v) => ({ s, v })));
        found.replaceChildren(...(rows.length ? rows.map(({ s, v }) => h("button", { class: "btn ghost", type: "button", onclick: () => pickServer(s, v) },
          `${s.name || s.host} · ${s.host} · ${v.label}`)) : [h("p", { class: "hint" }, "Nothing answered. Check the server is on and on the same network, or type its address.")]));
      } catch (err) { found.replaceChildren(h("p", { class: "error" }, err.message)); }
      btn.disabled = false; btn.textContent = "Find servers on my network";
    } }, "Find servers on my network"), found);
  }
  if (type === "dlna") {
    const found = h("div", { class: "found" });
    box.append(h("button", { class: "btn subtle", type: "button", onclick: async (e) => {
      e.currentTarget.textContent = "Looking…";
      try {
        const servers = await api("/api/dlna/discover");
        found.replaceChildren(...(servers.length ? servers.map((s) => h("button", { class: "btn ghost", type: "button", onclick: () => {
          $("#source-form [name=location]").value = s.location;
          const n = $("#source-form [name=name]"); if (!n.value) n.value = s.name;
        } }, s.name)) : [h("p", { class: "hint" }, "No servers answered. Check that the server is on and on the same network, or paste its address.")]));
      } catch (err) { found.replaceChildren(h("p", { class: "error" }, err.message)); }
      e.currentTarget.textContent = "Find servers on my network";
    } }, "Find servers on my network"), found);
  }
}
function pickServer(s, v) {
  const sel = $("#src-type");
  if (sel.value !== v.type) { sel.value = v.type; renderSourceFields(); }
  const set = (n, val) => { const el = $(`#source-form [name=${n}]`); if (el && !el.value) el.value = val; };
  set("name", s.name || s.host);
  if (v.type === "smb") set("server", s.host);
  else if (v.type === "ftp" || v.type === "sftp") set("host", s.host);
  else set("url", `http://${s.host}:${v.port}`);
}
$("#src-type").addEventListener("change", renderSourceFields);
$("#add-source-btn").addEventListener("click", () => {
  $("#source-form").reset(); $("#src-error").textContent = ""; renderSourceFields(); $("#source-dialog").showModal();
});
$("#source-form").addEventListener("submit", async (e) => {
  if (e.submitter?.value !== "save") return;
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  for (const k of Object.keys(data)) if (data[k] === "") delete data[k];
  if (data.type === "http") { data.urls = [{ name: data.name, url: data.url }]; delete data.url; }
  try {
    const src = await api("/api/sources", { method: "POST", body: data });
    $("#source-dialog").close();
    await loadSources();
    go(`#/b/${src.id}`);
  } catch (err) { $("#src-error").textContent = err.message; }
});

/* ===================================================== jobs */
const Jobs = {
  timer: null, list: [], paused: false,
  async act(path) {
    try { await api(path, { method: "POST" }); } catch (err) { toast(err.message); }
    this.poll();
  },
  async poll() {
    clearTimeout(this.timer);
    try { [this.list, { paused: this.paused }] = await Promise.all([api("/api/jobs"), api("/api/jobs/state")]); } catch { return; }
    const running = this.list.filter((j) => j.status === "running" || j.status === "queued");
    $("#jobs-dot").hidden = !running.length;
    $("#jobs-label").textContent = running.length ? (this.paused ? `Paused ${running.length}` : `Scanning ${running.length}`) : "Scans";
    if ($("#jobs-dialog").open) this.render();
    Player.onJobs(this.list);
    if (running.length || $("#jobs-dialog").open) this.timer = setTimeout(() => this.poll(), 2500);
  },
  render() {
    const ul = $("#jobs-list");
    const active = this.list.some((j) => j.status === "running" || j.status === "queued");
    const failed = this.list.some((j) => j.status === "error" || j.status === "cancelled");
    $("#jobs-tools").replaceChildren(...[
      h("button", { class: "btn subtle", type: "button", onclick: () => this.act(this.paused ? "/api/jobs/resume" : "/api/jobs/pause") },
        this.paused ? "Resume scans" : "Pause scans"),
      active && h("button", { class: "btn ghost", type: "button", onclick: () => confirm("Stop the running scan and clear the waiting ones?") && this.act("/api/jobs/stop-all") }, "Stop all"),
      failed && h("button", { class: "btn ghost", type: "button", onclick: () => this.act("/api/jobs/retry-failed") }, "Retry failed"),
    ].filter(Boolean));
    $("#jobs-note").textContent = this.paused
      ? "Paused. A scan that is already running will finish, then nothing new starts." : "";
    if (!this.list.length) { ul.replaceChildren(h("li", {}, h("span", { class: "stage" }, "Nothing has been scanned yet. Open a title and choose Scan to build its filter."))); return; }
    ul.replaceChildren(...this.list.map((j) => h("li", {},
      h("span", { class: "job-title" }, j.title || "Untitled"),
      h("span", { class: "job-action" },
        j.status === "queued" ? h("button", { class: "btn ghost", type: "button", title: "Move this title to the front of the queue", onclick: () => this.act(`/api/jobs/${j.id}/next`) }, "Scan next") : null,
        j.status === "running" || j.status === "queued"
          ? h("button", { class: "btn ghost", type: "button", onclick: async () => { await api(`/api/jobs/${j.id}/cancel`, { method: "POST" }); this.poll(); } }, "Cancel")
          : h("button", { class: "btn ghost", type: "button", onclick: () => this.act(`/api/jobs/${j.id}/restart`) }, "Restart")),
      h("span", { class: `stage ${j.status === "error" ? "error" : ""}` }, jobText(j)),
      j.status === "running" ? h("div", { class: "progress" }, h("i", { style: `width:${Math.round(j.progress * 100)}%` })) : null,
    )));
  },
};
function jobText(j) {
  if (j.status === "error") return `Couldn't finish: ${j.error || "unknown error"}`;
  if (j.status === "done") return `Done, ${j.stage}`;
  if (j.status === "cancelled") return "Cancelled";
  if (j.status === "queued") return "Waiting to start";
  return `${j.stage[0].toUpperCase()}${j.stage.slice(1)}, ${Math.round(j.progress * 100)}%`;
}
$("#jobs-btn").addEventListener("click", () => { $("#jobs-dialog").showModal(); Jobs.render(); Jobs.poll(); });
$$("[data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));

/* ===================================================== play queue: previous, next, shuffle, repeat */
const Queue = {
  list: [], pos: -1, history: [], played: new Set(), pending: false,
  shuffle: store.get("shuffle", false), repeat: store.get("repeat", "off"),   // off | all | one

  /** Remember the titles of the list the person is looking at: they become the play queue. */
  set(items) { this.list = items; },

  sync(src, item) {
    const i = this.list.findIndex((x) => x.src === src && x.item === item);
    if (i < 0) this.list = [{ src, item, title: "" }];
    this.pos = i < 0 ? 0 : i;
    if (this.pending) this.pending = false;              // moving inside the queue keeps its history
    else { this.history = []; this.played = new Set([this.pos]); }
    this.ui();
  },

  go(i) {
    const t = this.list[i];
    if (!t) return;
    this.pending = true; this.pos = i;
    location.hash = `#/p/${t.src}/${t.item}`;
  },

  /** Which index plays next, or null when the queue is over. */
  upNext() {
    const n = this.list.length;
    if (this.shuffle && n > 1) {
      let left = [...Array(n).keys()].filter((i) => !this.played.has(i));
      if (!left.length) {
        if (this.repeat !== "all") return null;
        this.played = new Set([this.pos]);
        left = [...Array(n).keys()].filter((i) => i !== this.pos);
      }
      return left[Math.floor(Math.random() * left.length)];
    }
    if (this.pos + 1 < n) return this.pos + 1;
    return this.repeat === "all" && n > 1 ? 0 : null;
  },

  next(auto = false) {
    if (auto && this.repeat === "one") { video.currentTime = 0; video.play().catch(() => {}); return; }
    const i = this.upNext();
    if (i == null) { if (!auto) toast("That was the last one"); $("#player").classList.remove("playing"); return; }
    this.history.push(this.pos); this.played.add(i);
    this.go(i);
  },

  prev() {
    if ((video.currentTime || 0) > 3 || (!this.history.length && this.pos <= 0 && this.repeat !== "all")) { Player.seek(0); return; }
    const i = this.history.length ? this.history.pop() : (this.pos > 0 ? this.pos - 1 : this.list.length - 1);
    this.go(i);
  },

  toggleShuffle() {
    this.shuffle = !this.shuffle; store.set("shuffle", this.shuffle);
    this.played = new Set([this.pos]); this.ui();
    toast(this.shuffle ? "Shuffle on" : "Shuffle off");
  },
  cycleRepeat() {
    this.repeat = { off: "all", all: "one", one: "off" }[this.repeat]; store.set("repeat", this.repeat); this.ui();
    toast({ off: "Repeat off", all: "Repeat all", one: "Repeat this one" }[this.repeat]);
  },

  ui() {
    const many = this.list.length > 1;
    $("#prev-btn").disabled = !many && this.repeat === "off";
    $("#next-btn").disabled = !many;
    $("#shuffle-btn").setAttribute("aria-pressed", String(this.shuffle));
    $("#shuffle-btn").disabled = !many;
    const label = { off: "Repeat: off (R)", all: "Repeat all (R)", one: "Repeat this one (R)" }[this.repeat];
    const r = $("#repeat-btn");
    r.dataset.repeat = this.repeat; r.setAttribute("aria-pressed", String(this.repeat !== "off"));
    r.setAttribute("aria-label", label); r.title = label;
  },
};
$("#prev-btn").addEventListener("click", () => Queue.prev());
$("#next-btn").addEventListener("click", () => Queue.next());
$("#shuffle-btn").addEventListener("click", () => Queue.toggleShuffle());
$("#repeat-btn").addEventListener("click", () => Queue.cycleRepeat());

/* ===================================================== catalog: posters, shows, details */
const initials = (t) => (t || "?").split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
const mins = (n) => (n ? `${Math.floor(n / 60) ? Math.floor(n / 60) + " h " : ""}${n % 60} min` : "");
const artBox = (url, label, cls = "art") => h("div", { class: cls }, url
  ? h("img", { src: url, alt: "", loading: "lazy" }) : h("div", { class: "noart" }, initials(label)));

const Catalog = {
  box: () => $("#catalog-view"),
  async open(view, id) {
    $$("#rail-links a").forEach((a) => a.setAttribute("aria-current", String(
      a.hash === `#/${view}` || (view === "show" && a.hash === "#/shows") || (view === "title" && a.hash === (this.cameFrom || "#/movies")))));
    this.box().replaceChildren(h("p", { class: "hint" }, "Loading…"));
    try {
      if (view === "movies") await this.grid("movies");
      else if (view === "shows") await this.grid("shows");
      else if (view === "show") await this.show(id);
      else await this.title(id);
    } catch (err) { this.box().replaceChildren(h("p", { class: "error" }, err.message)); }
  },

  empty(what) {
    return h("div", { class: "empty" }, h("h3", {}, `No ${what} yet`),
      h("p", {}, "Hush needs to look through your sources and add details and artwork. Run it once; after that it keeps itself up to date."),
      h("button", { class: "btn primary", type: "button", onclick: async () => {
        try { await api("/api/tasks/metadata/run", { method: "POST" }); toast("Started. This can take a few minutes."); } catch (e) { toast(e.message); }
      } }, "Find my titles"),
      h("a", { class: "btn ghost", href: "#/tasks" }, "Open Tasks"));
  },

  async grid(kind) {
    const items = await api(`/api/library/${kind}`);
    const isShows = kind === "shows";
    const q = h("input", { class: "search", type: "search", placeholder: `Find in ${isShows ? "TV shows" : "movies"}`, "aria-label": "Find a title" });
    const list = h("div", { class: "grid" });
    const draw = () => {
      const f = q.value.trim().toLowerCase();
      const shown = items.filter((m) => !f || m.title.toLowerCase().includes(f));
      if (!isShows) Queue.set(shown.map((m) => ({ src: m.source_id, item: m.item_id, title: m.title })));
      list.replaceChildren(...shown.map((m) => h("a", { class: "card", href: isShows ? `#/show/${m.show_key}` : `#/title/${m.media_key}` },
        h("div", { class: "art" }, m.art_url ? h("img", { src: m.art_url, alt: "", loading: "lazy" }) : h("div", { class: "noart" }, m.title),
          (isShows ? m.scanned && m.scanned === m.episodes : m.scanned) ? h("span", { class: "badge", title: "Language filter is ready" }, icon("hush", "")) : null),
        h("span", { class: "name" }, m.title),
        h("span", { class: "sub" }, isShows ? `${plural(m.episodes, "episode")}${m.seasons > 1 ? ` · ${m.seasons} seasons` : ""}` : (m.year || "")))));
    };
    q.addEventListener("input", draw);
    this.box().replaceChildren(
      h("div", { class: "catalog-head" }, h("div", {}, h("h1", {}, isShows ? "TV shows" : "Movies"),
        h("p", { class: "hint" }, plural(items.length, isShows ? "show" : "movie"))), q),
      items.length ? list : this.empty(isShows ? "TV shows" : "movies"));
    if (items.length) draw();
    this.cameFrom = isShows ? "#/shows" : "#/movies";
    document.title = `${isShows ? "TV shows" : "Movies"} – Hush`;
  },

  async show(key) {
    const { show, episodes } = await api(`/api/library/shows/${key}`);
    const seasons = {};
    for (const e of episodes) (seasons[e.season ?? 0] ||= []).push(e);
    this.cameFrom = "#/shows";
    Queue.set(episodes.map((e) => ({ src: e.source_id, item: e.item_id, title: e.title || "" })));
    document.title = `${show.title} – Hush`;
    this.box().replaceChildren(
      h("a", { class: "backlink", href: "#/shows" }, "← TV shows"),
      h("div", { class: "detail" }, artBox(show.art_url, show.title),
        h("div", {}, h("h1", {}, show.title, show.year ? ` (${show.year})` : ""),
          h("div", { class: "facts" }, ...[show.genres?.join(", "), show.rating ? `★ ${show.rating.toFixed(1)}` : "", plural(episodes.length, "episode")].filter(Boolean).map((t) => h("span", {}, t))),
          show.overview ? h("p", { class: "overview" }, show.overview) : null,
          h("div", { class: "actions" }, h("button", { class: "btn subtle", type: "button", onclick: () => this.scanAll(episodes) }, "Scan all episodes")))),
      ...Object.entries(seasons).map(([n, eps]) => h("section", { class: "season" },
        h("h3", {}, n === "0" ? "Specials" : `Season ${n}`),
        h("ul", { class: "eps" }, ...eps.map((e) => h("li", { class: "ep" },
          h("a", { class: "thumb", href: `#/title/${e.media_key}` }, e.art_url ? h("img", { src: e.art_url, alt: "", loading: "lazy" }) : null),
          h("div", {}, h("div", { class: "ep-title" }, h("a", { href: `#/title/${e.media_key}` }, `E${e.episode}${e.title ? ` · ${e.title}` : ""}`),
            e.scanned ? h("span", { class: "badge", style: "margin-left:.5rem", title: "Language filter is ready" }, icon("hush", ""), "Filter ready") : null),
            e.overview ? h("div", { class: "ep-sub" }, e.overview) : null),
          h("a", { class: "btn subtle", href: `#/p/${e.source_id}/${e.item_id}` }, "Play")))))));
  },

  async scanAll(episodes) {
    let n = 0;
    for (const e of episodes) {
      if (e.scanned) continue;
      try { await api("/api/analyze", { method: "POST", body: { source_id: e.source_id, item_id: e.item_id, title: e.title || "" } }); n++; } catch { /* skip */ }
    }
    toast(n ? `Queued ${plural(n, "episode")}` : "Everything is already scanned"); Jobs.poll();
  },

  async title(key) {
    const m = await api(`/api/library/title/${key}`);
    const show = m.show_key ? (await api(`/api/library/shows/${m.show_key}`)).show : null;
    const caps = await api(`/api/captions/${m.source_id}/${m.item_id}`).catch(() => ({ tracks: [], transcript: false }));
    document.title = `${show ? show.title + " – " : ""}${m.title} – Hush`;
    const heading = show ? `${show.title} · S${String(m.season).padStart(2, "0")}E${String(m.episode).padStart(2, "0")}` : `${m.title}${m.year ? ` (${m.year})` : ""}`;
    const mask = h("input", { type: "checkbox" });
    const tlink = (fmt, label) => h("a", { class: "btn ghost", href: "#", onclick: (e) => { e.preventDefault(); location.href = `/api/transcript/${key}.${fmt}${mask.checked ? "?censor=1" : ""}`; } }, label);
    this.box().replaceChildren(
      h("a", { class: "backlink", href: show ? `#/show/${m.show_key}` : "#/movies" }, show ? `← ${show.title}` : "← Movies"),
      h("div", { class: "detail" }, artBox(m.art_url, m.title, m.kind === "episode" ? "art wide" : "art"),
        h("div", {}, h("h1", {}, heading), m.kind === "episode" && m.title ? h("p", { class: "facts" }, m.title) : null,
          h("div", { class: "facts" }, ...[m.kind === "movie" ? m.genres?.join(", ") : "", mins(m.runtime), m.rating ? `★ ${Number(m.rating).toFixed(1)}` : ""].filter(Boolean).map((t) => h("span", {}, t))),
          m.overview ? h("p", { class: "overview" }, m.overview) : h("p", { class: "hint" }, "No summary yet."),
          h("div", { class: "actions" },
            h("a", { class: "btn primary", href: `#/p/${m.source_id}/${m.item_id}` }, "Play"),
            m.scanned ? h("span", { class: "badge", title: "Language filter is ready" }, icon("hush", ""), "Filter ready")
              : h("button", { class: "btn subtle", type: "button", onclick: async (ev) => {
                ev.currentTarget.disabled = true;
                try { await api("/api/analyze", { method: "POST", body: { source_id: m.source_id, item_id: m.item_id, title: m.title } }); toast("Scanning"); Jobs.poll(); } catch (e) { toast(e.message); }
              } }, "Scan this title"),
            h("button", { class: "btn ghost", type: "button", onclick: () => this.fixMatch(m, show) }, "Fix match")),
          h("h3", {}, "Transcript"),
          caps.transcript
            ? h("div", { class: "links" }, tlink("txt", "Text"), tlink("srt", "SRT"), tlink("vtt", "WebVTT"),
                h("label", { class: "inline" }, mask, "Mask language"))
            : h("p", { class: "hint" }, "Scan this title and the transcript is built from the dialogue."),
          h("h3", {}, "Captions and subtitles"),
          caps.tracks.length
            ? h("ul", { class: "links", style: "list-style:none;padding:0;margin:0" }, ...caps.tracks.map((t) => h("li", {},
                `${t.label} (${t.where}) `, h("a", { href: `/api/subtitle/${m.source_id}/${m.item_id}/${t.id}?format=srt&download=1` }, "SRT"), " · ",
                h("a", { href: `/api/subtitle/${m.source_id}/${m.item_id}/${t.id}?format=vtt&download=1` }, "WebVTT"))))
            : h("p", { class: "hint" }, "No subtitle or caption tracks in or next to this file."),
          m.provider ? h("p", { class: "hint", style: "margin-top:1.5rem" }, `Details from ${({ nfo: "the NFO file next to it", name: "the file name", tmdb: "TMDB", wikipedia: "Wikipedia", tvmaze: "TVmaze", manual: "your choice" })[m.provider] || m.provider}.`) : null)));
  },

  fixMatch(m, show) {
    const dlg = $("#match-dialog");
    $("#match-q").value = show ? show.title : m.title; $("#match-year").value = (show ? show.year : m.year) || "";
    const results = $("#match-results");
    const search = async () => {
      results.replaceChildren(h("li", {}, h("span"), h("span", { class: "sub" }, "Searching…"), h("span")));
      try {
        const q = new URLSearchParams({ key: m.media_key, q: $("#match-q").value });
        if ($("#match-year").value) q.set("year", $("#match-year").value);
        const found = await api(`/api/library/candidates?${q}`);
        results.replaceChildren(...(found.length ? found.map((c) => h("li", {},
          c.poster_url ? h("img", { src: c.poster_url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : h("span", { class: "nothumb" }),
          h("div", {}, h("div", {}, `${c.title}${c.year ? ` (${c.year})` : ""}`), h("div", { class: "sub" }, (c.overview || "").slice(0, 140))),
          h("button", { class: "btn subtle", type: "button", onclick: async () => {
            try { await api(`/api/library/title/${m.media_key}/match`, { method: "POST", body: { candidate: c } }); dlg.close(); toast("Updated"); this.open("title", m.media_key); }
            catch (e) { toast(e.message); }
          } }, "Use this"))) : [h("li", {}, h("span"), h("span", { class: "sub" }, "Nothing found. Try a shorter title."), h("span"))]));
      } catch (err) { results.replaceChildren(h("li", {}, h("span"), h("span", { class: "error" }, err.message), h("span"))); }
    };
    $("#match-form").onsubmit = (e) => { e.preventDefault(); search(); };
    dlg.showModal(); search();
  },
};

/* ===================================================== tasks */
const ago = (t) => {
  const s = Math.max(0, Date.now() / 1000 - t);
  return s < 90 ? "just now" : s < 5400 ? `${Math.round(s / 60)} min ago` : s < 129600 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} days ago`;
};
const inTime = (t) => {
  const s = t - Date.now() / 1000;
  return s < 90 ? "any moment" : s < 5400 ? `in ${Math.round(s / 60)} min` : s < 129600 ? `in ${Math.round(s / 3600)} h` : `in ${Math.round(s / 86400)} days`;
};
const INTERVALS = [[0.25, "Every 15 minutes"], [1, "Every hour"], [3, "Every 3 hours"], [6, "Every 6 hours"],
                   [12, "Every 12 hours"], [24, "Every day"], [168, "Every week"]];

const Tasks = {
  timer: null, data: null,
  async open() {
    clearTimeout(this.timer);
    document.title = "Tasks – Hush";
    await this.load();
  },
  async load() {
    clearTimeout(this.timer);
    try { [this.data, this.notify] = await Promise.all([api("/api/tasks"), api("/api/notifications")]); } catch { return; }
    if (!this.lib) await this.loadMore();
    if (location.hash.startsWith("#/tasks")) {
      if (!this.editing()) this.render();
      this.timer = setTimeout(() => this.load(), 4000);
    }
  },
  editing() { return !!document.activeElement?.closest?.("#tasks-list select, #tasks-list input"); },
  async save(id, patch) {
    try { this.data = await api(`/api/tasks/${id}`, { method: "PUT", body: patch }); this.render(); }
    catch (err) { toast(err.message); this.load(); }
  },
  async runNow(id) {
    try { await api(`/api/tasks/${id}/run`, { method: "POST" }); toast("Started"); } catch (err) { toast(err.message); }
    setTimeout(() => this.load(), 600);
  },
  render() {
    const { tasks, library, sources } = this.data;
    $("#tasks-summary").textContent = library.titles
      ? `${plural(library.titles, "title")} in your library, ${library.scanned} scanned.`
      : "Run a library refresh to count your titles.";
    $("#tasks-list").replaceChildren(...tasks.map((t) => {
      const status = [];
      if (t.running) status.push(h("span", { class: "busy" }, "Running now…"));
      else if (t.last_run) status.push(h("span", { class: t.last_status === "error" ? "error" : "" },
        `${t.last_status === "error" ? "Failed" : "Last run"} ${ago(t.last_run)}${t.last_duration != null ? ` (${Math.round(t.last_duration)} s)` : ""}`));
      else status.push(h("span", {}, "Hasn't run yet"));
      if (t.last_result) status.push(h("span", { class: t.last_status === "error" ? "error" : "" }, t.last_result));
      if (t.enabled && t.next_run && !t.running) status.push(h("span", {}, `Next run ${inTime(t.next_run)}`));
      if (!t.enabled) status.push(h("span", {}, "Off: only runs when you press Run now"));

      const opts = [
        h("label", {}, h("input", { type: "checkbox", checked: t.enabled, onchange: (e) => this.save(t.id, { enabled: e.target.checked }) }), "Run automatically"),
        h("select", { "aria-label": "How often", onchange: (e) => this.save(t.id, { interval_hours: Number(e.target.value) }) },
          ...(INTERVALS.some(([v]) => v === t.interval_hours) ? INTERVALS : [...INTERVALS, [t.interval_hours, `Every ${t.interval_hours} h`]])
            .map(([v, label]) => h("option", { value: v, selected: v === t.interval_hours }, label))),
      ];
      const extra = [];
      if (t.id === "refresh") {
        extra.push(h("div", { class: "task-sources", role: "group", "aria-label": "Sources to refresh" },
          ...sources.map((s) => h("label", {}, h("input", { type: "checkbox", checked: t.sources.includes(s.id), onchange: (e) => {
            const on = new Set(t.sources); e.target.checked ? on.add(s.id) : on.delete(s.id); this.save(t.id, { sources: [...on] });
          } }), s.name))));
        extra.push(h("div", { class: "task-opts" }, h("label", {}, h("input", { type: "checkbox", checked: t.scan_new,
          onchange: (e) => this.save(t.id, { scan_new: e.target.checked }) }), "Queue scans for titles that haven't been scanned")));
      }
      return h("article", { class: "task" },
        h("div", { class: "task-top" }, h("div", {}, h("h2", {}, t.name), h("p", {}, t.description)),
          h("button", { class: "btn subtle", type: "button", disabled: t.running, onclick: () => this.runNow(t.id) }, t.running ? "Running…" : "Run now")),
        h("div", { class: "task-opts" }, ...opts), ...extra,
        h("div", { class: "task-status" }, ...status));
    }), this.renderDetails(), this.renderTidy(), this.renderNotify());
  },
  async loadMore() {
    try { this.lib = await api("/api/library/settings"); this.batches = await api("/api/rename/batches"); } catch { /* keep old */ }
  },
  renderDetails() {
    const s = this.lib || { provider: "auto", has_key: false };
    const key = h("input", { type: "password", placeholder: s.has_key ? "A key is saved. Paste a new one to replace it." : "Paste your TMDB key (optional)", autocomplete: "off", spellcheck: "false", "aria-label": "TMDB API key" });
    key.addEventListener("change", async () => {
      if (!key.value.trim()) return;
      try { this.lib = await api("/api/library/settings", { method: "PUT", body: { tmdb_key: key.value.trim() } }); toast("Key saved"); } catch (e) { toast(e.message); }
      this.render();
    });
    return h("article", { class: "task" },
      h("div", { class: "task-top" }, h("div", {}, h("h2", {}, "Movie and show details"),
        h("p", {}, "Where summaries, genres and posters come from. Automatic uses TMDB when you add a free key, and the free Wikipedia and TVmaze services otherwise. Details in .nfo files next to your videos always win.")),
        h("button", { class: "btn subtle", type: "button", onclick: async () => {
          try { toast((await api("/api/library/settings/test", { method: "POST" })).message); } catch (e) { toast(e.message); }
        } }, "Test")),
      h("div", { class: "task-opts" },
        h("select", { "aria-label": "Source of details", onchange: async (e) => {
          try { this.lib = await api("/api/library/settings", { method: "PUT", body: { provider: e.target.value } }); } catch (err) { toast(err.message); }
          this.render();
        } },
          h("option", { value: "auto", selected: s.provider === "auto" }, "Automatic"),
          h("option", { value: "tmdb", selected: s.provider === "tmdb" }, "TMDB only"),
          h("option", { value: "none", selected: s.provider === "none" }, "Off: use file names and .nfo files only")),
        key),
      h("p", { class: "hint" }, "Get a free key at themoviedb.org → Settings → API. The key stays on your server."));
  },
  tidy: { source: "", layout: "flat", matched: true, plan: null, picked: new Set(), busy: false, result: null },
  renderTidy() {
    const t = this.tidy, locals = (this.data.sources || []).filter((s) => s.type === "local");
    if (!t.source || !locals.some((s) => s.id === t.source)) t.source = locals[0]?.id || "";
    const preview = async () => {
      t.busy = true; t.result = null; this.render();
      try {
        const q = new URLSearchParams({ source_id: t.source, only_matched: t.matched, layout: t.layout });
        t.plan = await api(`/api/rename/plan?${q}`);
        t.picked = new Set(t.plan.groups.map((g) => g.id));
      } catch (e) { toast(e.message); t.plan = null; }
      t.busy = false; this.render();
    };
    const apply = async () => {
      if (!confirm(`Rename ${plural(t.picked.size, "group")} of files now? You can undo it right afterwards.`)) return;
      t.busy = true; this.render();
      try {
        t.result = await api("/api/rename/apply", { method: "POST", body: { source_id: t.source, ids: [...t.picked], only_matched: t.matched, layout: t.layout } });
        t.plan = null; await this.loadMore();
      } catch (e) { toast(e.message); }
      t.busy = false; this.render();
    };
    const undo = async (batch) => {
      if (!confirm("Put every file from that rename back where it was?")) return;
      try {
        const r = await api(`/api/rename/undo/${batch}`, { method: "POST" });
        toast(r.problems.length ? `Undone, but: ${r.problems[0]}` : "Everything is back as it was");
        await this.loadMore();
      } catch (e) { toast(e.message); }
      this.render();
    };
    const last = (this.batches || []).find((b) => !b.undone);
    const sel = h("select", { "aria-label": "Folder to tidy", onchange: (e) => { t.source = e.target.value; t.plan = null; this.render(); } },
      ...locals.map((s) => h("option", { value: s.id, selected: s.id === t.source }, s.name)));
    const layout = h("select", { "aria-label": "Layout", onchange: (e) => { t.layout = e.target.value; t.plan = null; this.render(); } },
      h("option", { value: "flat", selected: t.layout === "flat" }, "All files directly in the folder"),
      h("option", { value: "folders", selected: t.layout === "folders" }, "One folder per movie, show and season"));
    const plan = t.plan;
    return h("article", { class: "task" },
      h("div", { class: "task-top" }, h("div", {}, h("h2", {}, "Tidy file names"),
        h("p", {}, "Renames your files to Title (Year).mkv and Show (Year) - S01E02 - Episode.mkv, using the details above. Nothing changes until you press Rename, and every rename can be undone. Hush never overwrites a file.")),
        h("button", { class: "btn subtle", type: "button", disabled: !t.source || t.busy, onclick: preview }, t.busy && !plan ? "Working…" : "Preview")),
      locals.length ? h("div", { class: "task-opts" }, sel, layout,
        h("label", {}, h("input", { type: "checkbox", checked: t.matched, onchange: (e) => { t.matched = e.target.checked; t.plan = null; this.render(); } }), "Only titles with a confirmed match"))
        : h("p", { class: "hint" }, "Renaming works on Local sources, which are folders on the server. Add one first."),
      plan ? h("div", {},
        h("p", { class: "hint" }, `${plural(plan.groups.length, "group")} to rename${plan.tidy ? `, ${plan.tidy} already tidy` : ""}${plan.skipped.length ? `, ${plan.skipped.length} skipped` : ""}.`),
        plan.groups.length ? h("ul", { class: "tidy-list" }, ...plan.groups.map((g) => h("li", {},
          h("input", { type: "checkbox", checked: t.picked.has(g.id), "aria-label": g.label, onchange: (e) => { e.target.checked ? t.picked.add(g.id) : t.picked.delete(g.id); this.render(); } }),
          h("div", {}, h("strong", {}, g.label),
            ...g.items.slice(0, 6).map((i) => h("div", {}, h("div", { class: "from" }, i.from.split("/").slice(-1)[0]), h("div", { class: "to" }, "→ " + i.to.split("/").slice(-1)[0]))),
            g.items.length > 6 ? h("div", { class: "from" }, `and ${g.items.length - 6} more`) : null)))) : null,
        plan.skipped.length ? h("details", {}, h("summary", { class: "hint" }, "Skipped"), h("ul", { class: "tidy-list" }, ...plan.skipped.map((s) => h("li", {}, h("span"), h("div", {}, s.name, h("div", { class: "from" }, s.reason)))))) : null,
        plan.groups.length ? h("div", { class: "task-opts" }, h("button", { class: "btn primary", type: "button", disabled: !t.picked.size || t.busy, onclick: apply }, `Rename ${plural(t.picked.size, "group")}`)) : null) : null,
      t.result ? h("p", { class: t.result.failed.length ? "error" : "hint" }, `Renamed ${plural(t.result.renamed, "title")}.${t.result.failed.length ? ` ${t.result.failed.length} failed: ${t.result.failed[0].reason}` : ""}`) : null,
      last ? h("div", { class: "task-opts" }, h("button", { class: "btn ghost", type: "button", onclick: () => undo(last.batch) }, `Undo the last rename (${plural(last.moves, "file move")})`)) : null);
  },
  async saveNotify(patch) {
    try { this.notify = await api("/api/notifications", { method: "PUT", body: patch }); toast("Saved"); }
    catch (err) { toast(err.message); }
    this.render();
  },
  renderNotify() {
    const n = this.notify;
    const url = h("input", { type: "text", value: n.url, placeholder: "https://ntfy.sh/my-hush  (or any webhook address)", spellcheck: "false", "aria-label": "Webhook address" });
    url.addEventListener("change", () => this.saveNotify({ url: url.value }));
    return h("article", { class: "task" },
      h("div", { class: "task-top" }, h("div", {}, h("h2", {}, "Notifications"),
        h("p", {}, "Get a message when a batch of scans finishes or a task fails. Works with ntfy, Gotify, Home Assistant and other webhooks.")),
        h("button", { class: "btn subtle", type: "button", onclick: async () => {
          try { await api("/api/notifications/test", { method: "POST" }); toast("Test sent"); } catch (err) { toast(err.message); }
        } }, "Send a test")),
      url,
      h("div", { class: "task-opts" },
        h("select", { "aria-label": "Message format", onchange: (e) => this.saveNotify({ format: e.target.value }) },
          h("option", { value: "text", selected: n.format === "text" }, "Plain text (ntfy, Gotify)"),
          h("option", { value: "json", selected: n.format === "json" }, "JSON (Home Assistant, others)")),
        h("label", {}, h("input", { type: "checkbox", checked: n.on_scans_done, onchange: (e) => this.saveNotify({ on_scans_done: e.target.checked }) }), "Scans finished"),
        h("label", {}, h("input", { type: "checkbox", checked: n.on_failure, onchange: (e) => this.saveNotify({ on_failure: e.target.checked }) }), "A task failed")),
      n.last_error ? h("div", { class: "task-status" }, h("span", { class: "error" }, `The last message didn't go through: ${n.last_error}`)) : null);
  },
};

/* ===================================================== player */
const video = $("#video");

const Player = {
  src: null, item: null, info: null, mode: "direct", offset: 0, duration: 0,
  filter: null, ranges: [], cats: new Set(), filterOn: store.get("filterOn", true),
  bleep: store.get("mode", "mute") === "bleep", audioIndex: null, subCues: null,
  job: null, markStart: null, selected: null, pendingSeek: null,

  /* ---------- loading ---------- */
  async open(sourceId, itemId) {
    this.close(false);
    this.src = sourceId; this.item = itemId; this.triedTranscode = false;
    Queue.sync(sourceId, itemId);
    $("#library").hidden = true; $("#player").hidden = false;
    document.body.style.overflow = "hidden";
    this.message("Opening…");
    try {
      this.info = await api(`/api/media/${sourceId}/${itemId}`);
    } catch (err) { this.message(err.message, true); return; }
    const info = this.info;
    this.duration = info.probe.duration || 0;
    this.mode = info.mode;
    $("#now-title").textContent = info.title;
    document.title = `${info.title} – Hush`;
    $("#audio-title").textContent = info.title;
    $("#player").classList.toggle("is-audio", info.kind === "audio");
    $("#audio-art").hidden = info.kind !== "audio";
    $("#t-dur").textContent = info.live ? "LIVE" : fmt(this.duration);
    $("#timeline").setAttribute("aria-valuemax", Math.round(this.duration));
    this.setupTracks();
    this.applyFilterButton();
    $("#mode-select").value = this.bleep ? "bleep" : "mute";
    this.startAt(0, true);
    await this.loadFilter();
    this.job = info.job;
    if (this.job) Jobs.poll();
    this.renderPanel();
  },

  close(goBack = true) {
    video.pause(); video.removeAttribute("src"); video.load();
    this.subCues = null; $("#subs").replaceChildren();
    this.filter = null; this.ranges = []; this.markStart = null; this.selected = null;
    $("#player").classList.remove("playing", "idle");
    $("#player").hidden = true; $("#library").hidden = false;
    document.body.style.overflow = "";
    document.title = "Hush";
    if (document.fullscreenElement) document.exitFullscreen();
    if (goBack) history.length > 1 ? history.back() : go("#/");
  },

  setupTracks() {
    const p = this.info.probe;
    const aSel = $("#audio-select");
    aSel.replaceChildren(...p.audio.map((a) => h("option", { value: a.index }, a.label || `Track ${a.index}`)));
    aSel.disabled = p.audio.length < 2;
    this.audioIndex = p.audio.length ? p.audio[0].index : null;
    const sSel = $("#sub-select");
    sSel.replaceChildren(h("option", { value: "" }, "Off"),
      ...p.subtitles.map((s) => h("option", { value: s.index }, s.label || `Subtitles ${s.index}`)));
    api(`/api/sidecars/${this.src}/${this.item}`).then((list) => {
      for (const s of list) sSel.append(h("option", { value: s.id }, s.label));
    }).catch(() => {});
  },

  streamUrl(start) {
    const q = new URLSearchParams({ start: start.toFixed(3) });
    if (this.audioIndex != null) q.set("audio", this.audioIndex);
    if (this.mode !== "direct") q.set("mode", this.mode);
    return `/api/stream/${this.src}/${this.item}?${q}`;
  },

  async startAt(t, initial = false) {
    const wasPlaying = !video.paused || initial;
    if (this.mode === "direct") {
      if (initial) video.src = `/api/raw/${this.src}/${this.item}`;
      else video.currentTime = t;
      this.offset = 0;
    } else {
      let landing = t;
      if (this.mode === "remux" && t > 0.2) {
        try { landing = (await api(`/api/seekpoint/${this.src}/${this.item}?t=${t}&mode=remux`)).start; } catch { /* use t */ }
      }
      this.offset = landing;
      this.pendingSeek = t - landing > 0.3 ? t - landing : null;
      video.src = this.streamUrl(landing);
    }
    this.message(null);
    this.Audio.reset();
    if (wasPlaying && !initial) video.play().catch(() => {});
  },

  now() { return this.offset + (video.currentTime || 0); },
  seek(t) { if (this.info?.live) return; this.startAt(Math.max(0, Math.min(t, (this.duration || 1e9) - 0.5))); },

  async loadFilter() {
    try {
      this.filter = await api(`/api/filters/${this.info.media_key}`);
      this.ranges = this.filter.ranges;
    } catch (err) {
      this.filter = null; this.ranges = [];
      if (err.status !== 404) toast(err.message);
    }
    const saved = store.get("cats", null);
    const cats = this.categories();
    this.cats = new Set(cats.filter((c) => saved ? saved.includes(c.id) : c.default).map((c) => c.id));
    this.renderMarks(); this.Audio.reset();
  },

  categories() { return (S.config?.categories || []); },
  active(r) { return r.enabled !== false && (r.source === "manual" || this.cats.has(r.category)); },
  activeRanges() { return this.ranges.filter((r) => this.active(r)); },
  rangeAt(t) { return this.ranges.find((r) => this.active(r) && t >= r.start && t < r.end); },
  /* Overlapping ranges are merged so one range's end never unmutes another. */
  intervals() {
    if (this._iv) return this._iv;
    const out = [];
    for (const r of this.activeRanges().sort((a, b) => a.start - b.start)) {
      const last = out[out.length - 1];
      if (last && r.start <= last.end + 0.02) last.end = Math.max(last.end, r.end);
      else out.push({ start: r.start, end: r.end });
    }
    out.forEach((iv) => (iv.id = iv.start.toFixed(3)));
    return (this._iv = out);
  },
  intervalAt(t) { return this.intervals().find((iv) => t >= iv.start && t < iv.end); },

  /* ---------- the audio filter ---------- */
  Audio: {
    ctx: null, mute: null, master: null, toneGain: null, scheduled: new Set(), timer: null, fallback: false,
    ensure() {
      if (this.ctx || this.fallback) { this.ctx?.resume(); return; }
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" });
        const source = ctx.createMediaElementSource(video);
        this.mute = ctx.createGain(); this.master = ctx.createGain(); this.toneGain = ctx.createGain();
        this.toneGain.gain.value = 0;
        const osc = ctx.createOscillator(); osc.type = "sine"; osc.frequency.value = 660;
        source.connect(this.mute).connect(this.master).connect(ctx.destination);
        osc.connect(this.toneGain).connect(this.master);
        osc.start();
        this.ctx = ctx;
        this.master.gain.value = Number($("#volume").value);
      } catch (err) {
        console.warn("Web Audio unavailable, using element mute", err);
        this.fallback = true;
      }
      if (!this.timer) this.timer = setInterval(() => this.tick(), 25);
    },
    volume(v) { if (this.master) this.master.gain.value = v; else video.volume = v; },
    set(muted, at) {
      if (!this.ctx) { video.muted = muted; return; }
      const when = at ?? this.ctx.currentTime;
      this.mute.gain.setTargetAtTime(muted ? 0 : 1, when, 0.004);
      this.toneGain.gain.setTargetAtTime(muted && Player.bleep ? 0.12 : 0, when, 0.004);
    },
    reset() {
      Player._iv = null;
      this.scheduled.clear();
      if (this.ctx) {
        const now = this.ctx.currentTime;
        this.mute.gain.cancelScheduledValues(now); this.toneGain.gain.cancelScheduledValues(now);
      }
      this.set(Player.filterOn && !!Player.intervalAt(Player.now()) && !video.paused);
    },
    tick() {
      const P = Player;
      if (!P.filterOn || video.paused || !P.intervals().length) {
        if (this.scheduled.size || (this.ctx ? this.mute.gain.value < 1 : video.muted)) { this.scheduled.clear(); this.set(false); }
        return;
      }
      const now = P.now(), rate = video.playbackRate || 1;
      const inside = P.intervalAt(now);
      if (!this.ctx) { video.muted = !!inside; return; }
      if (inside && !this.scheduled.has(inside.id) && this.mute.gain.value > 0.5) {
        this.set(true);                               // landed inside a range: mute now
        this.set(false, this.ctx.currentTime + (inside.end - now) / rate);
        this.scheduled.add(inside.id);
      }
      for (const r of P.intervals()) {               // schedule what starts in the next 200 ms
        if (r.start <= now || r.start > now + 0.2 || this.scheduled.has(r.id)) continue;
        const t0 = this.ctx.currentTime + (r.start - now) / rate;
        this.set(true, t0);
        this.set(false, this.ctx.currentTime + (r.end - now) / rate);
        this.scheduled.add(r.id);
      }
    },
  },

  /* ---------- UI ---------- */
  message(text, isError = false) {
    const m = $("#stage-msg");
    m.hidden = !text; m.textContent = text || ""; m.classList.toggle("error", isError);
  },

  applyFilterButton() {
    const b = $("#filter-btn");
    b.setAttribute("aria-pressed", String(this.filterOn));
    $("#filter-label").textContent = this.filterOn ? "Filter on" : "Filter off";
    $("#player").classList.toggle("unfiltered", !this.filterOn);
  },

  renderMarks() {
    const box = $("#tl-marks");
    const d = this.duration || 1;
    box.replaceChildren(...this.ranges.filter((r) => r.source === "manual" || this.cats.has(r.category)).map((r) => h("i", {
      class: r.enabled === false ? "off" : "",
      style: `left:${(r.start / d) * 100}%;width:${Math.max(0.15, ((r.end - r.start) / d) * 100)}%`,
    })));
  },

  frame() {
    const t = this.now(), d = this.duration || 1;
    $("#t-now").textContent = fmt(t);
    $("#tl-played").style.width = `${Math.min(100, (t / d) * 100)}%`;
    $("#tl-head").style.left = `${Math.min(100, (t / d) * 100)}%`;
    $("#timeline").setAttribute("aria-valuenow", Math.round(t));
    $("#timeline").setAttribute("aria-valuetext", `${fmt(t)} of ${fmt(d)}`);
    if (video.buffered.length) {
      const end = this.offset + video.buffered.end(video.buffered.length - 1);
      $("#tl-buffer").style.width = `${Math.min(100, (end / d) * 100)}%`;
    }
    const inside = this.filterOn && !video.paused ? this.rangeAt(t) : null;
    $("#filter-btn").classList.toggle("muting", !!inside);
    this.renderSubs(t);
    const cur = $(".range.current"); const id = inside?.id;
    if (cur && cur.dataset.id !== id) cur.classList.remove("current");
    if (id) $(`.range[data-id="${id}"]`)?.classList.add("current");
  },

  /* ---------- subtitles (censored on screen too) ---------- */
  async loadSubs(track) {
    this.subCues = null; $("#subs").replaceChildren();
    if (!track) return;
    try {
      const vtt = await api(`/api/subtitle/${this.src}/${this.item}/${track}`);
      this.subCues = parseVTT(vtt);
    } catch (err) { toast(`Subtitles couldn't load: ${err.message}`); }
  },
  renderSubs(t) {
    if (!this.subCues) return;
    const cue = this.subCues.find((c) => t >= c.start && t <= c.end);
    const box = $("#subs");
    if ((box.dataset.cue || "") === String(cue?.start ?? "") && box.dataset.f === String(this.filterOn)) return;
    box.dataset.cue = cue ? String(cue.start) : ""; box.dataset.f = String(this.filterOn);
    if (!cue) { box.replaceChildren(); return; }
    const words = new Set();
    if (this.filterOn) {
      for (const r of this.ranges) {
        if (!this.active(r) || r.end < cue.start - 0.5 || r.start > cue.end + 0.5) continue;
        (r.words || []).forEach((w) => words.add(w.toLowerCase().replace(/[^\p{L}\p{N}' ]/gu, "")));
      }
    }
    box.replaceChildren(h("span", {}, ...censor(cue.text, words)));
  },

  /* ---------- language panel ---------- */
  renderPanel() {
    const status = $("#panel-status");
    const hasFilter = !!this.filter;
    const running = this.job && (this.job.status === "running" || this.job.status === "queued");
    $("#cats").hidden = !hasFilter; $("#range-tools").hidden = !hasFilter; $("#panel-foot").hidden = !hasFilter;
    const eng = S.config?.engines || {};
    if (this.info?.live) {
      status.replaceChildren(h("p", {}, "This is a live stream, so it can't be scanned or filtered. It plays as it is."));
      $("#cats").hidden = $("#range-tools").hidden = $("#panel-foot").hidden = true;
      $("#ranges").replaceChildren();
      return;
    }
    if (running) {
      status.replaceChildren(
        h("p", {}, `Scanning this title. ${jobText(this.job)}. You can keep watching; the filter turns on when it's ready.`),
        h("div", { class: "progress" }, h("i", { style: `width:${Math.round(this.job.progress * 100)}%` })),
        h("div", { class: "actions" }, h("button", { class: "btn ghost", type: "button", onclick: () => this.cancelScan() }, "Cancel scan")));
    } else if (!hasFilter) {
      const failed = this.job?.status === "error" ? h("p", { class: "error" }, jobText(this.job)) : null;
      status.replaceChildren(
        h("p", {}, eng.whisper
          ? "This title hasn't been scanned. Hush listens to the dialogue and marks every word on your list, then mutes those moments while you watch."
          : "This title hasn't been scanned. Hush reads the subtitle track, marks every word on your list, then mutes those moments while you watch."),
        failed,
        h("div", { class: "actions" },
          h("button", { class: "btn primary", type: "button", onclick: () => this.scan() }, "Scan this title"),
          eng.whisper && this.info?.probe.subtitles.length
            ? h("button", { class: "btn ghost", type: "button", onclick: () => this.scan("subtitles") }, "Quick scan from subtitles") : null),
        !eng.whisper ? h("p", { class: "hint" }, "For titles without subtitles, install faster-whisper on the server to scan the audio itself.") : null,
        h("div", { class: "actions" },
          h("label", { class: "btn ghost", style: "display:inline-flex" }, "Load a filter file",
            h("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: (e) => this.importFile(e.target.files[0]) }))),
      );
    } else {
      const n = this.activeRanges().length;
      const how = { whisper: "from the dialogue audio", subtitles: "from the subtitles", manual: "by hand" }[this.filter.engine] || "";
      status.replaceChildren(h("p", {}, `${plural(n, "moment")} will be ${this.bleep ? "covered with a tone" : "muted"}. Scanned ${how}.`));
    }
    if (!hasFilter) { $("#ranges").replaceChildren(); return; }

    const counts = {};
    for (const r of this.ranges) counts[r.category] = (counts[r.category] || 0) + 1;
    $("#cat-list").replaceChildren(...this.categories().map((c) => h("label", { class: "chip" },
      h("input", { type: "checkbox", checked: this.cats.has(c.id), onchange: (e) => {
        e.target.checked ? this.cats.add(c.id) : this.cats.delete(c.id);
        store.set("cats", [...this.cats]); this.renderMarks(); this.renderPanel(); this.Audio.reset();
      } }), c.label, h("span", { class: "n" }, String(counts[c.id] || 0)))));
    this.renderRanges();
    $("#export-json").href = `/api/filters/${this.info.media_key}/export?format=json`;
    $("#export-edl").href = `/api/filters/${this.info.media_key}/export?format=edl&cats=${[...this.cats].join(",")}`;
  },

  renderRanges() {
    const reveal = $("#reveal").checked;
    const labels = Object.fromEntries(this.categories().map((c) => [c.id, c.label]));
    const list = this.ranges.filter((r) => r.source === "manual" || this.cats.has(r.category));
    $("#ranges").replaceChildren(...list.map((r) => h("li", {
      class: `range ${r.enabled === false ? "off" : ""}`, "data-id": r.id,
    },
      h("button", { class: "when", type: "button", onclick: () => { this.selected = r.id; this.seek(r.start - 2); this.renderRanges(); }, "aria-label": `Play from ${fmt(r.start)}` }, fmt(r.start)),
      h("div", {}, h("div", { class: "ctx" }, ...contextNodes(r, reveal)),
        h("span", { class: "cat" }, r.source === "manual" ? "Marked by you" : (labels[r.category] || r.category))),
      h("div", { class: "ops" },
        h("input", { type: "checkbox", checked: r.enabled !== false, "aria-label": r.enabled === false ? "Not filtered. Filter this moment" : "Filtered. Let this moment play",
          title: "Filter this moment", onchange: (e) => { r.enabled = e.target.checked; this.changed(); } }),
        h("button", { class: "icon-btn", type: "button", "aria-label": "Delete this moment", title: "Delete",
          onclick: () => { this.ranges = this.ranges.filter((x) => x !== r); this.changed(); }, html: `<svg viewBox="0 0 24 24">${ICONS.trash}</svg>` })),
      this.selected === r.id ? h("div", { class: "nudge" },
        h("span", {}, `${fmtPrecise(r.start)} to ${fmtPrecise(r.end)}`),
        h("button", { type: "button", onclick: () => this.nudge(r, "start", -0.1) }, "Start earlier"),
        h("button", { type: "button", onclick: () => this.nudge(r, "start", 0.1) }, "Start later"),
        h("button", { type: "button", onclick: () => this.nudge(r, "end", -0.1) }, "End sooner"),
        h("button", { type: "button", onclick: () => this.nudge(r, "end", 0.1) }, "End later")) : null,
    )));
  },

  nudge(r, edge, delta) {
    r[edge] = Math.max(0, Math.round((r[edge] + delta) * 1000) / 1000);
    if (r.end - r.start < 0.05) r[edge === "start" ? "start" : "end"] -= delta;
    this.changed();
    this.seek(r.start - 1.5);
  },

  saveTimer: null,
  changed() {
    this.ranges.sort((a, b) => a.start - b.start);
    this.renderMarks(); this.renderPanel(); this.Audio.reset();
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(async () => {
      try {
        this.filter = await api(`/api/filters/${this.info.media_key}`, { method: "PUT",
          body: { source_id: this.src, item_id: this.item, title: this.info.title, duration: this.duration, ranges: this.ranges } });
        this.ranges = this.filter.ranges; this.renderMarks();
      } catch (err) { toast(`Couldn't save: ${err.message}`); }
    }, 600);
  },

  mark() {
    const t = this.now();
    if (this.markStart == null) {
      this.markStart = t;
      $("#mark-btn").textContent = "End mark here";
      toast("Marking. Press M again where it should end.");
      return;
    }
    const [s, e] = [Math.min(this.markStart, t), Math.max(this.markStart, t)];
    this.markStart = null; $("#mark-btn").textContent = "Mark a moment";
    if (e - s < 0.2) { toast("That mark was too short."); return; }
    if (!this.filter) this.filter = { engine: "manual", ranges: [] };
    this.ranges.push({ id: Math.random().toString(36).slice(2, 12), start: s, end: e, words: [], category: "manual",
      context: "", source: "manual", enabled: true });
    toast(`Marked ${fmt(s)} to ${fmt(e)}`);
    this.changed();
  },

  async scan(engine) {
    try {
      this.job = await api("/api/analyze", { method: "POST", body: { source_id: this.src, item_id: this.item, title: this.info.title, engine } });
      this.renderPanel(); Jobs.poll();
    } catch (err) { toast(err.message); }
  },
  async cancelScan() {
    if (!this.job) return;
    await api(`/api/jobs/${this.job.id}/cancel`, { method: "POST" });
    Jobs.poll();
  },
  async importFile(file) {
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      if (!Array.isArray(data.ranges)) throw new Error("This isn't a Hush filter file.");
      this.filter = { engine: data.engine || "manual", ranges: [] };
      this.ranges = data.ranges;
      this.changed();
      toast(`Loaded ${plural(data.ranges.length, "moment")}`);
    } catch (err) { toast(err.message); }
  },

  onJobs(list) {
    if (!this.info || $("#player").hidden) return;
    const j = list.find((x) => x.media_key === this.info.media_key);
    if (!j) return;
    const was = this.job?.status;
    this.job = j;
    if (j.status === "done" && was && was !== "done") { this.loadFilter().then(() => this.renderPanel()); toast("Language filter is ready"); }
    else if (!$("#panel").hidden || j.status !== was) this.renderPanel();
  },
};

function parseVTT(text) {
  const cues = [];
  const ts = (s) => { const p = s.trim().split(":").map(Number); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]; };
  for (const block of text.replace(/\r/g, "").split(/\n\n+/)) {
    const lines = block.split("\n");
    const i = lines.findIndex((l) => l.includes("-->"));
    if (i < 0) continue;
    const [a, b] = lines[i].split("-->");
    const body = lines.slice(i + 1).join("\n").replace(/<[^>]+>/g, "").trim();
    if (body) cues.push({ start: ts(a), end: ts(b.trim().split(/\s+/)[0]), text: body });
  }
  return cues.sort((x, y) => x.start - y.start);
}

function censor(text, words) {
  if (!words.size) return [text];
  const out = [];
  const phrases = [...words].filter(Boolean).sort((a, b) => b.length - a.length)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "[\\s,.!?-]+"));
  if (!phrases.length) return [text];
  const re = new RegExp(`(^|[^\\p{L}])(${phrases.join("|")})(?=$|[^\\p{L}])`, "giu");
  let last = 0, m;
  while ((m = re.exec(text))) {
    const start = m.index + m[1].length;
    out.push(text.slice(last, start), h("span", { class: "bleeped" }, "•".repeat(Math.min(6, Math.max(3, m[2].length)))));
    last = start + m[2].length;
  }
  out.push(text.slice(last));
  return out;
}

// Words inside flagged phrases ("son of a …", "oh my …") that are fine on their own.
const COMMON = new Set("a an the of my oh for to son go sake swear with have had having get got off you it in on up out good holy lord christ jesus god gosh".split(" "));
const hide = (w) => w.replace(/\p{L}+/gu, (word) => word[0] + "•".repeat(word.length - 1));
function contextNodes(r, reveal) {
  if (!r.context) return [r.source === "manual" ? `${fmtPrecise(r.start)} to ${fmtPrecise(r.end)}` : (r.words || []).join(" ")];
  // Neighbouring detections also appear in each context line, so hide every flagged word.
  const flagged = new Set(Player.ranges.flatMap((x) => x.words || []).map((w) => w.toLowerCase().replace(/[^\p{L}\p{N}']/gu, ""))
    .filter((w) => !COMMON.has(w)));
  const parts = r.context.split(/⟦|⟧/);
  return parts.map((p, i) => {
    if (i % 2) return h("mark", {}, reveal ? p : hide(p));
    return reveal ? p : p.replace(/[\p{L}']+/gu, (w) => flagged.has(w.toLowerCase()) ? hide(w) : w);
  });
}

/* ---------- player wiring ---------- */
$("#play-btn").addEventListener("click", togglePlay);
function togglePlay() {
  Player.Audio.ensure();
  if (video.paused) video.play().catch((e) => Player.message(`Playback couldn't start: ${e.message}`, true));
  else video.pause();
}
video.addEventListener("click", togglePlay);
video.addEventListener("play", () => { $("#player").classList.add("playing"); $("#play-btn").setAttribute("aria-label", "Pause"); Player.Audio.ensure(); Player.Audio.reset(); idle.bump(); });
video.addEventListener("pause", () => { $("#player").classList.remove("playing"); $("#play-btn").setAttribute("aria-label", "Play"); Player.Audio.reset(); idle.show(); });
video.addEventListener("seeked", () => Player.Audio.reset());
video.addEventListener("ratechange", () => Player.Audio.reset());
video.addEventListener("waiting", () => Player.Audio.reset());
video.addEventListener("playing", () => { Player.message(null); Player.Audio.reset(); });
function applyPendingSeek() {  // live streams start on a keyframe; skip the few seconds before the target
  const ps = Player.pendingSeek;
  if (ps == null || video.readyState < 2) return;
  // Only when the browser can seek inside this stream without re-requesting it.
  const ok = video.seekable.length && video.seekable.end(video.seekable.length - 1) > ps;
  if (!ok) { Player.pendingSeek = null; return; }
  if (video.buffered.length && video.buffered.end(video.buffered.length - 1) > ps + 0.3) {
    Player.pendingSeek = null; video.currentTime = ps;
  }
}
["progress", "canplay", "timeupdate"].forEach((ev) => video.addEventListener(ev, applyPendingSeek));
video.addEventListener("ended", () => { $("#player").classList.remove("playing"); if (!Player.info?.live) Queue.next(true); });
video.addEventListener("error", () => {
  if (!Player.info) return;
  if (Player.mode === "direct") {           // the browser refused the original: fall back to a live stream
    Player.mode = Player.info.probe.video.length ? "transcode" : "audio";
    Player.startAt(video.currentTime || 0).then(() => video.play().catch(() => {}));
    return;
  }
  if (Player.mode === "remux" && !Player.triedTranscode) {   // the copied video was not something this browser decodes
    Player.triedTranscode = true; Player.mode = "transcode";
    Player.message("Switching to a compatible stream…");
    Player.startAt(Player.now()).then(() => video.play().catch(() => {}));
    return;
  }
  const code = video.error?.code ? ` (error ${video.error.code})` : "";
  const safari = /^((?!chrome|android|crios|fxios).)*safari/i.test(navigator.userAgent);
  Player.message(safari && Player.mode !== "direct"
    ? `Safari can't play Hush's live streams yet${code}. Open this page in Chrome, Firefox or Edge, or use "Watch on another player".`
    : `This file couldn't be played${code}. Check that the server can still reach it.`, true);
});
(function loop() { if (!$("#player").hidden) Player.frame(); requestAnimationFrame(loop); })();

$("#back10").addEventListener("click", () => Player.seek(Player.now() - 10));
$("#fwd10").addEventListener("click", () => Player.seek(Player.now() + 10));
$("#back-btn").addEventListener("click", () => Player.close());
$("#volume").value = store.get("volume", 1);
$("#volume").addEventListener("input", (e) => { Player.Audio.volume(Number(e.target.value)); store.set("volume", Number(e.target.value)); });
$("#filter-btn").addEventListener("click", () => {
  Player.filterOn = !Player.filterOn; store.set("filterOn", Player.filterOn);
  Player.applyFilterButton(); Player.Audio.reset();
  toast(Player.filterOn ? "Filter on" : "Filter off. Every word will play.");
});
$("#mode-select").addEventListener("change", (e) => { Player.bleep = e.target.value === "bleep"; store.set("mode", e.target.value); Player.Audio.reset(); Player.renderPanel(); });
$("#sub-select").addEventListener("change", (e) => Player.loadSubs(e.target.value));
$("#audio-select").addEventListener("change", async (e) => {
  const t = Player.now();
  Player.audioIndex = Number(e.target.value);
  try {
    const info = await api(`/api/media/${Player.src}/${Player.item}?audio=${Player.audioIndex}`);
    Player.mode = info.mode === "direct" ? "direct" : info.mode;
  } catch { Player.mode = "remux"; }
  if (Player.mode === "direct") { video.src = `/api/raw/${Player.src}/${Player.item}`; video.currentTime = t; video.play().catch(() => {}); }
  else Player.startAt(t);
});
$("#settings-btn").addEventListener("click", (e) => {
  const s = $("#settings"); s.hidden = !s.hidden; e.currentTarget.setAttribute("aria-expanded", String(!s.hidden));
});
$("#fs-btn").addEventListener("click", () => document.fullscreenElement ? document.exitFullscreen() : $("#player").requestFullscreen?.());
function togglePanel(open) {
  const p = $("#panel"); p.hidden = open === undefined ? !p.hidden : !open;
  $("#panel-btn").setAttribute("aria-expanded", String(!p.hidden));
  if (!p.hidden) Player.renderPanel();
}
$("#panel-btn").addEventListener("click", () => togglePanel());
$("#panel-close").addEventListener("click", () => togglePanel(false));
$("#reveal").addEventListener("change", () => Player.renderRanges());
$("#mark-btn").addEventListener("click", () => Player.mark());
$("#rescan-btn").addEventListener("click", () => {
  if (confirm("Scan this title again? Moments you marked or switched off are kept.")) Player.scan();
});
$("#rematch-btn").addEventListener("click", async () => {
  try {
    Player.filter = await api(`/api/filters/${Player.info.media_key}/rematch`, { method: "POST" });
    Player.ranges = Player.filter.ranges; Player.renderMarks(); Player.renderPanel(); Player.Audio.reset();
    toast("Word list reapplied");
  } catch (err) { toast(err.message); }
});
$("#external-btn").addEventListener("click", async () => {
  try {
    const r = await api(`/api/external/${Player.src}/${Player.item}?cats=${[...Player.cats].join(",")}`);
    $("#external-url").value = r.url; $("#external-dialog").showModal(); $("#external-url").select();
  } catch (err) { toast(err.message); }
});
$("#copy-url").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#external-url").value); toast("Link copied"); }
  catch { $("#external-url").select(); toast("Press Ctrl+C to copy"); }
});

/* timeline: click, drag, keys, hover tip */
(() => {
  const tl = $("#timeline"), tip = $("#tl-tip");
  const at = (e) => { const r = tl.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (Player.duration || 0); };
  let dragging = false;
  tl.addEventListener("pointerdown", (e) => { dragging = true; tl.setPointerCapture(e.pointerId); });
  tl.addEventListener("pointerup", (e) => { if (dragging) { dragging = false; Player.seek(at(e)); } });
  tl.addEventListener("pointermove", (e) => {
    const t = at(e), r = tl.getBoundingClientRect();
    const hit = Player.ranges.find((x) => Player.active(x) && t >= x.start - Player.duration * 0.004 && t <= x.end + Player.duration * 0.004);
    tip.hidden = false; tip.style.left = `${e.clientX - r.left}px`;
    tip.classList.toggle("word", !!hit);
    tip.textContent = hit ? `${fmt(t)}  muted: ${hide((hit.words || []).join(" ")) || "your mark"}` : fmt(t);
    if (dragging) $("#tl-played").style.width = `${(t / (Player.duration || 1)) * 100}%`;
  });
  tl.addEventListener("pointerleave", () => (tip.hidden = true));
  tl.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") { Player.seek(Player.now() - 5); e.preventDefault(); }
    if (e.key === "ArrowRight") { Player.seek(Player.now() + 5); e.preventDefault(); }
  });
})();

/* hide controls while watching */
const idle = {
  timer: null,
  bump() { this.show(); clearTimeout(this.timer); this.timer = setTimeout(() => { if (!video.paused && $("#panel").hidden && $("#settings").hidden) $("#player").classList.add("idle"); }, 3000); },
  show() { $("#player").classList.remove("idle"); clearTimeout(this.timer); },
};
$("#player").addEventListener("pointermove", () => idle.bump());

document.addEventListener("keydown", (e) => {
  if ($("#player").hidden || e.target.matches("input:not([type=checkbox]):not([type=range]), select, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
  if (document.querySelector("dialog[open]")) return;
  const k = e.key.toLowerCase();
  const map = {
    n: () => Queue.next(), p: () => Queue.prev(), s: () => Queue.toggleShuffle(), r: () => Queue.cycleRepeat(),
    " ": togglePlay, k: togglePlay, f: () => $("#fs-btn").click(), m: () => Player.mark(), h: () => $("#filter-btn").click(),
    j: () => Player.seek(Player.now() - 10), l: () => Player.seek(Player.now() + 10),
    arrowleft: () => Player.seek(Player.now() - 10), arrowright: () => Player.seek(Player.now() + 10),
    escape: () => (!$("#panel").hidden ? togglePanel(false) : !$("#settings").hidden ? ($("#settings").hidden = true) : null),
  };
  if (e.target === $("#timeline") && (k === "arrowleft" || k === "arrowright")) return;
  if (map[k]) { e.preventDefault(); map[k](); idle.bump(); }
});

/* ===================================================== routing */
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
async function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const [view, src, id] = [parts[0], parts[1], parts.slice(2).join("/")];
  $("#tasks").hidden = view !== "tasks";
  if (view === "p" && src && id) { Player.open(src, id); return; }
  if (!$("#player").hidden) Player.close(false);
  if (view === "tasks") { $("#library").hidden = true; Tasks.open(); return; }
  $("#library").hidden = false;
  const inCatalog = ["movies", "shows", "show", "title"].includes(view);
  $("#catalog-view").hidden = !inCatalog; $("#browser-view").hidden = inCatalog;
  $$("#rail-links a").forEach((a) => { if (!inCatalog) a.removeAttribute("aria-current"); });
  if (inCatalog) { Catalog.open(view, src); return; }
  if (view === "b" && src) { browse(src, id || ""); return; }
  const first = S.sources.find((s) => !s.error);
  if (first) browse(first.id);
  else {
    $("#crumbs").replaceChildren(); $("#entries").replaceChildren();
    showEmpty("Add your first source", "Point Hush at a NAS share, a folder, a DLNA server, Jellyfin or Plex. You can also paste a link to a single video on the left.");
  }
}
window.addEventListener("hashchange", route);

async function start() {
  $("#login").hidden = true; $("#app").hidden = false;
  try {
    [S.config] = await Promise.all([api("/api/config"), loadSources()]);
  } catch { return; }
  route();
  Jobs.poll();
}

(async () => {
  try {
    const s = await api("/api/session");
    S.authRequired = s.auth_required;
    $("#logout-btn").hidden = !s.auth_required;
    s.logged_in ? start() : showLogin();
  } catch { showLogin(); }
})();
