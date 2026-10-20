/* app.legacy.js - built from app.js (sha256 9fd906e337f17cdd25b3ad3c74afdf118aee3c2388b125200ffc020de7cd6adb) by scripts/build-legacy.sh. Do not edit. */
window.__hushBooted = true;
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const LAZY_FALLBACK = !("loading" in HTMLImageElement.prototype) && "IntersectionObserver" in window;
const lazyImages = LAZY_FALLBACK ? new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) {
    e.target.src = e.target.dataset.src;
    lazyImages.unobserve(e.target);
  }
}, { rootMargin: "400px" }) : null;
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (tag === "img" && k === "src" && LAZY_FALLBACK && attrs.loading === "lazy") {
      el.dataset.src = v;
      lazyImages.observe(el);
      continue;
    }
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
};
const thumb = (url, w = 320) => url ? `${url}${url.includes("?") ? "&" : "?"}w=${w}` : url;
const when = (t) => {
  const d = new Date(t * 1e3), now = /* @__PURE__ */ new Date(), days = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 864e5);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (days < 0) return `Aired ${d.toLocaleDateString([], { weekday: "short" })} ${time}`;
  if (days === 0) return `${d.getHours() >= 18 ? "Tonight" : "Today"} ${time}`;
  if (days === 1) return `Tomorrow ${time}`;
  return `${d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })} ${time}`;
};
const hm = (t) => new Date(t * 1e3).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
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
  trash: '<path d="M6 7h12l-1 13H7zM9 4h6l1 2H8z"/>'
};
const icon = (name, cls = "ico") => {
  const t = document.createElement("template");
  t.innerHTML = `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.video}</svg>`;
  return t.content.firstChild;
};
const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const s = Math.floor(t % 60), m = Math.floor(t / 60) % 60, hr = Math.floor(t / 3600);
  return (hr ? `${hr}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(s).padStart(2, "0")}`;
};
const fmtPrecise = (t) => fmt(t) + "." + String(Math.floor(t % 1 * 10));
const fmtSize = (b) => b == null ? "" : b > 1e9 ? (b / 1e9).toFixed(1) + " GB" : b > 1e6 ? Math.round(b / 1e6) + " MB" : Math.max(1, Math.round(b / 1e3)) + " KB";
const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;
const store = {
  get(k, d) {
    try {
      const v = localStorage.getItem("hush." + k);
      return v == null ? d : JSON.parse(v);
    } catch (e) {
      return d;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem("hush." + k, JSON.stringify(v));
    } catch (e) {
    }
  }
};
const UA = navigator.userAgent;
const IS_LG = /Web0S|webOS|NetCast/i.test(UA);
const IS_WEBKIT = /^((?!chrome|android|crios|fxios|edg).)*safari/i.test(UA) || /iP(hone|ad|od)/.test(UA) || navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
const TVUA = /NetCast|Tizen|Web0S|WebOS|SmartTV|SMART-TV|HbbTV|AppleTV|Xbox|PlayStation|CrKey|BRAVIA|AFTM|AFTT|GoogleTV|HushTV|Android.*\bTV\b/i;
const IS_TV_DEVICE = TVUA.test(UA);
const HEVC = (() => {
  try {
    const v = document.createElement("video"), ok = (t) => !!v.canPlayType && v.canPlayType(`video/mp4; codecs="${t}"`) === "probably";
    return IS_WEBKIT ? 0 : ok("hvc1.2.4.L93.B0") ? 2 : ok("hvc1.1.6.L93.B0") ? 1 : 0;
  } catch (e) {
    return 0;
  }
})();
const KEYCODE_NAMES = {
  37: "ArrowLeft",
  38: "ArrowUp",
  39: "ArrowRight",
  40: "ArrowDown",
  13: "Enter",
  27: "Escape",
  8: "Backspace",
  461: "GoBack",
  10009: "GoBack",
  10182: "GoBack",
  415: "MediaPlay",
  19: "MediaPause",
  413: "MediaStop",
  417: "MediaFastForward",
  412: "MediaRewind",
  10252: "MediaPlayPause"
};
const normKey = (e) => e.key && e.key !== "Unidentified" && e.key !== "Dead" ? e.key : KEYCODE_NAMES[e.keyCode] || e.key || "";
const TAB = (() => {
  try {
    let t = sessionStorage.getItem("hush.tab");
    if (!t) {
      t = Math.random().toString(36).slice(2, 12);
      sessionStorage.setItem("hush.tab", t);
    }
    return t;
  } catch (e) {
    return Math.random().toString(36).slice(2, 12);
  }
})();
let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.hidden = true, 3200);
}
class ApiError extends Error {
  constructor(status, msg) {
    super(msg);
    this.status = status;
  }
}
async function api(path, opts = {}) {
  var _a;
  const init = { credentials: "same-origin", ...opts, headers: { ...opts.headers || {} } };
  if (opts.body && typeof opts.body !== "string") {
    init.body = JSON.stringify(opts.body);
    init.headers["Content-Type"] = "application/json";
  }
  const r = await fetch(path, init);
  if (r.status === 401 && !path.startsWith("/api/login")) {
    showLogin();
    throw new ApiError(401, "Sign in to continue");
  }
  const data = ((_a = r.headers.get("content-type")) == null ? void 0 : _a.includes("json")) ? await r.json() : await r.text();
  if (!r.ok) throw new ApiError(r.status, data && data.detail || `Request failed (${r.status})`);
  return data;
}
const S = {
  config: null,
  sources: [],
  source: null,
  dirNames: { "": null },
  dirParent: {},
  entries: []
};
function showLogin() {
  $("#app").hidden = true;
  $("#login").hidden = false;
  $("#password").focus();
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: { password: $("#password").value } });
    $("#password").value = "";
    start();
  } catch (err) {
    $("#login-error").textContent = err.message;
  }
});
$("#logout-btn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  showLogin();
});
$("#password-btn").addEventListener("click", () => {
  $("#password-form").reset();
  $("#pw-error").textContent = "";
  $("#pw-current-row").hidden = !S.authRequired;
  $("#password-dialog").showModal();
});
$("#password-form").addEventListener("submit", async (e) => {
  var _a;
  if (((_a = e.submitter) == null ? void 0 : _a.value) !== "save") return;
  e.preventDefault();
  if ($("#pw-new").value !== $("#pw-again").value) {
    $("#pw-error").textContent = "The new passwords don't match";
    return;
  }
  try {
    await api("/api/password", { method: "POST", body: { current: $("#pw-current").value, new: $("#pw-new").value } });
    S.authRequired = true;
    $("#logout-btn").hidden = false;
    $("#password-dialog").close();
    toast("Password changed");
  } catch (err) {
    $("#pw-error").textContent = err.message;
  }
});
async function loadSources() {
  S.sources = await api("/api/sources");
  const ul = $("#source-list");
  ul.replaceChildren(...S.sources.map((s) => h(
    "li",
    {},
    s.error ? h("div", { class: "err", title: s.error }, `${s.name}: ${s.error}`) : h(
      "button",
      { type: "button", "aria-current": String(S.source === s.id), onclick: () => go(`#/b/${s.id}`) },
      icon(s.type, "kind"),
      h("span", {}, s.name),
      s.editable ? h("span", {
        class: "remove",
        role: "button",
        tabindex: "0",
        "aria-label": `Remove ${s.name}`,
        onclick: (e) => {
          e.stopPropagation();
          removeSource(s);
        }
      }, "×") : null
    )
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
    var _a;
    const btn = li.querySelector("button");
    if (btn) btn.setAttribute("aria-current", String(((_a = S.sources[i]) == null ? void 0 : _a.id) === sourceId));
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
  for (const e of S.entries) if (e.kind === "dir") {
    S.dirNames[e.id] = e.name;
    S.dirParent[e.id] = dirId;
  }
  S.currentDir = dirId;
  S.letter = "";
  $("#scan-all-btn").hidden = sourceId === "url";
  $("#filter-input").value = "";
  renderEntries();
}
function renderCrumbs(src, dirId) {
  const trail = [];
  for (let d = dirId; d; d = S.dirParent[d]) {
    trail.unshift(d);
    if (trail.length > 30) break;
  }
  const ol = $("#crumbs");
  ol.replaceChildren(
    h("li", {}, h("button", { type: "button", onclick: () => go(`#/b/${src.id || S.source}`) }, src.name)),
    ...trail.map((d) => h("li", {}, h("button", { type: "button", onclick: () => go(`#/b/${S.source}/${d}`) }, S.dirNames[d] || "…")))
  );
}
function showEmpty(title, body) {
  const empty = $("#browser-empty");
  empty.replaceChildren(h("h2", {}, title), h("p", {}, body));
  empty.hidden = false;
}
function renderEntries() {
  const q = $("#filter-input").value.trim().toLowerCase();
  const wanted = S.letter || "";
  const bar = $("#folder-letters");
  if (S.entries.length >= 15) {
    if (!S.letterBar) {
      S.letterBar = makeLetterBar((l) => {
        S.letter = l;
        renderEntries();
      });
      bar.replaceChildren(S.letterBar.el);
    }
    S.letterBar.set(new Set(S.entries.map((e) => letterOf(e.name))), wanted);
  } else {
    bar.replaceChildren();
    S.letterBar = null;
  }
  const items = S.entries.filter((e) => (!q || e.name.toLowerCase().includes(q)) && (!wanted || S.entries.length < 15 || letterOf(e.name) === wanted));
  Queue.set(items.filter((e) => e.kind !== "dir").map((e) => ({ src: e.source_id || S.source, item: e.id, title: e.name })));
  const list = $("#entries");
  list.replaceChildren(...items.map((e) => {
    var _a;
    const isDir = e.kind === "dir";
    const target = isDir ? `#/b/${S.source}/${e.id}` : `#/p/${e.source_id || S.source}/${e.id}`;
    return h(
      "li",
      { class: `entry ${e.kind}` },
      icon(isDir ? "dir" : e.kind),
      h("a", { class: "name", href: target, title: e.name }, e.name),
      h(
        "span",
        { class: "meta" },
        isDir ? "" : [(_a = e.meta) == null ? void 0 : _a.year, fmtSize(e.size)].filter(Boolean).join("  "),
        e.watched ? h("span", { class: "resume" }, "  ✓ Watched") : e.resume ? h("span", { class: "resume" }, `  Resume ${fmt(e.resume)}`) : null
      ),
      isDir ? h("span") : e.filtered ? h("span", { class: "badge", title: "Language filter is ready" }, icon("hush", ""), "Filter ready") : h("button", { class: "btn subtle scan-btn", type: "button", onclick: (ev) => scanFromList(ev, e) }, "Scan")
    );
  }));
  if (!items.length) {
    S.source === "url" ? showEmpty("No links yet", "Paste a link to a video or song in the box on the left and press Play.") : showEmpty(q ? "Nothing matches" : "This folder is empty", q ? "Try a shorter search." : "Hush shows folders, videos and music here. Other files are hidden.");
  } else $("#browser-empty").hidden = true;
}
$("#filter-input").addEventListener("input", renderEntries);
$("#scan-all-btn").addEventListener("click", async (ev) => {
  const btn = ev.currentTarget;
  if (!confirm("Scan every title in this folder, and the folders inside it, that hasn't been scanned yet? Scans run one after another in the background, so a big library takes a while.")) return;
  btn.disabled = true;
  try {
    const r = await api("/api/scan-folder", { method: "POST", body: { source_id: S.source, dir_id: S.currentDir || "" } });
    toast(r.queued ? `Queued ${plural(r.queued, "title")} to scan` : "Everything here is already scanned");
    Jobs.poll();
  } catch (err) {
    toast(err.message);
  }
  btn.disabled = false;
});
async function scanFromList(ev, e) {
  const btn = ev.currentTarget;
  btn.disabled = true;
  btn.textContent = "Queued";
  try {
    await api("/api/analyze", { method: "POST", body: { source_id: e.source_id || S.source, item_id: e.id, title: e.name } });
    toast(`Scanning ${e.name}`);
    Jobs.poll();
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Scan";
    toast(err.message);
  }
}
$("#url-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const r = await api("/api/open-url", { method: "POST", body: { url: $("#url-input").value.trim() } });
    $("#url-input").value = "";
    go(r.kind === "dir" ? `#/b/${r.source_id}/${r.item_id}` : `#/p/${r.source_id}/${r.item_id}`);
  } catch (err) {
    toast(err.message);
  }
});
const SOURCE_FIELDS = {
  smb: [
    ["server", "Server", "nas.local or 192.168.1.20"],
    ["share", "Share", "Movies"],
    ["path", "Folder inside the share (optional)", "Family/Films"],
    ["username", "User name", ""],
    ["password", "Password", "", "password"]
  ],
  local: [["path", "Folder path on the server", "/media/movies"]],
  dlna: [["location", "Server description URL", "http://192.168.1.20:8200/rootDesc.xml"]],
  jellyfin: [
    ["url", "Server address", "http://192.168.1.20:8096"],
    ["api_key", "API key", "Dashboard → API Keys", "password"],
    ["username", "User (optional)", "Leave blank for the first user"]
  ],
  plex: [["url", "Server address", "http://192.168.1.20:32400"], ["token", "Plex token", "", "password"]],
  http: [["url", "Web folder or link", "http://192.168.1.20:8080/movies/"]],
  ftp: [
    ["host", "Server", "192.168.1.20"],
    ["port", "Port (optional)", "21"],
    ["path", "Folder (optional)", "/movies"],
    ["username", "User name (blank for anonymous)", ""],
    ["password", "Password", "", "password"]
  ],
  sftp: [
    ["host", "Server", "192.168.1.20"],
    ["port", "Port (optional)", "22"],
    ["path", "Folder (optional)", "/home/me/movies"],
    ["username", "User name", ""],
    ["password", "Password", "", "password"]
  ]
};
const SOURCE_HINTS = {
  smb: "Works with Windows shares, Synology, QNAP and TrueNAS. Nothing needs to be mounted.",
  local: "Any folder the Hush server can read, including NAS shares mounted with NFS or CIFS.",
  plex: "To find your token, open any item in Plex Web, choose Get Info → View XML, and copy the X-Plex-Token value from the address.",
  ftp: "Plain FTP. Files play and scan like any other.",
  sftp: "Any server you can log in to over SSH. Password login; blank password uses the server's SSH keys.",
  http: "End a folder address with / to browse it. Works with nginx, Apache and Caddy file listings."
};
function renderSourceFields() {
  const type = $("#src-type").value;
  const box = $("#src-fields");
  box.replaceChildren(...SOURCE_FIELDS[type].map(([name, label, ph, kind]) => h("label", {}, label, h("input", {
    name,
    type: kind || "text",
    placeholder: ph,
    autocomplete: kind === "password" ? "new-password" : "off",
    required: !/optional/i.test(label) && name !== "username" && name !== "password"
  }))));
  if (SOURCE_HINTS[type]) box.prepend(h("p", { class: "hint" }, SOURCE_HINTS[type]));
  if (["smb", "ftp", "sftp", "jellyfin", "plex"].includes(type)) {
    const found = h("div", { class: "found" });
    box.append(h("button", { class: "btn subtle", type: "button", onclick: async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "Scanning…";
      try {
        const r = await api("/api/network/scan");
        const rows = r.servers.flatMap((s) => s.services.map((v) => ({ s, v })));
        found.replaceChildren(...rows.length ? rows.map(({ s, v }) => h(
          "button",
          { class: "btn ghost", type: "button", onclick: () => pickServer(s, v) },
          `${s.name || s.host} · ${s.host} · ${v.label}`
        )) : [h("p", { class: "hint" }, "Nothing answered. Check the server is on and on the same network, or type its address.")]);
      } catch (err) {
        found.replaceChildren(h("p", { class: "error" }, err.message));
      }
      btn.disabled = false;
      btn.textContent = "Find servers on my network";
    } }, "Find servers on my network"), found);
  }
  if (type === "dlna") {
    const found = h("div", { class: "found" });
    box.append(h("button", { class: "btn subtle", type: "button", onclick: async (e) => {
      e.currentTarget.textContent = "Looking…";
      try {
        const servers = await api("/api/dlna/discover");
        found.replaceChildren(...servers.length ? servers.map((s) => h("button", { class: "btn ghost", type: "button", onclick: () => {
          $("#source-form [name=location]").value = s.location;
          const n = $("#source-form [name=name]");
          if (!n.value) n.value = s.name;
        } }, s.name)) : [h("p", { class: "hint" }, "No servers answered. Check that the server is on and on the same network, or paste its address.")]);
      } catch (err) {
        found.replaceChildren(h("p", { class: "error" }, err.message));
      }
      e.currentTarget.textContent = "Find servers on my network";
    } }, "Find servers on my network"), found);
  }
}
function pickServer(s, v) {
  const sel = $("#src-type");
  if (sel.value !== v.type) {
    sel.value = v.type;
    renderSourceFields();
  }
  const set = (n, val) => {
    const el = $(`#source-form [name=${n}]`);
    if (el && !el.value) el.value = val;
  };
  set("name", s.name || s.host);
  if (v.type === "smb") set("server", s.host);
  else if (v.type === "ftp" || v.type === "sftp") set("host", s.host);
  else set("url", `http://${s.host}:${v.port}`);
}
$("#src-type").addEventListener("change", renderSourceFields);
$("#add-source-btn").addEventListener("click", () => {
  $("#source-form").reset();
  $("#src-error").textContent = "";
  renderSourceFields();
  $("#source-dialog").showModal();
});
$("#source-form").addEventListener("submit", async (e) => {
  var _a;
  if (((_a = e.submitter) == null ? void 0 : _a.value) !== "save") return;
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  for (const k of Object.keys(data)) if (data[k] === "") delete data[k];
  if (data.type === "http") {
    data.urls = [{ name: data.name, url: data.url }];
    delete data.url;
  }
  try {
    const src = await api("/api/sources", { method: "POST", body: data });
    $("#source-dialog").close();
    await loadSources();
    go(`#/b/${src.id}`);
  } catch (err) {
    $("#src-error").textContent = err.message;
  }
});
const Jobs = {
  timer: null,
  list: [],
  paused: false,
  async act(path) {
    try {
      await api(path, { method: "POST" });
    } catch (err) {
      toast(err.message);
    }
    this.poll();
  },
  async poll() {
    clearTimeout(this.timer);
    try {
      [this.list, { paused: this.paused }] = await Promise.all([api("/api/jobs"), api("/api/jobs/state")]);
    } catch (e) {
      return;
    }
    const running = this.list.filter((j) => j.status === "running" || j.status === "queued");
    $("#jobs-dot").hidden = !running.length;
    $("#jobs-label").textContent = running.length ? this.paused ? `Paused ${running.length}` : `Scanning ${running.length}` : "Scans";
    if ($("#jobs-dialog").open) this.render();
    Player.onJobs(this.list);
    if (running.length || $("#jobs-dialog").open) this.timer = setTimeout(() => this.poll(), 2500);
  },
  render() {
    const ul = $("#jobs-list");
    const active = this.list.some((j) => j.status === "running" || j.status === "queued");
    const failed = this.list.some((j) => j.status === "error" || j.status === "cancelled");
    $("#jobs-tools").replaceChildren(...[
      h(
        "button",
        { class: "btn subtle", type: "button", onclick: () => this.act(this.paused ? "/api/jobs/resume" : "/api/jobs/pause") },
        this.paused ? "Resume scans" : "Pause scans"
      ),
      active && h("button", { class: "btn ghost", type: "button", onclick: () => confirm("Stop the running scan and clear the waiting ones?") && this.act("/api/jobs/stop-all") }, "Stop all"),
      failed && h("button", { class: "btn ghost", type: "button", onclick: () => this.act("/api/jobs/retry-failed") }, "Retry failed")
    ].filter(Boolean));
    $("#jobs-note").textContent = this.paused ? "Paused. A scan that is already running will finish, then nothing new starts." : "";
    if (!this.list.length) {
      ul.replaceChildren(h("li", {}, h("span", { class: "stage" }, "Nothing has been scanned yet. Open a title and choose Scan to build its filter.")));
      return;
    }
    ul.replaceChildren(...this.list.map((j) => h(
      "li",
      {},
      h("span", { class: "job-title" }, j.title || "Untitled"),
      h(
        "span",
        { class: "job-action" },
        j.status === "queued" ? h("button", { class: "btn ghost", type: "button", title: "Move this title to the front of the queue", onclick: () => this.act(`/api/jobs/${j.id}/next`) }, "Scan next") : null,
        j.status === "running" || j.status === "queued" ? h("button", { class: "btn ghost", type: "button", onclick: async () => {
          await api(`/api/jobs/${j.id}/cancel`, { method: "POST" });
          this.poll();
        } }, "Cancel") : h("button", { class: "btn ghost", type: "button", onclick: () => this.act(`/api/jobs/${j.id}/restart`) }, "Restart")
      ),
      h("span", { class: `stage ${j.status === "error" ? "error" : ""}` }, jobText(j)),
      j.status === "running" ? h("div", { class: "progress" }, h("i", { style: `width:${Math.round(j.progress * 100)}%` })) : null
    )));
  }
};
function jobText(j) {
  if (j.status === "error") return `Couldn't finish: ${j.error || "unknown error"}`;
  if (j.status === "done") return `Done, ${j.stage}`;
  if (j.status === "cancelled") return "Cancelled";
  if (j.status === "queued") return "Waiting to start";
  return `${j.stage[0].toUpperCase()}${j.stage.slice(1)}, ${Math.round(j.progress * 100)}%`;
}
const WeatherCard = {
  loc: null,
  async load() {
    let w;
    try {
      w = await api("/api/weather");
    } catch (e) {
      return;
    }
    this.loc = w.configured ? w : null;
    $("#weather-info").textContent = w.configured ? w.unavailable ? `${w.place} (the weather service is not answering)` : `${w.place}: ${w.temp}${w.unit}, ${w.text.toLowerCase()}` : "Not set. Pick your town to show the weather while a channel opens.";
    if (w.configured) $("#weather-unit").value = w.unit === "°F" ? "f" : "c";
  },
  async save(place) {
    try {
      await api("/api/weather/location", { method: "PUT", body: place });
      toast(place.name ? "Weather location saved" : "Weather removed");
      $("#weather-results").replaceChildren();
      WaitScreen.weather = null;
      this.load();
    } catch (err) {
      toast(err.message);
    }
  }
};
$("#weather-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#weather-q").value.trim(), box = $("#weather-results");
  if (q.length < 2) return;
  try {
    const rs = await api(`/api/weather/search?q=${encodeURIComponent(q)}`);
    box.replaceChildren(...rs.length ? rs.map((r) => h(
      "div",
      { class: "found-row" },
      h("div", {}, h("strong", {}, r.name), h("div", { class: "hint" }, [r.region, r.country].filter(Boolean).join(", "))),
      h("button", { class: "btn subtle", type: "button", onclick: () => WeatherCard.save({ name: [r.name, r.region].filter(Boolean).join(", "), lat: r.lat, lon: r.lon, unit: $("#weather-unit").value }) }, "Use this")
    )) : [h("p", { class: "hint" }, "Nothing found")]);
  } catch (err) {
    box.replaceChildren(h("p", { class: "error" }, err.message));
  }
});
$("#weather-clear").addEventListener("click", () => WeatherCard.save({}));
$("#weather-unit").addEventListener("change", () => {
  const l = WeatherCard.loc;
  if (l) WeatherCard.save({ name: l.place, lat: l.lat, lon: l.lon, unit: $("#weather-unit").value });
});
const Refresh = {
  async start() {
    try {
      const r = await api("/api/library/refresh", { method: "POST" });
      toast(r.started ? "Looking for new titles…" : "A refresh is already running");
    } catch (err) {
      toast(err.message);
      return;
    }
    this.follow();
  },
  follow() {
    const set = (busy) => ["#refresh-btn", "#refresh-btn2"].forEach((id) => {
      const b = $(id);
      b.disabled = busy;
      b.textContent = busy ? "Refreshing…" : id === "#refresh-btn" ? "↻ Refresh" : "Refresh now";
    });
    set(true);
    const poll = async () => {
      try {
        const s = await api("/api/library/refresh");
        if (s.running) {
          setTimeout(poll, 3e3);
          return;
        }
        set(false);
        toast(s.result || "Library is up to date");
        Catalog.version = null;
        const [view, id] = location.hash.replace(/^#\/?/, "").split("/");
        if (["home", "movies", "shows", "show", "title", "live", "folders"].includes(view)) Catalog.open(view, id, { quiet: true });
      } catch (e) {
        set(false);
      }
    };
    setTimeout(poll, 2e3);
  }
};
["#refresh-btn", "#refresh-btn2"].forEach((id) => $(id).addEventListener("click", () => Refresh.start()));
$("#app-update-btn").addEventListener("click", () => {
  var _a;
  return (_a = window.HushApp) == null ? void 0 : _a.checkForUpdate();
});
$("#app-server-btn").addEventListener("click", () => {
  var _a;
  return (_a = window.HushApp) == null ? void 0 : _a.changeServer();
});
$("#pl-settings-btn").addEventListener("click", () => {
  Catalog.liveState = { q: "", group: "", favorites: false, hideDead: true, letter: "", ...Catalog.liveState || {}, panel: true };
  go("#/live");
});
$("#jobs-btn").addEventListener("click", () => {
  $("#jobs-dialog").showModal();
  Jobs.render();
  Jobs.poll();
});
$$("[data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
const autoplay = () => store.get("autoplay", true);
const LETTERS = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZ", ..."1234567890"];
const letterOf = (name, skipArticles = false) => {
  let t = (name || "").trim();
  if (skipArticles) {
    const m = /^(the|an|a)\s+\S/i.exec(t);
    if (m) t = t.slice(m[1].length).trim();
  }
  for (const ch of t) {
    if (/[0-9]/.test(ch)) return ch;
    const base = ch.normalize("NFKD")[0].toUpperCase();
    if (base >= "A" && base <= "Z") return base;
    if (/[\p{L}\p{N}]/u.test(ch)) return "*";
  }
  return "*";
};
const sortKey = (name) => (name || "").trim().replace(/^(the|an|a)\s+(?=\S)/i, "").toLowerCase();
function makeLetterBar(onPick) {
  const el = h("div", { class: "letters", role: "group", "aria-label": "Jump to a letter" });
  let current = "", available = /* @__PURE__ */ new Set();
  const draw = () => el.replaceChildren(...[
    h("button", { type: "button", class: "lt", "aria-pressed": String(current === ""), onclick: () => pick("") }, "All"),
    ...LETTERS.map((l) => h("button", {
      type: "button",
      class: "lt",
      "aria-pressed": String(current === l),
      disabled: !available.has(l) && current !== l,
      onclick: () => pick(current === l ? "" : l)
    }, l)),
    available.has("*") ? h("button", {
      type: "button",
      class: "lt",
      title: "Other alphabets and symbols",
      "aria-pressed": String(current === "*"),
      onclick: () => pick(current === "*" ? "" : "*")
    }, "…") : null
  ].filter(Boolean));
  const pick = (l) => {
    current = l;
    draw();
    onPick(l);
  };
  return { el, set(avail, cur) {
    available = avail;
    current = cur;
    draw();
  }, get current() {
    return current;
  } };
}
const pk = (k) => {
  var _a;
  return `${((_a = S.profile) == null ? void 0 : _a.id) || ""}.${k}`;
};
const isKids = () => {
  var _a;
  return !!((_a = S.profile) == null ? void 0 : _a.kids);
};
const initialOf = (name) => {
  var _a;
  return ((_a = (name || "?").trim()[0]) == null ? void 0 : _a.toUpperCase()) || "?";
};
function fillAvatar(el, p) {
  el.style.background = (p == null ? void 0 : p.color) || "";
  const svg = (p == null ? void 0 : p.avatar) && window.AVATAR_SVG ? window.AVATAR_SVG[p.avatar] : "";
  if (svg) el.innerHTML = svg;
  else el.textContent = initialOf(p == null ? void 0 : p.name);
  return el;
}
const avatarEl = (p, cls = "avatar") => fillAvatar(h("span", { class: cls }), p);
const RATING_NAMES = { 0: "G", 1: "PG", 2: "PG-13" };
const kidsSummary = (s = {}) => [
  (s.block || []).includes("mild") || !s.block ? "No flagged language" : "Mild language allowed",
  `up to ${RATING_NAMES[s.max_cert] || "any rating"}`,
  s.allow_live ? "Live TV on" : "no Live TV"
].join(" · ");
const Profiles = {
  data: null,
  async load() {
    this.data = await api("/api/profiles");
    S.profile = this.data.current;
    return this.data;
  },
  /** Make the app match the chosen profile: kids see no admin tools and always get the filter. */
  apply() {
    var _a, _b, _c;
    const p = S.profile, kids = isKids();
    document.documentElement.classList.toggle("kids", kids);
    fillAvatar($("#profile-avatar"), p);
    $("#profile-name").textContent = (p == null ? void 0 : p.name) || "";
    $("#profile-btn").hidden = (((_a = this.data) == null ? void 0 : _a.profiles.length) || 1) < 2 && !((_b = this.data) == null ? void 0 : _b.can_manage);
    const live = !kids || !!((_c = p == null ? void 0 : p.settings) == null ? void 0 : _c.allow_live);
    $$(".live-link").forEach((el) => {
      el.hidden = !live;
    });
    Player.filterOn = kids ? true : store.get(pk("filterOn"), true);
    Player.bleep = !kids && store.get(pk("mode"), "mute") === "bleep";
    $("#mode-select").value = Player.bleep ? "bleep" : "mute";
  },
  /** The full-screen picker. ``forced`` = nobody has chosen yet, so there is no way to cancel. */
  show(forced = false) {
    const d = this.data, box = $("#profile-tiles");
    $("#profile-pass").hidden = true;
    $("#profile-pass-error").textContent = "";
    box.replaceChildren(...d.profiles.map((p) => h(
      "button",
      { class: "tile", type: "button", onclick: () => this.choose(p) },
      avatarEl(p, "face"),
      h("span", { class: "nm" }, p.name),
      p.kids ? h("span", { class: "kid" }, "Kids") : null
    )));
    $("#profiles-manage").hidden = !d.can_manage || forced;
    $("#profiles-cancel").hidden = forced;
    $("#profile-picker").hidden = false;
    document.body.style.overflow = "hidden";
    setTimeout(() => {
      var _a;
      return (_a = box.querySelector(".tile")) == null ? void 0 : _a.focus();
    }, 50);
  },
  hide() {
    $("#profile-picker").hidden = true;
    document.body.style.overflow = "";
  },
  async choose(p, password) {
    try {
      await api("/api/profiles/select", { method: "POST", body: { id: p.id, password } });
    } catch (err) {
      if (err.status === 403 && this.data.lock) {
        $("#profile-pass-text").textContent = `Enter the Hush password to switch to ${p.name}.`;
        $("#profile-pass").hidden = false;
        $("#profile-pass-input").value = "";
        $("#profile-pass-input").focus();
        this.pending = p;
        return;
      }
      toast(err.message);
      return;
    }
    location.hash = "#/home";
    location.reload();
  }
};
$("#profile-btn").addEventListener("click", async () => {
  await Profiles.load();
  Profiles.show(false);
});
$("#profiles-cancel").addEventListener("click", () => Profiles.hide());
$("#profiles-manage").addEventListener("click", () => {
  Profiles.hide();
  go("#/profiles");
});
$("#profile-pass").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/profiles/select", { method: "POST", body: { id: Profiles.pending.id, password: $("#profile-pass-input").value } });
    location.hash = "#/home";
    location.reload();
  } catch (err) {
    $("#profile-pass-error").textContent = err.message;
  }
});
$("#profile-pass-cancel").addEventListener("click", () => {
  $("#profile-pass").hidden = true;
});
const Progress = {
  timer: null,
  last: -1,
  armed: false,
  arm() {
    this.armed = true;
    this.last = -1;
    clearInterval(this.timer);
    this.timer = setInterval(() => {
      if (!video.paused) this.save();
    }, 1e4);
  },
  disarm() {
    this.armed = false;
    clearInterval(this.timer);
  },
  /** Send the position. A title that is nearly over is recorded as watched by the server. */
  save(force = false, finished = false) {
    const P = Player;
    if (!this.armed || !P.info || P.info.live || !P.duration) return;
    const pos = finished ? P.duration : P.now();
    if (!force && Math.abs(pos - this.last) < 5) return;
    this.last = pos;
    fetch(`/api/progress/${P.info.media_key}`, {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: P.src, item_id: P.item, title: P.info.title, position: pos, duration: P.duration })
    }).catch(() => {
    });
  }
};
window.addEventListener("pagehide", () => Progress.save(true));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") Progress.save(true);
});
const guide = {
  feed: null,
  observer: null,
  /** Every channel, in pages as you scroll. Starts from the filters the Live TV page had. */
  newFeed() {
    const st = Catalog.liveState || {};
    this.feed = { q: st.q || "", group: st.group || "", favorites: !!st.favorites, items: [], total: 0, loading: false, done: false };
    $("#guide-q").value = this.feed.q;
    $("#guide-fav").setAttribute("aria-pressed", String(this.feed.favorites));
    $("#guide-fav").textContent = this.feed.favorites ? "★ Favorites only" : "☆ Favorites";
  },
  async more() {
    const f = this.feed;
    if (!f || f.loading || f.done) return false;
    f.loading = true;
    try {
      const q = new URLSearchParams({ q: f.q, group: f.group, favorites: f.favorites, hide_dead: true, limit: 240, offset: f.items.length });
      const r = await api(`/api/live/channels?${q}`);
      if (f !== this.feed) return false;
      const first = f.items.length;
      f.items.push(...r.channels);
      f.total = r.total;
      f.done = f.items.length >= r.total || !r.channels.length;
      this.append(first);
      return !!r.channels.length;
    } catch (e) {
      return false;
    } finally {
      f.loading = false;
    }
  },
  append(from) {
    var _a;
    const list = $("#guide-list");
    (_a = list.querySelector(".sentinel")) == null ? void 0 : _a.remove();
    list.append(...this.feed.items.slice(from).map((c, k) => {
      const i = from + k;
      return h("li", {}, h(
        "button",
        { type: "button", "data-key": c.key, "aria-current": String(c.key === Player.chan), onclick: () => this.pick(i) },
        h("span", { class: "n" }, i + 1),
        h("span", {}, splitTags(c.name).title)
      ));
    }));
    if (!this.feed.done) list.append(h("li", { class: "sentinel" }, ""));
    this.watch();
    $("#guide-count").textContent = `${plural(this.feed.total, "channel")}`;
  },
  watch() {
    var _a;
    (_a = this.observer) == null ? void 0 : _a.disconnect();
    const s = $("#guide-list .sentinel");
    if (!s) return;
    this.observer = new IntersectionObserver((e) => {
      if (e[0].isIntersecting) this.more();
    }, { root: $("#guide-list") });
    this.observer.observe(s);
  },
  async reload() {
    this.newFeedKeep();
    $("#guide-list").replaceChildren();
    await this.more();
  },
  newFeedKeep() {
    this.feed = {
      q: $("#guide-q").value.trim(),
      group: $("#guide-group").value,
      favorites: $("#guide-fav").getAttribute("aria-pressed") === "true",
      items: [],
      total: 0,
      loading: false,
      done: false
    };
  },
  /** Play this channel; from now on up/down and the number keys move through THIS list. */
  pick(i) {
    const c = this.feed.items[i];
    if (!c) return;
    Queue.set(this.feed.items.map((x) => ({ src: "url", item: x.item_id, title: x.name, chan: x.key, logo: x.logo_url, groups: x.groups })));
    const feed = this.feed;
    Queue.loadMore = async () => feed === this.feed ? this.more() : false;
    if (c.key !== Player.chan) {
      Queue.history.push(Queue.pos);
      Queue.go(i);
    }
  },
  async open() {
    var _a;
    if (!Player.chan) return;
    if (!$("#panel").hidden) togglePanel(false);
    $("#guide").hidden = false;
    $("#guide-btn").setAttribute("aria-expanded", "true");
    if (!$("#guide-group").dataset.ready) {
      $("#guide-group").dataset.ready = "1";
      try {
        for (const g of await api("/api/live/groups")) $("#guide-group").append(h("option", { value: g.name }, `${g.name} (${g.count})`));
      } catch (e) {
      }
    }
    this.newFeed();
    $("#guide-group").value = this.feed.group;
    $("#guide-list").replaceChildren();
    await this.more();
    for (let n = 0; n < 3 && !$(`#guide-list [data-key="${Player.chan}"]`) && !this.feed.done; n++) await this.more();
    (_a = $(`#guide-list [data-key="${Player.chan}"]`)) == null ? void 0 : _a.scrollIntoView({ block: "center" });
    $("#guide-q").focus({ preventScroll: true });
  },
  close() {
    var _a;
    $("#guide").hidden = true;
    $("#guide-btn").setAttribute("aria-expanded", "false");
    (_a = this.observer) == null ? void 0 : _a.disconnect();
  },
  toggle() {
    $("#guide").hidden ? this.open() : this.close();
  }
};
let guideTimer;
$("#guide-q").addEventListener("input", () => {
  clearTimeout(guideTimer);
  guideTimer = setTimeout(() => guide.reload(), 300);
});
$("#guide-group").addEventListener("change", () => guide.reload());
$("#guide-fav").addEventListener("click", (e) => {
  const on = e.currentTarget.getAttribute("aria-pressed") !== "true";
  e.currentTarget.setAttribute("aria-pressed", String(on));
  e.currentTarget.textContent = on ? "★ Favorites only" : "☆ Favorites";
  guide.reload();
});
$("#guide-btn").addEventListener("click", () => guide.toggle());
$("#guide-close").addEventListener("click", () => guide.close());
const Queue = {
  list: [],
  pos: -1,
  history: [],
  played: /* @__PURE__ */ new Set(),
  pending: false,
  shuffle: store.get("shuffle", false),
  repeat: store.get("repeat", "off"),
  // off | all | one
  /** Remember the titles of the list the person is looking at: they become the play queue. */
  set(items) {
    this.list = items;
  },
  sync(src, item) {
    var _a;
    const i = this.list.findIndex((x) => x.src === src && x.item === item);
    if (i < 0) this.list = [{ src, item, title: "" }];
    this.pos = i < 0 ? 0 : i;
    const key = ((_a = this.list[this.pos]) == null ? void 0 : _a.chan) || null;
    if (key && key !== this.curKey) this.lastKey = this.curKey;
    if (key) this.curKey = key;
    if (this.pending) this.pending = false;
    else {
      this.history = [];
      this.played = /* @__PURE__ */ new Set([this.pos]);
    }
    this.ui();
  },
  go(i) {
    const t = this.list[i];
    if (!t) return;
    this.pending = true;
    this.pos = i;
    if (Player.mini) {
      Player.open(t.src, t.item, { mini: true });
      return;
    }
    const hash = `#/p/${t.src}/${t.item}`;
    if (location.hash.startsWith("#/p/") && location.hash !== hash) {
      location.replace(location.href.split("#")[0] + hash);
    } else location.hash = hash;
  },
  /** Which index plays next, or null when the queue is over. */
  upNext() {
    const n = this.list.length;
    if (this.shuffle && n > 1) {
      let left = [...Array(n).keys()].filter((i) => !this.played.has(i));
      if (!left.length) {
        if (this.repeat !== "all") return null;
        this.played = /* @__PURE__ */ new Set([this.pos]);
        left = [...Array(n).keys()].filter((i) => i !== this.pos);
      }
      return left[Math.floor(Math.random() * left.length)];
    }
    if (this.pos + 1 < n) return this.pos + 1;
    return this.repeat === "all" && n > 1 ? 0 : null;
  },
  next(auto = false) {
    if (auto && this.repeat === "one") {
      video.currentTime = 0;
      video.play().catch(() => {
      });
      return;
    }
    const i = this.upNext();
    if (i == null) {
      if (!auto) toast("That was the last one");
      $("#player").classList.remove("playing");
      return;
    }
    this.history.push(this.pos);
    this.played.add(i);
    this.go(i);
  },
  prev() {
    if (Player.chan) {
      this.zap(-1);
      return;
    }
    if ((video.currentTime || 0) > 3 || !this.history.length && this.pos <= 0 && this.repeat !== "all") {
      Player.seek(0);
      return;
    }
    const i = this.history.length ? this.history.pop() : this.pos > 0 ? this.pos - 1 : this.list.length - 1;
    this.go(i);
  },
  /* ---------- Live TV, like a remote: channel up/down, number keys, last channel ---------- */
  curKey: null,
  lastKey: null,
  loadMore: null,
  digits: "",
  digitTimer: null,
  bannerTimer: null,
  epg: {},
  /** "Now: … · Next: …" for a channel, when the programme guide knows it (kept for a minute). */
  async guideLine(key) {
    let e = this.epg[key];
    if (!e || Date.now() - e.at > 6e4) {
      try {
        e = this.epg[key] = { at: Date.now(), data: (await api(`/api/live/epg?keys=${key}`))[key] || {} };
      } catch (e2) {
        return "";
      }
    }
    const { now, next } = e.data;
    return now ? `Now: ${now.title} (until ${hm(now.stop)})${next ? ` · Next: ${next.title}` : ""}` : "";
  },
  /** Get the neighbouring channels ready, so channel up/down starts quickly. */
  warm() {
    const items = [this.pos + 1, this.pos - 1].map((i) => this.list[i]).filter((c) => c == null ? void 0 : c.chan).map((c) => ({ src: c.src, item: c.item }));
    if (items.length) api("/api/live/warm", { method: "POST", body: { items } }).catch(() => {
    });
  },
  banner(at = this.pos) {
    const c = this.list[at];
    if (!(c == null ? void 0 : c.chan)) return;
    $("#cb-num").textContent = at + 1;
    $("#cb-name").textContent = splitTags(c.title).title;
    $("#cb-sub").textContent = [...splitTags(c.title).tags, ...(c.groups || []).slice(0, 2)].join(" · ");
    const logo = $("#cb-logo");
    logo.hidden = !c.logo;
    if (c.logo) logo.src = c.logo;
    this.guideLine(c.chan).then((line) => {
      var _a;
      if (line && ((_a = this.list[at]) == null ? void 0 : _a.chan) === c.chan) $("#cb-sub").textContent = line;
    });
    const b = $("#chan-banner");
    b.hidden = false;
    clearTimeout(this.bannerTimer);
    this.bannerTimer = setTimeout(() => {
      b.hidden = true;
    }, 4500);
  },
  /** Go to the channel at this position, loading more of the list first if it is further down. */
  async jumpTo(i) {
    while (i >= this.list.length && this.loadMore && await this.loadMore()) {
    }
    if (i >= 0 && i < this.list.length) {
      this.history.push(this.pos);
      this.go(i);
    } else toast(`There is no channel ${i + 1}`);
  },
  async zap(dir) {
    var _a;
    const n = this.list.length;
    if (n < 2) return;
    let i = ((_a = this.zapTo) != null ? _a : this.pos) + dir;
    if (i < 0) i = this.list.length - 1;
    else if (i >= this.list.length && !(this.loadMore && await this.loadMore())) i = 0;
    this.zapTo = i;
    this.banner(i);
    clearTimeout(this.zapTimer);
    this.zapTimer = setTimeout(() => {
      const t = this.zapTo;
      this.zapTo = null;
      this.history.push(this.pos);
      this.go(t);
    }, 280);
  },
  recall() {
    const i = this.list.findIndex((x) => x.chan && x.chan === this.lastKey);
    if (i < 0) {
      toast("No earlier channel yet");
      return;
    }
    this.go(i);
  },
  digit(d) {
    this.digits = (this.digits + d).slice(-4);
    const box = $("#chan-entry");
    box.textContent = this.digits;
    box.hidden = false;
    clearTimeout(this.digitTimer);
    this.digitTimer = setTimeout(() => {
      const n = Number(this.digits);
      this.digits = "";
      box.hidden = true;
      if (n > 0) this.jumpTo(n - 1);
    }, 1400);
  },
  toggleShuffle() {
    this.shuffle = !this.shuffle;
    store.set("shuffle", this.shuffle);
    this.played = /* @__PURE__ */ new Set([this.pos]);
    this.ui();
    toast(this.shuffle ? "Shuffle on" : "Shuffle off");
  },
  cycleRepeat() {
    this.repeat = { off: "all", all: "one", one: "off" }[this.repeat];
    store.set("repeat", this.repeat);
    this.ui();
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
    r.dataset.repeat = this.repeat;
    r.setAttribute("aria-pressed", String(this.repeat !== "off"));
    r.setAttribute("aria-label", label);
    r.title = label;
  }
};
$("#prev-btn").addEventListener("click", () => Queue.prev());
$("#next-btn").addEventListener("click", () => Queue.next());
$("#shuffle-btn").addEventListener("click", () => Queue.toggleShuffle());
$("#repeat-btn").addEventListener("click", () => Queue.cycleRepeat());
const initials = (t) => {
  const words = (t || "").replace(/[\[(][^\])]*[\])]/g, " ").split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  return (words.length > 1 ? words.slice(0, 2).map((w) => w[0]).join("") : (words[0] || "?").slice(0, 2)).toUpperCase();
};
const splitTags = (name) => {
  const tags = [...(name || "").matchAll(/[\[(]([^\])]*)[\])]/g)].map((m) => m[1].trim()).filter(Boolean);
  return { title: (name || "").replace(/\s*[\[(][^\])]*[\])]/g, "").trim() || name, tags };
};
const mins = (n) => n ? `${Math.floor(n / 60) ? Math.floor(n / 60) + " h " : ""}${n % 60} min` : "";
const artBox = (url, label, cls = "art") => h("div", { class: cls }, url ? h("img", { src: url, alt: "", loading: "lazy" }) : h("div", { class: "noart" }, initials(label)));
const Catalog = {
  box: () => $("#catalog-view"),
  /** A show or movie's background picture, faded in behind the top of the page. Cleared on every other page. */
  backdrop(url) {
    const b = this.box();
    b.classList.toggle("has-fanart", !!url);
    if (url) b.style.setProperty("--fanart", `url("${url}")`);
    else b.style.removeProperty("--fanart");
  },
  async open(view, id, opts = {}) {
    if (view !== "live") Queue.loadMore = null;
    if (!opts.quiet || !["show", "title"].includes(view)) this.backdrop(null);
    $$("#rail-links a").forEach((a) => a.setAttribute("aria-current", String(
      a.hash === `#/${view}` || view === "show" && a.hash === "#/shows" || view === "title" && a.hash === (this.cameFrom || "#/movies")
    )));
    const scroll = window.scrollY;
    if (!opts.quiet) this.box().replaceChildren(h("p", { class: "hint" }, "Loading…"));
    try {
      if (view === "profiles") await this.profilesPage();
      else if (view === "home") await this.home();
      else if (view === "folders") await this.folders();
      else if (view === "live") await this.live();
      else if (view === "mylist") await this.mylist();
      else if (view === "downloads") await this.downloads();
      else if (view === "movies") await this.grid("movies");
      else if (view === "shows") await this.grid("shows");
      else if (view === "show") await this.show(id);
      else await this.title(id);
    } catch (err) {
      if (!opts.quiet) this.box().replaceChildren(h("p", { class: "error" }, err.message));
    }
    if (opts.quiet) window.scrollTo(0, scroll);
  },
  /** The library follows the server: when a scan, refresh or rename changes it, the open page redraws itself. */
  version: null,
  watching: false,
  watch() {
    if (this.watching) return;
    this.watching = true;
    const check = async () => {
      if (document.hidden || $("#app").hidden) return;
      let v;
      try {
        v = (await api("/api/library/version")).version;
      } catch (e) {
        return;
      }
      if (this.version === null) {
        this.version = v;
        return;
      }
      if (v === this.version) return;
      if (!this.idle()) return;
      this.version = v;
      const [view, id] = location.hash.replace(/^#\/?/, "").split("/");
      if (["home", "movies", "shows", "show", "title", "live", "folders", "mylist"].includes(view)) this.open(view, id, { quiet: true });
    };
    setInterval(check, 15e3);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) check();
    });
  },
  idle() {
    var _a, _b;
    if (document.querySelector("dialog[open]") || $("#library").hidden || !$("#player").hidden && !Player.mini) return false;
    return !((_b = (_a = document.activeElement) == null ? void 0 : _a.matches) == null ? void 0 : _b.call(_a, "input, textarea, select"));
  },
  /** Downloads: a window onto your qBittorrent (its downloads and its RSS downloader). */
  async downloads() {
    document.title = "Downloads – Hush";
    clearInterval(this.dlTimer);
    const speed = (b) => b ? `${fmtSize(b)}/s` : "";
    const eta = (s) => s > 0 && s < 864e4 ? s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round(s % 3600 / 60)} min` : `${Math.max(1, Math.round(s / 60))} min` : "";
    const stateText = (t) => t.done ? t.paused ? "Finished" : "Finished · sharing" : t.paused ? "Paused" : { downloading: "Downloading", stalledDL: "Waiting for sources", metaDL: "Getting details", queuedDL: "Queued", checkingDL: "Checking", error: "Error", missingFiles: "Files missing" }[t.state] || t.state;
    const addWrap = h("div", { class: "dl-add" });
    const listBox = h("div", { class: "dl-list" }), rssBox = h("div", { class: "dl-rss" }), conn = h("div", { class: "dl-conn" });
    const act = async (hash, action) => {
      try {
        await api(`/api/qbit/torrents/${hash}/${action}`, { method: "POST" });
        refreshList();
      } catch (err) {
        toast(err.message);
      }
    };
    const form = () => {
      var _a, _b, _c;
      const url = h("input", { type: "text", placeholder: "http://192.168.100.50:8080", "aria-label": "qBittorrent address", spellcheck: "false", value: ((_a = this.qbPublic) == null ? void 0 : _a.url) || "" });
      const user = h("input", { type: "text", placeholder: "User name", "aria-label": "qBittorrent user name", autocomplete: "off", value: ((_b = this.qbPublic) == null ? void 0 : _b.username) || "" });
      const pass = h("input", { type: "password", placeholder: ((_c = this.qbPublic) == null ? void 0 : _c.has_password) ? "Password (saved)" : "Password", "aria-label": "qBittorrent password", autocomplete: "off" });
      return h("form", { class: "row", onsubmit: async (e) => {
        e.preventDefault();
        try {
          await api("/api/qbit/settings", { method: "PUT", body: { url: url.value, username: user.value, password: pass.value } });
          toast("Saved");
          this.open("downloads", null, { quiet: true });
        } catch (err) {
          toast(err.message);
        }
      } }, url, user, pass, h("button", { class: "btn primary", type: "submit" }, "Save and connect"));
    };
    let cats = { categories: [], default_path: "" };
    const dest = store.get("qbit_dest", { kind: "", value: "" });
    const destBody = () => dest.kind === "category" && dest.value ? { category: dest.value } : dest.kind === "path" && dest.value.trim() ? { save_path: dest.value.trim() } : {};
    const destBox = () => {
      const pathIn = h("input", {
        type: "text",
        placeholder: cats.default_path ? `Folder on the qBittorrent machine, e.g. ${cats.default_path}` : "Folder on the qBittorrent machine",
        "aria-label": "Download folder",
        value: dest.kind === "path" ? dest.value : "",
        spellcheck: "false",
        oninput: (e) => {
          dest.value = e.target.value;
          store.set("qbit_dest", dest);
        }
      });
      pathIn.hidden = dest.kind !== "path";
      const sel = h(
        "select",
        { "aria-label": "Save new downloads to", onchange: (e) => {
          const v = e.target.value;
          if (v.startsWith("c:")) {
            dest.kind = "category";
            dest.value = v.slice(2);
          } else if (v === "path") {
            dest.kind = "path";
            dest.value = pathIn.value;
          } else {
            dest.kind = "";
            dest.value = "";
          }
          pathIn.hidden = dest.kind !== "path";
          store.set("qbit_dest", dest);
        } },
        h("option", { value: "" }, `qBittorrent decides${cats.default_path ? ` (${cats.default_path})` : ""}`),
        ...cats.categories.map((c) => h("option", { value: `c:${c.name}`, selected: dest.kind === "category" && dest.value === c.name }, `Category: ${c.name}${c.save_path ? ` → ${c.save_path}` : ""}`)),
        h("option", { value: "path", selected: dest.kind === "path" }, "A folder I choose…")
      );
      return h("div", { class: "row" }, h("label", { class: "hint", style: "align-self:center" }, "Save to"), sel, pathIn);
    };
    const addBox = () => {
      const link = h("input", { type: "text", placeholder: "Paste a magnet link or .torrent address", "aria-label": "Link to add to qBittorrent", spellcheck: "false", autocomplete: "off" });
      return h("form", { class: "row", onsubmit: async (e) => {
        e.preventDefault();
        const b = e.submitter;
        b.disabled = true;
        try {
          await api("/api/qbit/add", { method: "POST", body: { url: link.value, ...destBody() } });
          toast("Sent to qBittorrent");
          link.value = "";
          refreshList();
        } catch (err) {
          toast(err.message);
        }
        b.disabled = false;
      } }, link, h("button", { class: "btn primary", type: "submit" }, "Add to qBittorrent"));
    };
    const refreshList = async () => {
      let s;
      try {
        s = await api("/api/qbit");
      } catch (err) {
        listBox.replaceChildren(h("p", { class: "error" }, err.message));
        return;
      }
      this.qbPublic = s;
      const connSig = JSON.stringify([s.connected, s.configured, s.url, s.version, s.error]);
      if (connSig !== conn.dataset.sig) {
        conn.dataset.sig = connSig;
        conn.replaceChildren(
          h(
            "p",
            { class: s.connected ? "hint" : s.configured ? "error" : "hint" },
            s.connected ? `Connected to qBittorrent ${s.version} at ${s.url}` : s.configured ? s.error || "Not connected" : "Connect Hush to the qBittorrent you already run. Hush only watches its downloads and RSS rules; qBittorrent decides what is saved and where."
          ),
          s.connected ? h("button", { class: "btn ghost", type: "button", onclick: () => {
            var _a;
            ((_a = conn.querySelector("form")) == null ? void 0 : _a.remove()) || conn.append(form());
          } }, "Change connection") : form()
        );
      }
      if (!s.connected) {
        listBox.replaceChildren();
        rssBox.replaceChildren();
        addWrap.replaceChildren();
        return;
      }
      const listSig = JSON.stringify(s.torrents.map((t) => [t.hash, t.progress, t.state, t.dlspeed, t.category, t.save_path]));
      if (listSig === listBox.dataset.sig) return;
      listBox.dataset.sig = listSig;
      if (!addWrap.firstChild) {
        try {
          cats = await api("/api/qbit/categories");
        } catch (e) {
        }
        addWrap.append(destBox(), addBox());
      }
      listBox.replaceChildren(h("h2", {}, "Downloads"), ...s.torrents.length ? s.torrents.map((t) => h(
        "div",
        { class: "dl" },
        h(
          "div",
          { class: "dl-top" },
          h("strong", { class: "dl-name", title: t.name }, t.name),
          h("span", { class: "hint" }, [stateText(t), fmtSize(t.size), speed(t.dlspeed), t.done ? "" : eta(t.eta)].filter(Boolean).join(" · "))
        ),
        t.save_path ? h("div", { class: "hint", title: "Where qBittorrent saves it" }, t.save_path) : null,
        h("div", { class: "pbar big" }, h("i", { style: `width:${Math.round(t.progress * 100)}%` })),
        h(
          "div",
          { class: "dl-actions" },
          t.paused ? h("button", { class: "btn subtle", type: "button", onclick: () => act(t.hash, "resume") }, "Resume") : h("button", { class: "btn subtle", type: "button", onclick: () => act(t.hash, "pause") }, "Pause"),
          cats.categories.length ? h("select", { "aria-label": `Category for ${t.name}`, onchange: async (e) => {
            try {
              await api(`/api/qbit/category/${t.hash}`, { method: "POST", body: { category: e.target.value } });
              toast("Category changed");
            } catch (err) {
              toast(err.message);
            }
          } }, h("option", { value: "" }, "No category"), ...cats.categories.map((c) => h("option", { value: c.name, selected: c.name === t.category }, c.name))) : null,
          h("button", { class: "btn ghost", type: "button", title: "Move the files to another folder", onclick: async () => {
            const p = prompt("Move to which folder? (a folder on the qBittorrent machine)", t.save_path || "");
            if (!p) return;
            try {
              await api(`/api/qbit/location/${t.hash}`, { method: "POST", body: { path: p } });
              toast("qBittorrent is moving it");
            } catch (err) {
              toast(err.message);
            }
          } }, "Move…"),
          h("button", { class: "btn ghost", type: "button", title: "Takes it off the list; the files stay", onclick: () => {
            if (confirm(`Remove "${t.name}" from qBittorrent's list? The files are kept.`)) act(t.hash, "remove");
          } }, "Remove")
        )
      )) : [h("p", { class: "hint" }, "Nothing downloading right now.")]);
    };
    const refreshRss = async () => {
      let r;
      try {
        r = await api("/api/qbit/rss");
      } catch (e) {
        rssBox.replaceChildren();
        return;
      }
      rssBox.replaceChildren(
        h("h2", {}, "RSS downloader"),
        ...r.feeds.length ? r.feeds.map((f) => h(
          "section",
          { class: "dl-feed" },
          h("div", { class: "dl-top" }, h("strong", {}, f.title || f.name), h("button", { class: "btn ghost", type: "button", onclick: async (e) => {
            e.currentTarget.disabled = true;
            try {
              await api("/api/qbit/rss/refresh", { method: "POST", body: { name: f.name } });
              toast("qBittorrent is checking the feed");
              setTimeout(refreshRss, 4e3);
            } catch (err) {
              toast(err.message);
            }
          } }, "Check now")),
          f.has_error ? h("p", { class: "error" }, "qBittorrent could not read this feed") : null,
          h("ul", { class: "dl-articles" }, ...f.articles.slice(0, 10).map((a) => h(
            "li",
            {},
            h("span", { class: "grow" }, a.title, a.date ? h("span", { class: "hint" }, ` · ${new Date(a.date).toLocaleDateString()}`) : null),
            a.in_client ? h("span", { class: "hint" }, "In qBittorrent") : h("button", { class: "btn subtle", type: "button", onclick: async (e) => {
              const b = e.currentTarget;
              b.disabled = true;
              b.textContent = "Adding…";
              try {
                const r2 = await api("/api/qbit/rss/add", { method: "POST", body: { feed: f.name, id: a.id, ...destBody() } });
                toast(`Sent to qBittorrent: ${r2.title}`);
                b.textContent = "Added";
                refreshList();
              } catch (err) {
                toast(err.message);
                b.disabled = false;
                b.textContent = "Add";
              }
            } }, "Add")
          )))
        )) : [h("p", { class: "hint" }, "No RSS feeds in qBittorrent yet.")],
        r.rules.length ? h("h3", {}, "Download rules") : null,
        ...r.rules.map((u) => h("div", { class: "pref" }, h("div", {}, h("strong", {}, u.name), h("p", { class: "hint" }, [u.enabled ? "On" : "Off", u.must_contain && `matches "${u.must_contain}"`, u.last_match && `last match ${u.last_match}`].filter(Boolean).join(" · ")))))
      );
    };
    this.box().replaceChildren(h("div", { class: "catalog-head" }, h("div", {}, h("h1", {}, "Downloads"))), conn, addWrap, listBox, rssBox);
    await refreshList();
    refreshRss();
    this.dlTimer = setInterval(() => {
      var _a, _b;
      if (location.hash !== "#/downloads" || document.hidden) {
        if (location.hash !== "#/downloads") clearInterval(this.dlTimer);
        return;
      }
      if (((_b = (_a = document.activeElement) == null ? void 0 : _a.matches) == null ? void 0 : _b.call(_a, "input")) && this.box().contains(document.activeElement)) return;
      refreshList();
    }, 5e3);
  },
  /** A status picker for a show or movie: puts it on My List, changes its status, or takes it off. */
  listControl(target, current, onChange) {
    const labels = { watching: "Watching", planned: "Plan to watch", completed: "Completed", dropped: "Dropped" };
    return h(
      "select",
      { class: "list-status", "aria-label": "My List", onchange: async (e) => {
        const v = e.target.value;
        try {
          if (!v) {
            if (target.ref) await api(`/api/watchlist?ref=${encodeURIComponent(target.ref)}`, { method: "DELETE" });
          } else await api("/api/watchlist", { method: "POST", body: { ...target, status: v } });
          toast(v ? `${labels[v]}` : "Removed from My List");
          onChange == null ? void 0 : onChange(v);
        } catch (err) {
          toast(err.message);
        }
      } },
      h("option", { value: "" }, current ? "Remove from My List" : "＋ My List"),
      ...Object.entries(labels).map(([k, t]) => h("option", { value: k, selected: k === current }, t))
    );
  },
  async mylist() {
    this.cameFrom = "#/mylist";
    document.title = "My List – Hush";
    const st = this.listState || (this.listState = { filter: "all" });
    const items = await api("/api/watchlist");
    const names = { watching: "Watching", planned: "Plan to watch", completed: "Completed", dropped: "Dropped" };
    const counts = { all: items.length };
    for (const k of Object.keys(names)) counts[k] = items.filter((i) => i.status === k).length;
    const rank = (i) => {
      var _a;
      return ((_a = i.progress) == null ? void 0 : _a.unwatched) ? 0 : i.airing ? 1 : 2;
    };
    const shown = items.filter((i) => st.filter === "all" || i.status === st.filter).sort((a, b) => Object.keys(names).indexOf(a.status) - Object.keys(names).indexOf(b.status) || rank(a) - rank(b) || (a.title || "").localeCompare(b.title || ""));
    const chips = h("div", { class: "letters", role: "group", "aria-label": "Show" }, ...["all", ...Object.keys(names)].map((k) => h(
      "button",
      { class: "lt", type: "button", "aria-pressed": String(st.filter === k), onclick: () => {
        st.filter = k;
        this.open("mylist", null, { quiet: true });
      } },
      `${k === "all" ? "All" : names[k]} ${counts[k]}`
    )));
    const card = (i) => {
      var _a, _b;
      const href = i.kind === "movie" ? `#/title/${i.media_key}` : i.show_key ? `#/show/${i.show_key}` : null;
      const nx = (_a = i.progress) == null ? void 0 : _a.next;
      const lines = [];
      if (i.kind === "movie") lines.push(i.watched ? "Watched" : i.position ? `Resume ${fmt(i.position)}` : "");
      else if (i.in_library) lines.push(nx ? `Next: S${nx.season}E${nx.episode}${nx.title ? ` · ${nx.title}` : ""}` : ((_b = i.progress) == null ? void 0 : _b.episodes) ? "All caught up" : "No episodes yet");
      else lines.push([i.network, i.show_status].filter(Boolean).join(" · "), "Not in your library");
      if (i.airing) lines.push(`${i.in_library ? "New" : "Next"}: S${i.airing.season}E${i.airing.episode} · ${when(i.airing.airs_at)}`);
      const art = h("div", { class: "art" }, i.art_url ? h("img", { src: thumb(i.art_url), alt: "", loading: "lazy" }) : h("div", { class: "noart" }, i.title));
      const playHref = i.kind === "movie" ? `#/p/${i.source_id}/${i.item_id}` : nx ? `#/p/${nx.source_id}/${nx.item_id}` : null;
      const target = i.show_key ? { show_key: i.show_key } : i.media_key ? { media_key: i.media_key } : { ref: i.ref };
      return h(
        "div",
        { class: "card ml" },
        href ? h("a", { href }, art) : art,
        h("span", { class: "name" }, i.title),
        ...lines.filter(Boolean).map((t) => h("span", { class: "sub" }, t)),
        h(
          "div",
          { class: "ml-actions" },
          playHref ? h("a", { class: "btn subtle", href: playHref, onclick: () => {
            Queue.set([i.kind === "movie" ? { src: i.source_id, item: i.item_id, title: i.title } : { src: nx.source_id, item: nx.item_id, title: nx.title }]);
          } }, (nx == null ? void 0 : nx.position) || i.position ? "Resume" : "Play") : null,
          this.listControl({ ...target }, i.status, () => this.open("mylist", null, { quiet: true }))
        )
      );
    };
    const found = h("div", { class: "found" });
    const search = h("input", { class: "search", type: "search", placeholder: "Find a show to follow", "aria-label": "Find a show to follow", autocomplete: "off" });
    let timer;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = search.value.trim();
        if (q.length < 2) {
          found.replaceChildren();
          return;
        }
        try {
          const rs = await api(`/api/watchlist/search?q=${encodeURIComponent(q)}`);
          found.replaceChildren(...rs.length ? rs.map((r) => h(
            "div",
            { class: "found-row" },
            h("div", {}, h("strong", {}, r.title), r.year ? ` (${r.year})` : "", h("div", { class: "hint" }, [r.network, r.status].filter(Boolean).join(" · "))),
            items.some((i) => i.ref === `tm:${r.tvmaze_id}`) ? h("span", { class: "hint" }, "On your list") : h("button", { class: "btn subtle", type: "button", onclick: async () => {
              try {
                await api("/api/watchlist", { method: "POST", body: { tvmaze_id: r.tvmaze_id, status: "planned" } });
                toast(`${r.title} added`);
                search.value = "";
                this.open("mylist", null, { quiet: true });
              } catch (err) {
                toast(err.message);
              }
            } }, "Follow")
          )) : [h("p", { class: "hint" }, "Nothing found")]);
        } catch (err) {
          found.replaceChildren(h("p", { class: "error" }, err.message));
        }
      }, 350);
    });
    this.box().replaceChildren(
      h("div", { class: "catalog-head" }, h(
        "div",
        {},
        h("h1", {}, "My List"),
        h("p", { class: "hint" }, "Shows and movies you follow, what to watch next, and when new episodes air.")
      )),
      ...[
        isKids() ? null : h("div", { class: "ml-search" }, search, found),
        items.length ? chips : null,
        items.length ? h("div", { class: "grid" }, ...shown.map(card)) : h(
          "div",
          { class: "empty" },
          h("h3", {}, "Your list is empty"),
          h("p", {}, "Shows you start watching appear here by themselves. Use the box above to follow a show you are interested in, or the My List menu on any show or movie.")
        )
      ].filter(Boolean)
    );
  },
  /** The programme-guide part of the playlist manager: sources, status and a refresh button. */
  guidesBox() {
    const box = h("div", { class: "guides" });
    const render = async () => {
      var _a;
      let g;
      try {
        g = await api("/api/live/guides");
      } catch (e) {
        return;
      }
      const st = g.status;
      const input = h("input", { type: "text", placeholder: "https://…/guide.xml.gz", "aria-label": "Guide address", spellcheck: "false" });
      const sel = h(
        "select",
        { "aria-label": "Suggested guides" },
        h("option", { value: "" }, "Pick a free guide…"),
        ...g.presets.map((p) => h("option", { value: p.url }, p.name))
      );
      const add = async (url) => {
        try {
          await api("/api/live/guides", { method: "POST", body: { url } });
          toast("Guide added. Reading it can take a minute.");
          render();
        } catch (err) {
          toast(err.message);
        }
      };
      box.replaceChildren(
        h("strong", {}, "Programme guide"),
        h("p", { class: "hint" }, st ? `${plural(st.matched, "channel")} matched · ${plural(st.programmes, "programme")} · updated ${new Date(st.at * 1e3).toLocaleString()}${((_a = st.errors) == null ? void 0 : _a.length) ? ` · ${st.errors.join("; ")}` : ""}` : "No guide yet. Add one so channels can show what is on now and next."),
        ...[...g.urls, ...g.advertised].map((u) => h(
          "div",
          { class: "row" },
          h("span", { class: "grow hint", title: u }, u.replace(/^https?:\/\//, "")),
          g.urls.includes(u) ? h("button", { class: "btn ghost", type: "button", onclick: async () => {
            await api(`/api/live/guides?url=${encodeURIComponent(u)}`, { method: "DELETE" });
            render();
          } }, "Remove") : h("span", { class: "hint" }, "from playlist")
        )),
        h("form", { class: "row", onsubmit: (e) => {
          e.preventDefault();
          if (input.value.trim()) add(input.value.trim());
        } }, input, h("button", { class: "btn subtle", type: "submit" }, "Add guide")),
        h(
          "div",
          { class: "row" },
          sel,
          h("button", { class: "btn subtle", type: "button", onclick: () => sel.value && add(sel.value) }, "Add"),
          h("button", { class: "btn ghost", type: "button", onclick: async (e) => {
            e.currentTarget.disabled = true;
            await api("/api/live/guides/refresh", { method: "POST" }).catch(() => {
            });
            toast("Refreshing the guide…");
            setTimeout(render, 15e3);
          } }, "Refresh now")
        )
      );
    };
    render();
    return box;
  },
  /* ---------- Live TV: channels from IPTV playlists ---------- */
  async live() {
    const st = this.liveState || (this.liveState = { q: "", group: "", favorites: false, hideDead: true, panel: false, letter: "" });
    this.cameFrom = "#/live";
    document.title = "Live TV – Hush";
    const [groups, playlists] = await Promise.all([api("/api/live/groups"), api("/api/live/playlists")]);
    const head = h("div", { class: "catalog-head" });
    const tools = h("div", { class: "live-tools" });
    const panel = h("div", { class: "pl-panel", hidden: !st.panel });
    const grid = h("div", { class: "chans" });
    const more = h("button", { class: "btn subtle", type: "button", hidden: true }, "Show more channels");
    const summary = h("p", { class: "hint" });
    let loaded = [], total = 0, stats = { dead: 0, favorites: 0, total: 0 };
    const toQueue = () => Queue.set(loaded.map((c) => ({ src: "url", item: c.item_id, title: c.name, chan: c.key, logo: c.logo_url, groups: c.groups })));
    const card = (c, n, setQueue = toQueue) => {
      const star = h("button", {
        class: "star",
        type: "button",
        "aria-pressed": String(c.favorite),
        title: c.favorite ? "Remove from favorites" : "Add to favorites",
        "aria-label": `Favorite: ${c.name}`,
        onclick: async (e) => {
          e.preventDefault();
          e.stopPropagation();
          c.favorite = !c.favorite;
          star.setAttribute("aria-pressed", String(c.favorite));
          star.textContent = c.favorite ? "★" : "☆";
          try {
            await api(`/api/live/channels/${c.key}/favorite`, { method: "POST", body: { favorite: c.favorite } });
          } catch (err) {
            toast(err.message);
          }
        }
      }, c.favorite ? "★" : "☆");
      let peek = null, snap = null;
      const stopPeek = () => {
        clearTimeout(peek);
        snap == null ? void 0 : snap.remove();
        snap = null;
      };
      const startPeek = (e) => {
        stopPeek();
        const logo = e.currentTarget.querySelector(".logo");
        peek = setTimeout(() => {
          if (!logo || Player.chan === c.key) return;
          snap = h("img", { class: "snap", src: `/api/live/snapshot/${c.key}.jpg`, alt: "", onerror: () => stopPeek() });
          logo.append(snap);
        }, 900);
      };
      return h(
        "a",
        {
          class: "chan",
          "data-key": c.key,
          href: `#/p/url/${c.item_id}`,
          onclick: () => {
            stopPeek();
            setQueue();
          },
          onmouseenter: startPeek,
          onfocus: startPeek,
          onmouseleave: stopPeek,
          onblur: stopPeek
        },
        n != null ? h("span", { class: "num" }, n + 1) : null,
        h("div", { class: "logo" }, c.logo_url ? h("img", { src: thumb(c.logo_url, 160), alt: "", loading: "lazy", onerror: (e) => {
          e.target.replaceWith(h("span", { class: "noart" }, initials(c.name)));
        } }) : h("span", { class: "noart" }, initials(c.name))),
        star,
        h("span", { class: "name", title: c.name }, splitTags(c.name).title),
        h("span", { class: "sub" }, [...splitTags(c.name).tags, ...c.groups.slice(0, 1)].join(" · "))
      );
    };
    const fetchPage = async (reset) => {
      if (reset) {
        loaded = [];
        grid.replaceChildren();
      }
      const q = new URLSearchParams({ q: st.q, group: st.group, favorites: st.favorites, hide_dead: st.hideDead, letter: st.letter, limit: IS_TV_DEVICE || TV.on ? 48 : 120, offset: loaded.length });
      const r = await api(`/api/live/channels?${q}`);
      total = r.total;
      stats = r.stats;
      const first = loaded.length;
      loaded = loaded.concat(r.channels);
      grid.append(...r.channels.map((c, i) => card(c, first + i)));
      toQueue();
      api(`/api/live/epg?keys=${r.channels.slice(0, 80).map((c) => c.key).join(",")}`).then((g) => {
        for (const [k, v] of Object.entries(g)) {
          const sub = grid.querySelector(`[data-key="${k}"] .sub`);
          if (sub && v.now) sub.textContent = `Now: ${v.now.title}`;
        }
      }).catch(() => {
      });
      lb.set(new Set(Object.keys(r.letters)), st.letter);
      showRecent();
      more.hidden = loaded.length >= total;
      summary.textContent = stats.total ? `${plural(total, "channel")}${st.group ? ` in ${st.group}` : ""}${stats.dead ? ` · ${stats.dead} hidden because they didn't play` : ""}` : "";
      if (!stats.total) grid.replaceChildren();
    };
    more.addEventListener("click", () => fetchPage(false));
    Queue.loadMore = async () => {
      if (loaded.length >= total) return false;
      await fetchPage(false);
      return true;
    };
    const lb = makeLetterBar((l) => {
      st.letter = l;
      fetchPage(true);
    });
    const recentBox = h("section", { class: "recent-row", hidden: true });
    const showRecent = async () => {
      const plain = !st.q && !st.group && !st.favorites && !st.letter;
      if (!plain) {
        recentBox.hidden = true;
        return;
      }
      try {
        const r = await api("/api/live/channels?recent=true&limit=8");
        const items = r.channels;
        recentBox.hidden = !items.length;
        const q = () => Queue.set(items.map((c) => ({ src: "url", item: c.item_id, title: c.name, chan: c.key, logo: c.logo_url, groups: c.groups })));
        recentBox.replaceChildren(
          h("h2", {}, "Recently watched"),
          h("div", { class: "chans small" }, ...items.map((c) => card(c, null, () => {
            q();
            Queue.loadMore = null;
          })))
        );
      } catch (e) {
        recentBox.hidden = true;
      }
    };
    let timer;
    const search = h("input", { class: "search", type: "search", placeholder: "Find a channel", value: st.q, "aria-label": "Find a channel" });
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        st.q = search.value.trim();
        fetchPage(true);
      }, 300);
    });
    const sel = h(
      "select",
      { "aria-label": "Group", onchange: (e) => {
        st.group = e.target.value;
        fetchPage(true);
      } },
      h("option", { value: "" }, "All groups"),
      ...groups.map((g) => h("option", { value: g.name, selected: g.name === st.group }, `${g.name} (${g.count})`))
    );
    const favBtn = h("button", { class: "btn subtle", type: "button", "aria-pressed": String(st.favorites), onclick: (e) => {
      st.favorites = !st.favorites;
      e.currentTarget.setAttribute("aria-pressed", String(st.favorites));
      e.currentTarget.textContent = st.favorites ? "★ Favorites only" : "☆ Favorites";
      fetchPage(true);
    } }, st.favorites ? "★ Favorites only" : "☆ Favorites");
    const dead = h("label", {}, h("input", { type: "checkbox", checked: st.hideDead, onchange: (e) => {
      st.hideDead = e.target.checked;
      fetchPage(true);
    } }), "Hide channels that don't play");
    const plBtn = h("button", { class: "btn ghost", type: "button", onclick: () => setPanel(!st.panel) });
    const setPanel = (on) => {
      st.panel = on;
      panel.hidden = !on;
      plBtn.textContent = `Playlists ${on ? "▴" : "▾"}`;
      plBtn.setAttribute("aria-expanded", String(on));
    };
    tools.append(search, sel, favBtn, dead, plBtn);
    const reloadAll = () => this.open("live");
    const addName = h("input", { type: "text", placeholder: "Name (optional)", "aria-label": "Playlist name" });
    const addUrl = h("input", { type: "text", placeholder: "https://…/channels.m3u", "aria-label": "Playlist address", spellcheck: "false" });
    panel.append(
      h(
        "div",
        { class: "row", style: "justify-content:space-between;align-items:center" },
        h("strong", {}, "Playlists"),
        h("button", { class: "btn ghost", type: "button", onclick: () => {
          setPanel(false);
          plBtn.focus();
        } }, "Collapse ▴")
      ),
      h("p", { class: "hint" }, "Playlists are .m3u or .m3u8 lists of channels. Hush reads them once, keeps the channels here with their logos and groups, and refreshes them every day."),
      playlists.length ? h("ul", {}, ...playlists.map((p) => h(
        "li",
        {},
        h("span", { class: "grow" }, h("strong", {}, p.name), " ", h("span", { class: p.error ? "error" : "hint" }, p.error ? p.error : `${plural(p.channels, "channel")}`)),
        h("button", { class: "btn ghost", type: "button", onclick: async (e) => {
          e.currentTarget.disabled = true;
          e.currentTarget.textContent = "Reading…";
          try {
            await api(`/api/live/playlists/${p.id}/refresh`, { method: "POST" });
          } catch (err) {
            toast(err.message);
          }
          reloadAll();
        } }, "Refresh"),
        h("button", { class: "btn ghost", type: "button", onclick: async () => {
          if (!confirm(`Remove "${p.name}" and its channels from Live TV?`)) return;
          await api(`/api/live/playlists/${p.id}`, { method: "DELETE" });
          reloadAll();
        } }, "Remove")
      ))) : "",
      h("form", { class: "row", onsubmit: async (e) => {
        e.preventDefault();
        const btn = e.submitter;
        btn.disabled = true;
        btn.textContent = "Reading…";
        try {
          await api("/api/live/playlists", { method: "POST", body: { name: addName.value, url: addUrl.value } });
          toast("Playlist added");
          reloadAll();
        } catch (err) {
          toast(err.message);
          btn.disabled = false;
          btn.textContent = "Add playlist";
        }
      } }, addName, addUrl, h("button", { class: "btn primary", type: "submit" }, "Add playlist")),
      this.guidesBox(),
      h("div", { class: "row" }, h("button", { class: "btn subtle", type: "button", onclick: async (e) => {
        e.currentTarget.disabled = true;
        e.currentTarget.textContent = "Importing…";
        try {
          const r = await api("/api/live/playlists/import", { method: "POST" });
          toast(r.imported ? `Imported ${plural(r.imported, "playlist")}` : "No saved playlists found");
        } catch (err) {
          toast(err.message);
        }
        reloadAll();
      } }, "Import playlists from my saved sources"))
    );
    head.append(h("div", {}, h("h1", {}, "Live TV"), summary));
    const empty = h(
      "div",
      { class: "empty", hidden: true },
      h("h3", {}, "No channels yet"),
      h("p", {}, "Add an IPTV playlist (.m3u or .m3u8) and its channels appear here with their logos, sorted into groups."),
      h("button", { class: "btn primary", type: "button", onclick: () => {
        setPanel(true);
        panel.scrollIntoView({ block: "nearest" });
      } }, "Add a playlist")
    );
    this.box().replaceChildren(head, tools, lb.el, panel, recentBox, grid, h("div", { class: "row", style: "margin-top:1.25rem" }, more), empty);
    await fetchPage(true);
    empty.hidden = stats.total > 0;
    setPanel(st.panel || !stats.total);
  },
  empty(what) {
    if (isKids()) return h(
      "div",
      { class: "empty" },
      h("h3", {}, `No ${what} for you yet`),
      h("p", {}, "Titles show up here once a grown-up has scanned them and they are safe to watch.")
    );
    return h(
      "div",
      { class: "empty" },
      h("h3", {}, `No ${what} yet`),
      h("p", {}, "Hush needs to look through your sources and add details and artwork. Run it once; after that it keeps itself up to date."),
      h("button", { class: "btn primary", type: "button", onclick: async () => {
        try {
          await api("/api/tasks/metadata/run", { method: "POST" });
          toast("Started. This can take a few minutes.");
        } catch (e) {
          toast(e.message);
        }
      } }, "Find my titles"),
      h("a", { class: "btn ghost", href: "#/tasks" }, "Open Tasks")
    );
  },
  /* ---------- Home: shelves, made for the couch ---------- */
  shelf(title, seeAll, cards) {
    if (!cards.length) return null;
    return h(
      "section",
      { class: "shelf" },
      h("div", { class: "shelf-head" }, h("h2", {}, title), seeAll ? h("a", { href: seeAll }, "See all →") : null),
      h("div", { class: "shelf-row" }, ...cards)
    );
  },
  async home() {
    this.cameFrom = "#/home";
    document.title = "Home – Hush";
    const get = (p, f = (x) => x) => api(p).then(f).catch(() => []);
    const [cont, recent, favs, movies, shows, soon, mine] = await Promise.all([
      get("/api/progress/recent?limit=12"),
      get("/api/live/channels?recent=true&limit=12", (r) => r.channels),
      get("/api/live/channels?favorites=true&limit=16", (r) => r.channels),
      get("/api/library/movies"),
      get("/api/library/shows"),
      get("/api/library/upcoming"),
      get("/api/watchlist")
    ]);
    const upNext = mine.filter((i) => {
      var _a;
      return i.status === "watching" && ((_a = i.progress) == null ? void 0 : _a.next) && !i.progress.next.position;
    });
    const chan = (list) => (c) => h(
      "a",
      { class: "chan", href: `#/p/url/${c.item_id}`, onclick: () => {
        Queue.set(list.map((x) => ({ src: "url", item: x.item_id, title: x.name, chan: x.key, logo: x.logo_url, groups: x.groups })));
        Queue.loadMore = null;
      } },
      h("div", { class: "logo" }, c.logo_url ? h("img", { src: thumb(c.logo_url, 160), alt: "", loading: "lazy" }) : h("span", { class: "noart" }, initials(c.name))),
      h("span", { class: "name" }, splitTags(c.name).title)
    );
    const poster = (isShow, list) => (m) => h(
      "a",
      {
        class: "card",
        href: isShow ? `#/show/${m.show_key}` : `#/title/${m.media_key}`,
        onclick: () => {
          if (!isShow) Queue.set(list.map((x) => ({ src: x.source_id, item: x.item_id, title: x.title })));
        }
      },
      h("div", { class: "art" }, m.art_url ? h("img", { src: thumb(m.art_url), alt: "", loading: "lazy" }) : h("div", { class: "noart" }, m.title)),
      h("span", { class: "name" }, m.title),
      h("span", { class: "sub" }, isShow ? plural(m.episodes, "episode") : m.year || "")
    );
    movies.sort((a, b) => sortKey(a.title).localeCompare(sortKey(b.title)));
    shows.sort((a, b) => sortKey(a.title).localeCompare(sortKey(b.title)));
    const rows = [
      this.shelf("Continue watching", null, cont.map((it) => h(
        "a",
        { class: "card wide", href: `#/p/${it.source_id}/${it.item_id}` },
        h(
          "div",
          { class: "art" },
          it.art_url ? h("img", { src: thumb(it.art_url), alt: "", loading: "lazy" }) : h("div", { class: "noart" }, it.title),
          it.fraction != null ? h("div", { class: "pbar" }, h("i", { style: `width:${Math.round(it.fraction * 100)}%` })) : null
        ),
        h("span", { class: "name" }, it.title),
        h("span", { class: "sub" }, [it.subtitle, it.duration ? `${fmt(it.duration - it.position)} left` : ""].filter(Boolean).join(" · "))
      ))),
      this.shelf("Up next on My List", "#/mylist", upNext.slice(0, 16).map((i) => h(
        "a",
        {
          class: "card wide",
          href: `#/p/${i.progress.next.source_id}/${i.progress.next.item_id}`,
          onclick: () => Queue.set([{ src: i.progress.next.source_id, item: i.progress.next.item_id, title: i.progress.next.title }])
        },
        h("div", { class: "art" }, i.art_url ? h("img", { src: thumb(i.art_url), alt: "", loading: "lazy" }) : h("div", { class: "noart" }, i.title)),
        h("span", { class: "name" }, i.title),
        h("span", { class: "sub" }, `S${i.progress.next.season}E${i.progress.next.episode}${i.progress.next.title ? ` · ${i.progress.next.title}` : ""}`)
      ))),
      this.shelf("Coming up", null, soon.slice(0, 16).map((u) => h(
        "a",
        { class: "card", href: `#/show/${u.show_key}` },
        h("div", { class: "art" }, u.art_url ? h("img", { src: thumb(u.art_url), alt: "", loading: "lazy" }) : h("div", { class: "noart" }, u.show_title)),
        h("span", { class: "name" }, u.show_title),
        h("span", { class: "sub" }, `S${u.season}E${u.episode} · ${when(u.airs_at)}`)
      ))),
      this.shelf("Live TV: recently watched", "#/live", recent.map(chan(recent))),
      this.shelf("Live TV: favorites", "#/live", favs.map(chan(favs))),
      this.shelf("Movies", "#/movies", movies.slice(0, 18).map(poster(false, movies))),
      this.shelf("TV shows", "#/shows", shows.slice(0, 18).map(poster(true, shows)))
    ].filter(Boolean);
    this.box().replaceChildren(
      h("div", { class: "catalog-head" }, h("div", {}, h("h1", {}, "Home"))),
      ...rows.length ? rows : [h(
        "div",
        { class: "empty" },
        h("h3", {}, "Nothing here yet"),
        h("p", {}, "Add a source, then open Tasks to build your library. Live TV channels you watch and favorite show up here."),
        h("a", { class: "btn primary", href: "#/live" }, "Open Live TV")
      )]
    );
  },
  /* ---------- manage profiles (grown-ups only) ---------- */
  async profilesPage() {
    this.cameFrom = "#/profiles";
    document.title = "Profiles – Hush";
    const d = await Profiles.load();
    const lockBox = h("input", { type: "checkbox", checked: d.lock, onchange: async (e) => {
      try {
        await api("/api/profiles/lock", { method: "PUT", body: { lock: e.target.checked } });
        toast(e.target.checked ? "Leaving a kids profile now asks for the password" : "Switching is free again");
      } catch (err) {
        toast(err.message);
        e.target.checked = !e.target.checked;
      }
    } });
    this.box().replaceChildren(
      h("div", { class: "catalog-head" }, h(
        "div",
        {},
        h("h1", {}, "Profiles"),
        h("p", { class: "hint" }, "Everyone keeps their own place in movies and shows, favorite channels and filter choices. No passwords: just pick a name.")
      )),
      h("div", { class: "profile-list" }, ...d.profiles.map((p) => h(
        "div",
        { class: "profile-row" },
        avatarEl(p),
        h("div", { class: "grow" }, h("strong", {}, p.name), h("div", { class: "sub" }, p.kids ? kidsSummary(p.settings) : "Sees everything. Can change settings.")),
        h("button", { class: "btn subtle", type: "button", onclick: () => this.profileDialog(p, d) }, "Edit")
      ))),
      h("div", { class: "row" }, h("button", { class: "btn primary", type: "button", onclick: () => this.profileDialog(null, d) }, "Add a profile")),
      d.lock !== void 0 && d.profiles.some((p) => p.kids) ? h(
        "label",
        { class: "inline", style: "display:flex;gap:.5rem;align-items:center;margin-top:1.25rem;color:var(--linen-dim)" },
        lockBox,
        "Ask for the Hush password to leave a kids profile (needs a Hush password to be set)"
      ) : null
    );
  },
  profileDialog(p, d) {
    const dlg = $("#profile-dialog"), isNew = !p;
    let color = (p == null ? void 0 : p.color) || d.colors[d.profiles.length % d.colors.length];
    let avatar = (p == null ? void 0 : p.avatar) || "";
    $("#pd-title").textContent = isNew ? "Add a profile" : `Edit ${p.name}`;
    $("#pd-name").value = (p == null ? void 0 : p.name) || "";
    $("#pd-kids").checked = !!(p == null ? void 0 : p.kids);
    $("#pd-error").textContent = "";
    const st = (p == null ? void 0 : p.settings) || { block: d.categories, max_cert: 1, hide_unscanned: true, allow_live: false };
    $("#pd-language").value = (st.block || []).includes("mild") ? "strict" : "mild";
    $("#pd-cert").value = [0, 1, 2].includes(st.max_cert) ? String(st.max_cert) : "5";
    $("#pd-unscanned").checked = st.hide_unscanned === false;
    $("#pd-unrated").checked = !!st.allow_unrated;
    $("#pd-live").checked = !!st.allow_live;
    const sync = () => {
      $("#pd-kidsopts").hidden = !$("#pd-kids").checked;
    };
    $("#pd-kids").onchange = sync;
    sync();
    const swatches = $("#pd-colors");
    const drawColors = () => swatches.replaceChildren(...d.colors.map((c) => h("button", {
      type: "button",
      role: "radio",
      "aria-checked": String(c === color),
      "aria-label": c,
      style: `background:${c}`,
      onclick: () => {
        color = c;
        drawColors();
        drawAvatars();
      }
    })));
    const avatarBox = $("#pd-avatars");
    const drawAvatars = () => avatarBox.replaceChildren(...["", ...d.avatars].map((id) => {
      const name = $("#pd-name").value || "A";
      const b = h("button", {
        type: "button",
        role: "radio",
        "aria-checked": String(id === avatar),
        title: id || "Letter",
        "aria-label": id || "Letter",
        onclick: () => {
          avatar = id;
          drawAvatars();
        }
      });
      fillAvatar(b, { color, avatar: id, name });
      return b;
    }));
    const redraw = () => {
      drawColors();
      drawAvatars();
    };
    $("#pd-name").oninput = drawAvatars;
    redraw();
    $("#pd-delete").hidden = isNew;
    $("#pd-delete").onclick = async () => {
      if (!confirm(`Delete ${p.name}? Their place in movies and favorite channels go too.`)) return;
      try {
        await api(`/api/profiles/${p.id}`, { method: "DELETE" });
        dlg.close();
        this.open("profiles");
      } catch (err) {
        $("#pd-error").textContent = err.message;
      }
    };
    $("#pd-form").onsubmit = async (e) => {
      var _a;
      if (((_a = e.submitter) == null ? void 0 : _a.value) !== "save") return;
      e.preventDefault();
      const kids = $("#pd-kids").checked;
      const body = { name: $("#pd-name").value, kids, color, avatar, settings: kids ? {
        block: $("#pd-language").value === "strict" ? d.categories : d.categories.filter((c) => c !== "mild"),
        max_hits: 0,
        max_cert: Number($("#pd-cert").value),
        hide_unscanned: !$("#pd-unscanned").checked,
        allow_unrated: $("#pd-unrated").checked,
        allow_live: $("#pd-live").checked
      } : {} };
      try {
        await api(isNew ? "/api/profiles" : `/api/profiles/${p.id}`, { method: isNew ? "POST" : "PUT", body });
        dlg.close();
        toast("Saved");
        await Profiles.load();
        Profiles.apply();
        this.open("profiles");
      } catch (err) {
        $("#pd-error").textContent = err.message;
      }
    };
    dlg.showModal();
  },
  async folders() {
    this.cameFrom = "#/folders";
    document.title = "Folders – Hush";
    const list = S.sources.filter((s) => !s.error);
    this.box().replaceChildren(
      h("div", { class: "catalog-head" }, h("div", {}, h("h1", {}, "Folders"), h("p", { class: "hint" }, "Browse your sources as folders"))),
      list.length ? h("div", { class: "grid shelf-grid" }, ...list.map((s) => h(
        "a",
        { class: "card wide", href: `#/b/${s.id}` },
        h("div", { class: "art" }, h("div", { class: "noart" }, s.name)),
        h("span", { class: "name" }, s.name),
        h("span", { class: "sub" }, s.type)
      ))) : h("div", { class: "empty" }, h("h3", {}, "No sources yet"), h("p", {}, "Add a source from the normal (not big screen) view."))
    );
  },
  /** "Continue watching": titles that were left part-way, newest first. */
  async continueRow() {
    let items = [];
    try {
      items = await api("/api/progress/recent?limit=12");
    } catch (e) {
      return null;
    }
    if (!items.length) return null;
    const row = h("section", { class: "continue" }, h("h2", {}, "Continue watching"));
    const grid = h("div", { class: "grid shelf" });
    for (const it of items) {
      const card = h(
        "a",
        { class: "card wide", href: `#/p/${it.source_id}/${it.item_id}` },
        h(
          "div",
          { class: "art" },
          it.art_url ? h("img", { src: thumb(it.art_url), alt: "", loading: "lazy" }) : h("div", { class: "noart" }, it.title),
          it.fraction != null ? h("div", { class: "pbar" }, h("i", { style: `width:${Math.round(it.fraction * 100)}%` })) : null,
          h("button", { class: "x", type: "button", title: "Remove from Continue watching", "aria-label": `Remove ${it.title}`, onclick: async (e) => {
            e.preventDefault();
            e.stopPropagation();
            try {
              await api(`/api/progress/${it.media_key}`, { method: "DELETE" });
              card.remove();
              if (!grid.children.length) row.remove();
            } catch (err) {
              toast(err.message);
            }
          } }, "✕")
        ),
        h("span", { class: "name" }, it.title),
        h("span", { class: "sub" }, [it.subtitle, it.duration ? `${fmt(it.duration - it.position)} left` : `at ${fmt(it.position)}`].filter(Boolean).join(" · "))
      );
      grid.append(card);
    }
    row.append(grid);
    return row;
  },
  async grid(kind) {
    const [items, shelf] = await Promise.all([api(`/api/library/${kind}`), this.continueRow()]);
    const isShows = kind === "shows";
    items.sort((a, b) => sortKey(a.title).localeCompare(sortKey(b.title)));
    const sel = this.letterSel || (this.letterSel = { movies: "", shows: "" });
    const bar = makeLetterBar((l) => {
      sel[kind] = l;
      draw();
    });
    const available = new Set(items.map((m) => letterOf(m.title, true)));
    const q = h("input", { class: "search", type: "search", placeholder: `Find in ${isShows ? "TV shows" : "movies"}`, "aria-label": "Find a title" });
    const list = h("div", { class: "grid" });
    const draw = () => {
      const f = q.value.trim().toLowerCase();
      bar.set(available, sel[kind]);
      const shown = items.filter((m) => (!f || m.title.toLowerCase().includes(f)) && (!sel[kind] || letterOf(m.title, true) === sel[kind]));
      if (!isShows) Queue.set(shown.map((m) => ({ src: m.source_id, item: m.item_id, title: m.title })));
      list.replaceChildren(...shown.map((m) => h(
        "a",
        { class: "card", href: isShows ? `#/show/${m.show_key}` : `#/title/${m.media_key}` },
        h(
          "div",
          { class: "art" },
          m.art_url ? h("img", { src: thumb(m.art_url), alt: "", loading: "lazy" }) : h("div", { class: "noart" }, m.title),
          (isShows ? m.scanned && m.scanned === m.episodes : m.scanned) ? h("span", { class: "badge", title: "Language filter is ready" }, icon("hush", "")) : null,
          (isShows ? m.episodes && m.watched >= m.episodes : m.watched) ? h("span", { class: "tick" }, "✓ Watched") : null,
          !isShows && !m.watched && m.position && m.duration ? h("div", { class: "pbar" }, h("i", { style: `width:${Math.round(m.position / m.duration * 100)}%` })) : null
        ),
        h("span", { class: "name" }, m.title),
        h("span", { class: "sub" }, isShows ? `${plural(m.episodes, "episode")}${m.seasons > 1 ? ` · ${m.seasons} seasons` : ""}` : m.year || "")
      )));
    };
    q.addEventListener("input", draw);
    this.box().replaceChildren(...[
      h("div", { class: "catalog-head" }, h(
        "div",
        {},
        h("h1", {}, isShows ? "TV shows" : "Movies"),
        h("p", { class: "hint" }, plural(items.length, isShows ? "show" : "movie"))
      ), q),
      items.length ? bar.el : null,
      shelf,
      items.length ? list : this.empty(isShows ? "TV shows" : "movies")
    ].filter(Boolean));
    if (items.length) draw();
    this.cameFrom = isShows ? "#/shows" : "#/movies";
    document.title = `${isShows ? "TV shows" : "Movies"} – Hush`;
  },
  async show(key) {
    var _a, _b, _c;
    const { show, episodes, upcoming = [], list_status = null } = await api(`/api/library/shows/${key}`);
    const seasons = {};
    for (const e of episodes) (seasons[_b = (_a = e.season) != null ? _a : 0] || (seasons[_b] = [])).push(e);
    this.cameFrom = "#/shows";
    Queue.set(episodes.map((e) => ({ src: e.source_id, item: e.item_id, title: e.title || "" })));
    document.title = `${show.title} – Hush`;
    this.backdrop(show.fanart_url);
    this.box().replaceChildren(
      h("a", { class: "backlink", href: "#/shows" }, "← TV shows"),
      h(
        "div",
        { class: "detail" },
        artBox(show.art_url, show.title),
        h(
          "div",
          {},
          h("h1", {}, show.title, show.year ? ` (${show.year})` : ""),
          h("div", { class: "facts" }, ...[(_c = show.genres) == null ? void 0 : _c.join(", "), show.rating ? `★ ${show.rating.toFixed(1)}` : "", plural(episodes.length, "episode")].filter(Boolean).map((t) => h("span", {}, t))),
          show.overview ? h("p", { class: "overview" }, show.overview) : null,
          h(
            "div",
            { class: "actions" },
            this.listControl({ show_key: key }, list_status, () => this.open("show", key, { quiet: true })),
            h("button", { class: "btn subtle admin-only", type: "button", onclick: () => this.scanAll(episodes) }, "Scan all episodes")
          )
        )
      ),
      upcoming.length ? h(
        "section",
        { class: "season" },
        h("h3", {}, "Coming up"),
        h("ul", { class: "eps" }, ...upcoming.slice(0, 8).map((u) => h(
          "li",
          { class: "ep" },
          h(
            "div",
            {},
            h("div", { class: "ep-title" }, `S${u.season}E${u.episode}${u.title ? ` · ${u.title}` : ""}`, h("span", { class: "badge", style: "margin-left:.5rem" }, when(u.airs_at))),
            u.overview ? h("div", { class: "ep-sub" }, u.overview) : null
          )
        )))
      ) : null,
      ...Object.entries(seasons).map(([n, eps]) => h(
        "section",
        { class: "season" },
        h("h3", {}, n === "0" ? "Specials" : `Season ${n}`),
        h("ul", { class: "eps" }, ...eps.map((e) => h(
          "li",
          { class: "ep" },
          h("a", { class: "thumb", href: `#/title/${e.media_key}` }, e.art_url ? h("img", { src: thumb(e.art_url, 240), alt: "", loading: "lazy" }) : null),
          h(
            "div",
            {},
            h(
              "div",
              { class: "ep-title" },
              h("a", { href: `#/title/${e.media_key}` }, `E${e.episode}${e.title ? ` · ${e.title}` : ""}`),
              e.watched ? h("span", { class: "hint", style: "margin-left:.5rem" }, "✓ Watched") : e.position ? h("span", { class: "hint", style: "margin-left:.5rem" }, `Resume ${fmt(e.position)}`) : null,
              e.scanned ? h("span", { class: "badge", style: "margin-left:.5rem", title: "Language filter is ready" }, icon("hush", ""), "Filter ready") : null
            ),
            e.overview ? h("div", { class: "ep-sub" }, e.overview) : null
          ),
          h("a", { class: "btn subtle", href: `#/p/${e.source_id}/${e.item_id}` }, e.position && !e.watched ? "Resume" : "Play")
        )))
      ))
    );
  },
  async scanAll(episodes) {
    let n = 0;
    for (const e of episodes) {
      if (e.scanned) continue;
      try {
        await api("/api/analyze", { method: "POST", body: { source_id: e.source_id, item_id: e.item_id, title: e.title || "" } });
        n++;
      } catch (e2) {
      }
    }
    toast(n ? `Queued ${plural(n, "episode")}` : "Everything is already scanned");
    Jobs.poll();
  },
  async title(key) {
    var _a;
    const m = await api(`/api/library/title/${key}`);
    const show = m.show_key ? (await api(`/api/library/shows/${m.show_key}`)).show : null;
    const caps = await api(`/api/captions/${m.source_id}/${m.item_id}`).catch(() => ({ tracks: [], transcript: false }));
    document.title = `${show ? show.title + " – " : ""}${m.title} – Hush`;
    this.backdrop(m.fanart_url || (show == null ? void 0 : show.fanart_url));
    const heading = show ? `${show.title} · S${String(m.season).padStart(2, "0")}E${String(m.episode).padStart(2, "0")}` : `${m.title}${m.year ? ` (${m.year})` : ""}`;
    const mask = h("input", { type: "checkbox" });
    const tlink = (fmt2, label) => h("a", { class: "btn ghost", href: "#", onclick: (e) => {
      e.preventDefault();
      location.href = `/api/transcript/${key}.${fmt2}${mask.checked ? "?censor=1" : ""}`;
    } }, label);
    this.box().replaceChildren(
      h("a", { class: "backlink", href: show ? `#/show/${m.show_key}` : "#/movies" }, show ? `← ${show.title}` : "← Movies"),
      h(
        "div",
        { class: "detail" },
        artBox(m.art_url, m.title, m.kind === "episode" ? "art wide" : "art"),
        h(
          "div",
          {},
          h("h1", {}, heading),
          m.kind === "episode" && m.title ? h("p", { class: "facts" }, m.title) : null,
          h("div", { class: "facts" }, ...[m.kind === "movie" ? (_a = m.genres) == null ? void 0 : _a.join(", ") : "", mins(m.runtime), m.rating ? `★ ${Number(m.rating).toFixed(1)}` : ""].filter(Boolean).map((t) => h("span", {}, t))),
          m.overview ? h("p", { class: "overview" }, m.overview) : h("p", { class: "hint" }, "No summary yet."),
          h(
            "div",
            { class: "actions" },
            h("a", { class: "btn primary", href: `#/p/${m.source_id}/${m.item_id}` }, m.position && !m.watched ? `Resume from ${fmt(m.position)}` : "Play"),
            m.kind === "movie" ? this.listControl({ media_key: key }, m.list_status, () => this.open("title", key, { quiet: true })) : null,
            h("button", { class: "btn ghost", type: "button", onclick: async () => {
              try {
                await api(`/api/progress/${key}/watched`, { method: "POST", body: { watched: !m.watched, source_id: m.source_id, item_id: m.item_id, title: m.title } });
                toast(m.watched ? "Marked as not watched" : "Marked as watched");
                this.open("title", key);
              } catch (err) {
                toast(err.message);
              }
            } }, m.watched ? "Mark as not watched" : "Mark as watched"),
            m.scanned ? h("span", { class: "badge", title: "Language filter is ready" }, icon("hush", ""), "Filter ready") : h("button", { class: "btn subtle admin-only", type: "button", onclick: async (ev) => {
              ev.currentTarget.disabled = true;
              try {
                await api("/api/analyze", { method: "POST", body: { source_id: m.source_id, item_id: m.item_id, title: m.title } });
                toast("Scanning");
                Jobs.poll();
              } catch (e) {
                toast(e.message);
              }
            } }, "Scan this title"),
            h("button", { class: "btn ghost admin-only", type: "button", onclick: () => this.fixMatch(m, show) }, "Fix match")
          ),
          isKids() ? null : h("h3", {}, "Transcript"),
          isKids() ? null : caps.transcript ? h(
            "div",
            { class: "links" },
            tlink("txt", "Text"),
            tlink("srt", "SRT"),
            tlink("vtt", "WebVTT"),
            h("label", { class: "inline" }, mask, "Mask language")
          ) : h("p", { class: "hint" }, "Scan this title and the transcript is built from the dialogue."),
          isKids() ? null : h("h3", {}, "Captions and subtitles"),
          isKids() ? null : caps.tracks.length ? h("ul", { class: "links", style: "list-style:none;padding:0;margin:0" }, ...caps.tracks.map((t) => h(
            "li",
            {},
            `${t.label} (${t.where}) `,
            h("a", { href: `/api/subtitle/${m.source_id}/${m.item_id}/${t.id}?format=srt&download=1` }, "SRT"),
            " · ",
            h("a", { href: `/api/subtitle/${m.source_id}/${m.item_id}/${t.id}?format=vtt&download=1` }, "WebVTT")
          ))) : h("p", { class: "hint" }, "No subtitle or caption tracks in or next to this file."),
          m.provider ? h("p", { class: "hint", style: "margin-top:1.5rem" }, `Details from ${{ nfo: "the NFO file next to it", name: "the file name", tmdb: "TMDB", wikipedia: "Wikipedia", tvmaze: "TVmaze", manual: "your choice" }[m.provider] || m.provider}.`) : null
        )
      )
    );
  },
  fixMatch(m, show) {
    const dlg = $("#match-dialog");
    $("#match-q").value = show ? show.title : m.title;
    $("#match-year").value = (show ? show.year : m.year) || "";
    const results = $("#match-results");
    const search = async () => {
      results.replaceChildren(h("li", {}, h("span"), h("span", { class: "sub" }, "Searching…"), h("span")));
      try {
        const q = new URLSearchParams({ key: m.media_key, q: $("#match-q").value });
        if ($("#match-year").value) q.set("year", $("#match-year").value);
        const found = await api(`/api/library/candidates?${q}`);
        results.replaceChildren(...found.length ? found.map((c) => h(
          "li",
          {},
          c.poster_url ? h("img", { src: c.poster_url, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }) : h("span", { class: "nothumb" }),
          h("div", {}, h("div", {}, `${c.title}${c.year ? ` (${c.year})` : ""}`), h("div", { class: "sub" }, (c.overview || "").slice(0, 140))),
          h("button", { class: "btn subtle", type: "button", onclick: async () => {
            try {
              await api(`/api/library/title/${m.media_key}/match`, { method: "POST", body: { candidate: c } });
              dlg.close();
              toast("Updated");
              this.open("title", m.media_key);
            } catch (e) {
              toast(e.message);
            }
          } }, "Use this")
        )) : [h("li", {}, h("span"), h("span", { class: "sub" }, "Nothing found. Try a shorter title."), h("span"))]);
      } catch (err) {
        results.replaceChildren(h("li", {}, h("span"), h("span", { class: "error" }, err.message), h("span")));
      }
    };
    $("#match-form").onsubmit = (e) => {
      e.preventDefault();
      search();
    };
    dlg.showModal();
    search();
  }
};
const ago = (t) => {
  const s = Math.max(0, Date.now() / 1e3 - t);
  return s < 90 ? "just now" : s < 5400 ? `${Math.round(s / 60)} min ago` : s < 129600 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} days ago`;
};
const inTime = (t) => {
  const s = t - Date.now() / 1e3;
  return s < 90 ? "any moment" : s < 5400 ? `in ${Math.round(s / 60)} min` : s < 129600 ? `in ${Math.round(s / 3600)} h` : `in ${Math.round(s / 86400)} days`;
};
const INTERVALS = [
  [0.25, "Every 15 minutes"],
  [1, "Every hour"],
  [3, "Every 3 hours"],
  [6, "Every 6 hours"],
  [12, "Every 12 hours"],
  [24, "Every day"],
  [168, "Every week"]
];
const Tasks = {
  timer: null,
  data: null,
  async open() {
    clearTimeout(this.timer);
    document.title = "Tasks – Hush";
    await this.load();
  },
  async load() {
    clearTimeout(this.timer);
    try {
      [this.data, this.notify] = await Promise.all([api("/api/tasks"), api("/api/notifications")]);
    } catch (e) {
      return;
    }
    if (!this.lib) await this.loadMore();
    if (location.hash.startsWith("#/tasks")) {
      if (!this.editing()) this.render();
      this.timer = setTimeout(() => this.load(), 4e3);
    }
  },
  editing() {
    var _a, _b;
    return !!((_b = (_a = document.activeElement) == null ? void 0 : _a.closest) == null ? void 0 : _b.call(_a, "#tasks-list select, #tasks-list input"));
  },
  async save(id, patch) {
    try {
      this.data = await api(`/api/tasks/${id}`, { method: "PUT", body: patch });
      this.render();
    } catch (err) {
      toast(err.message);
      this.load();
    }
  },
  async runNow(id) {
    try {
      await api(`/api/tasks/${id}/run`, { method: "POST" });
      toast("Started");
    } catch (err) {
      toast(err.message);
    }
    setTimeout(() => this.load(), 600);
  },
  render() {
    const { tasks, library, sources } = this.data;
    $("#tasks-summary").textContent = library.titles ? `${plural(library.titles, "title")} in your library, ${library.scanned} scanned.` : "Run a library refresh to count your titles.";
    $("#tasks-list").replaceChildren(...tasks.map((t) => {
      const status = [];
      if (t.running) status.push(h("span", { class: "busy" }, "Running now…"));
      else if (t.last_run) status.push(h(
        "span",
        { class: t.last_status === "error" ? "error" : "" },
        `${t.last_status === "error" ? "Failed" : "Last run"} ${ago(t.last_run)}${t.last_duration != null ? ` (${Math.round(t.last_duration)} s)` : ""}`
      ));
      else status.push(h("span", {}, "Hasn't run yet"));
      if (t.last_result) status.push(h("span", { class: t.last_status === "error" ? "error" : "" }, t.last_result));
      if (t.enabled && t.next_run && !t.running) status.push(h("span", {}, `Next run ${inTime(t.next_run)}`));
      if (!t.enabled) status.push(h("span", {}, "Off: only runs when you press Run now"));
      const opts = [
        h("label", {}, h("input", { type: "checkbox", checked: t.enabled, onchange: (e) => this.save(t.id, { enabled: e.target.checked }) }), "Run automatically"),
        h(
          "select",
          { "aria-label": "How often", onchange: (e) => this.save(t.id, { interval_hours: Number(e.target.value) }) },
          ...(INTERVALS.some(([v]) => v === t.interval_hours) ? INTERVALS : [...INTERVALS, [t.interval_hours, `Every ${t.interval_hours} h`]]).map(([v, label]) => h("option", { value: v, selected: v === t.interval_hours }, label))
        )
      ];
      const extra = [];
      if (t.id === "refresh") {
        extra.push(h(
          "div",
          { class: "task-sources", role: "group", "aria-label": "Sources to refresh" },
          ...sources.map((s) => h("label", {}, h("input", { type: "checkbox", checked: t.sources.includes(s.id), onchange: (e) => {
            const on = new Set(t.sources);
            e.target.checked ? on.add(s.id) : on.delete(s.id);
            this.save(t.id, { sources: [...on] });
          } }), s.name))
        ));
        extra.push(h("div", { class: "task-opts" }, h("label", {}, h("input", {
          type: "checkbox",
          checked: t.scan_new,
          onchange: (e) => this.save(t.id, { scan_new: e.target.checked })
        }), "Queue scans for titles that haven't been scanned")));
      }
      return h(
        "article",
        { class: "task" },
        h(
          "div",
          { class: "task-top" },
          h("div", {}, h("h2", {}, t.name), h("p", {}, t.description)),
          h("button", { class: "btn subtle", type: "button", disabled: t.running, onclick: () => this.runNow(t.id) }, t.running ? "Running…" : "Run now")
        ),
        h("div", { class: "task-opts" }, ...opts),
        ...extra,
        h("div", { class: "task-status" }, ...status)
      );
    }), this.renderDetails(), this.renderTidy(), this.renderNotify());
  },
  async loadMore() {
    try {
      this.lib = await api("/api/library/settings");
      this.batches = await api("/api/rename/batches");
    } catch (e) {
    }
  },
  renderDetails() {
    const s = this.lib || { provider: "auto", has_key: false };
    const key = h("input", { type: "password", placeholder: s.has_key ? "A key is saved. Paste a new one to replace it." : "Paste your TMDB key (optional)", autocomplete: "off", spellcheck: "false", "aria-label": "TMDB API key" });
    key.addEventListener("change", async () => {
      if (!key.value.trim()) return;
      try {
        this.lib = await api("/api/library/settings", { method: "PUT", body: { tmdb_key: key.value.trim() } });
        toast("Key saved");
      } catch (e) {
        toast(e.message);
      }
      this.render();
    });
    return h(
      "article",
      { class: "task" },
      h(
        "div",
        { class: "task-top" },
        h(
          "div",
          {},
          h("h2", {}, "Movie and show details"),
          h("p", {}, "Where summaries, genres and posters come from. Automatic uses TMDB when you add a free key, and the free Wikipedia and TVmaze services otherwise. Details in .nfo files next to your videos always win.")
        ),
        h("button", { class: "btn subtle", type: "button", onclick: async () => {
          try {
            toast((await api("/api/library/settings/test", { method: "POST" })).message);
          } catch (e) {
            toast(e.message);
          }
        } }, "Test")
      ),
      h(
        "div",
        { class: "task-opts" },
        h(
          "select",
          { "aria-label": "Source of details", onchange: async (e) => {
            try {
              this.lib = await api("/api/library/settings", { method: "PUT", body: { provider: e.target.value } });
            } catch (err) {
              toast(err.message);
            }
            this.render();
          } },
          h("option", { value: "auto", selected: s.provider === "auto" }, "Automatic"),
          h("option", { value: "tmdb", selected: s.provider === "tmdb" }, "TMDB only"),
          h("option", { value: "none", selected: s.provider === "none" }, "Off: use file names and .nfo files only")
        ),
        key
      ),
      h("p", { class: "hint" }, "Get a free key at themoviedb.org → Settings → API. The key stays on your server.")
    );
  },
  tidy: { source: "", layout: "flat", matched: true, plan: null, picked: /* @__PURE__ */ new Set(), busy: false, result: null },
  renderTidy() {
    var _a;
    const t = this.tidy, locals = (this.data.sources || []).filter((s) => s.type === "local");
    if (!t.source || !locals.some((s) => s.id === t.source)) t.source = ((_a = locals[0]) == null ? void 0 : _a.id) || "";
    const preview = async () => {
      t.busy = true;
      t.result = null;
      this.render();
      try {
        const q = new URLSearchParams({ source_id: t.source, only_matched: t.matched, layout: t.layout });
        t.plan = await api(`/api/rename/plan?${q}`);
        t.picked = new Set(t.plan.groups.map((g) => g.id));
      } catch (e) {
        toast(e.message);
        t.plan = null;
      }
      t.busy = false;
      this.render();
    };
    const apply = async () => {
      if (!confirm(`Rename ${plural(t.picked.size, "group")} of files now? You can undo it right afterwards.`)) return;
      t.busy = true;
      this.render();
      try {
        t.result = await api("/api/rename/apply", { method: "POST", body: { source_id: t.source, ids: [...t.picked], only_matched: t.matched, layout: t.layout } });
        t.plan = null;
        await this.loadMore();
      } catch (e) {
        toast(e.message);
      }
      t.busy = false;
      this.render();
    };
    const undo = async (batch) => {
      if (!confirm("Put every file from that rename back where it was?")) return;
      try {
        const r = await api(`/api/rename/undo/${batch}`, { method: "POST" });
        toast(r.problems.length ? `Undone, but: ${r.problems[0]}` : "Everything is back as it was");
        await this.loadMore();
      } catch (e) {
        toast(e.message);
      }
      this.render();
    };
    const last = (this.batches || []).find((b) => !b.undone);
    const sel = h(
      "select",
      { "aria-label": "Folder to tidy", onchange: (e) => {
        t.source = e.target.value;
        t.plan = null;
        this.render();
      } },
      ...locals.map((s) => h("option", { value: s.id, selected: s.id === t.source }, s.name))
    );
    const layout = h(
      "select",
      { "aria-label": "Layout", onchange: (e) => {
        t.layout = e.target.value;
        t.plan = null;
        this.render();
      } },
      h("option", { value: "flat", selected: t.layout === "flat" }, "All files directly in the folder"),
      h("option", { value: "folders", selected: t.layout === "folders" }, "One folder per movie, show and season")
    );
    const plan = t.plan;
    return h(
      "article",
      { class: "task" },
      h(
        "div",
        { class: "task-top" },
        h(
          "div",
          {},
          h("h2", {}, "Tidy file names"),
          h("p", {}, "Renames your files to Title (Year).mkv and Show (Year) - S01E02 - Episode.mkv, using the details above. Nothing changes until you press Rename, and every rename can be undone. Hush never overwrites a file.")
        ),
        h("button", { class: "btn subtle", type: "button", disabled: !t.source || t.busy, onclick: preview }, t.busy && !plan ? "Working…" : "Preview")
      ),
      locals.length ? h(
        "div",
        { class: "task-opts" },
        sel,
        layout,
        h("label", {}, h("input", { type: "checkbox", checked: t.matched, onchange: (e) => {
          t.matched = e.target.checked;
          t.plan = null;
          this.render();
        } }), "Only titles with a confirmed match")
      ) : h("p", { class: "hint" }, "Renaming works on Local sources, which are folders on the server. Add one first."),
      plan ? h(
        "div",
        {},
        h("p", { class: "hint" }, `${plural(plan.groups.length, "group")} to rename${plan.tidy ? `, ${plan.tidy} already tidy` : ""}${plan.skipped.length ? `, ${plan.skipped.length} skipped` : ""}.`),
        plan.groups.length ? h("ul", { class: "tidy-list" }, ...plan.groups.map((g) => h(
          "li",
          {},
          h("input", { type: "checkbox", checked: t.picked.has(g.id), "aria-label": g.label, onchange: (e) => {
            e.target.checked ? t.picked.add(g.id) : t.picked.delete(g.id);
            this.render();
          } }),
          h(
            "div",
            {},
            h("strong", {}, g.label),
            ...g.items.slice(0, 6).map((i) => h("div", {}, h("div", { class: "from" }, i.from.split("/").slice(-1)[0]), h("div", { class: "to" }, "→ " + i.to.split("/").slice(-1)[0]))),
            g.items.length > 6 ? h("div", { class: "from" }, `and ${g.items.length - 6} more`) : null
          )
        ))) : null,
        plan.skipped.length ? h("details", {}, h("summary", { class: "hint" }, "Skipped"), h("ul", { class: "tidy-list" }, ...plan.skipped.map((s) => h("li", {}, h("span"), h("div", {}, s.name, h("div", { class: "from" }, s.reason)))))) : null,
        plan.groups.length ? h("div", { class: "task-opts" }, h("button", { class: "btn primary", type: "button", disabled: !t.picked.size || t.busy, onclick: apply }, `Rename ${plural(t.picked.size, "group")}`)) : null
      ) : null,
      t.result ? h("p", { class: t.result.failed.length ? "error" : "hint" }, `Renamed ${plural(t.result.renamed, "title")}.${t.result.failed.length ? ` ${t.result.failed.length} failed: ${t.result.failed[0].reason}` : ""}`) : null,
      last ? h("div", { class: "task-opts" }, h("button", { class: "btn ghost", type: "button", onclick: () => undo(last.batch) }, `Undo the last rename (${plural(last.moves, "file move")})`)) : null
    );
  },
  async saveNotify(patch) {
    try {
      this.notify = await api("/api/notifications", { method: "PUT", body: patch });
      toast("Saved");
    } catch (err) {
      toast(err.message);
    }
    this.render();
  },
  renderNotify() {
    const n = this.notify;
    const url = h("input", { type: "text", value: n.url, placeholder: "https://ntfy.sh/my-hush  (or any webhook address)", spellcheck: "false", "aria-label": "Webhook address" });
    url.addEventListener("change", () => this.saveNotify({ url: url.value }));
    return h(
      "article",
      { class: "task" },
      h(
        "div",
        { class: "task-top" },
        h(
          "div",
          {},
          h("h2", {}, "Notifications"),
          h("p", {}, "Get a message when a batch of scans finishes or a task fails. Works with ntfy, Gotify, Home Assistant and other webhooks.")
        ),
        h("button", { class: "btn subtle", type: "button", onclick: async () => {
          try {
            await api("/api/notifications/test", { method: "POST" });
            toast("Test sent");
          } catch (err) {
            toast(err.message);
          }
        } }, "Send a test")
      ),
      url,
      h(
        "div",
        { class: "task-opts" },
        h(
          "select",
          { "aria-label": "Message format", onchange: (e) => this.saveNotify({ format: e.target.value }) },
          h("option", { value: "text", selected: n.format === "text" }, "Plain text (ntfy, Gotify)"),
          h("option", { value: "json", selected: n.format === "json" }, "JSON (Home Assistant, others)")
        ),
        h("label", {}, h("input", { type: "checkbox", checked: n.on_scans_done, onchange: (e) => this.saveNotify({ on_scans_done: e.target.checked }) }), "Scans finished"),
        h("label", {}, h("input", { type: "checkbox", checked: n.on_failure, onchange: (e) => this.saveNotify({ on_failure: e.target.checked }) }), "A task failed")
      ),
      n.last_error ? h("div", { class: "task-status" }, h("span", { class: "error" }, `The last message didn't go through: ${n.last_error}`)) : null
    );
  }
};
const video = $("#video");
const Player = {
  src: null,
  item: null,
  info: null,
  mode: "direct",
  offset: 0,
  duration: 0,
  filter: null,
  ranges: [],
  cats: /* @__PURE__ */ new Set(),
  filterOn: true,
  bleep: false,
  audioIndex: null,
  subCues: null,
  job: null,
  markStart: null,
  selected: null,
  pendingSeek: null,
  /* ---------- loading ---------- */
  async open(sourceId, itemId, opts = {}) {
    var _a, _b, _c;
    const keepMini = !!opts.mini;
    const libraryWasHidden = $("#library").hidden;
    this.close(false);
    if (keepMini) $("#library").hidden = libraryWasHidden;
    this.src = sourceId;
    this.item = itemId;
    this.triedTranscode = false;
    const token = this.openToken = (this.openToken || 0) + 1;
    (_a = this.openAbort) == null ? void 0 : _a.abort();
    const abort = this.openAbort = new AbortController();
    Queue.sync(sourceId, itemId);
    this.chan = ((_b = Queue.list[Queue.pos]) == null ? void 0 : _b.chan) || null;
    this.reported = null;
    if (!opts.alt || !this.altTried) this.altTried = /* @__PURE__ */ new Set();
    if (this.chan) this.altTried.add(this.chan);
    const back = (S.libraryHash || "").replace(/^#\/?/, "").split("/")[0];
    $("#back-btn").textContent = { live: "Back to Live TV", movies: "Back to Movies", title: "Back to Movies", shows: "Back to TV shows", show: "Back to the show", b: "Back to the folder" }[back] || "Back to library";
    $("#guide-btn").hidden = !this.chan;
    guide.close();
    if (this.chan) Queue.banner();
    $("#player").hidden = false;
    if (!keepMini) {
      $("#library").hidden = true;
      document.body.style.overflow = "hidden";
    }
    if (keepMini) {
      this.message("Opening…");
      this.minimize();
    } else {
      const nm = splitTags(((_c = Queue.list[Queue.pos]) == null ? void 0 : _c.title) || "").title;
      WaitScreen.start(this.chan ? `Tuning in${nm ? " to " + nm : ""}` : `Opening${nm ? " " + nm : ""}`, this.chan && (isKids() || this.filterOn) ? 18 : 8);
    }
    let info;
    try {
      info = await api(`/api/media/${sourceId}/${itemId}?hevc=${HEVC}`, { signal: abort.signal });
    } catch (err) {
      if (token !== this.openToken) return;
      this.report(false);
      if (this.chan && await this.tryAlternate()) return;
      this.message(err.message, true);
      return;
    }
    if (token !== this.openToken) return;
    this.info = info;
    if (this.mini) this.miniTitle();
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
    $("#autoplay-toggle").checked = autoplay();
    const resumeAt = info.resume && !info.resume.finished && info.resume.position > 20 ? info.resume.position : 0;
    this.startAt(resumeAt, true);
    if (resumeAt) this.showResume(resumeAt);
    if (autoplay()) {
      video.play().catch(() => this.message("Press play to start"));
    }
    if (this.chan) Queue.warm();
    await this.loadFilter();
    if (token !== this.openToken) return;
    this.job = info.job;
    if (this.job) Jobs.poll();
    this.renderPanel();
  },
  close(goBack = true) {
    WaitScreen.stop();
    this.releaseLiveFilter();
    this.endMini();
    Progress.save(true);
    Progress.disarm();
    $("#resume-chip").hidden = true;
    video.pause();
    video.removeAttribute("src");
    video.load();
    this.subCues = null;
    $("#subs").replaceChildren();
    this.filter = null;
    this.ranges = [];
    this.markStart = null;
    this.selected = null;
    $("#player").classList.remove("playing", "idle");
    $("#player").hidden = true;
    $("#library").hidden = false;
    document.body.style.overflow = "";
    document.title = "Hush";
    if (document.fullscreenElement && !IS_TV_DEVICE) document.exitFullscreen();
    if (goBack) go(S.libraryHash || "#/");
  },
  setupTracks() {
    const p = this.info.probe;
    const aSel = $("#audio-select");
    aSel.replaceChildren(...p.audio.map((a) => h("option", { value: a.index }, a.label || `Track ${a.index}`)));
    aSel.disabled = p.audio.length < 2;
    this.audioIndex = p.audio.length ? p.audio[0].index : null;
    const sSel = $("#sub-select");
    sSel.replaceChildren(
      h("option", { value: "" }, "Off"),
      ...p.subtitles.map((s) => h("option", { value: s.index }, s.label || `Subtitles ${s.index}`))
    );
    api(`/api/sidecars/${this.src}/${this.item}`).then((list) => {
      for (const s of list) sSel.append(h("option", { value: s.id }, s.label));
    }).catch(() => {
    });
  },
  streamUrl(start2) {
    const q = new URLSearchParams({ start: start2.toFixed(3) });
    if (this.audioIndex != null) q.set("audio", this.audioIndex);
    if (this.mode !== "direct") q.set("mode", this.mode);
    return `/api/stream/${this.src}/${this.item}?${q}`;
  },
  hls: IS_WEBKIT || IS_LG,
  hlsSig: "",
  hlsTimer: null,
  /** True when the server (not the browser) is muting the filtered words. */
  serverMuted() {
    return this.hls && this.mode !== "direct" || this.liveFiltered;
  },
  /** Live channels are filtered by their captions on the server, about 10 seconds behind the broadcast. */
  wantsLiveFilter() {
    var _a;
    return !!(((_a = this.info) == null ? void 0 : _a.live) && this.chan && (isKids() || this.filterOn));
  },
  async openLiveFilter() {
    const body = { src: this.src, item: this.item, cats: [...this.cats].join(","), tab: TAB };
    const r = await api("/api/livefilter/open", { method: "POST", body });
    this.liveSid = r.sid;
    this.watchLiveFilter(r.sid, r.status);
    return this.hls ? r.hls : r.mp4;
  },
  /** Tells the person what the filter found, once: no captions means nothing can be filtered on that channel. */
  watchLiveFilter(sid, first) {
    clearTimeout(this.lfTimer);
    let told = false, warned = false;
    const look = async (st) => {
      if (this.liveSid !== sid) return;
      try {
        st = st || await api(`/api/livefilter/${sid}/status`);
      } catch (e) {
        return;
      }
      if (st.state === "nocaptions" && !told && !isKids()) {
        told = true;
        toast("This channel has no captions and can't be listened to, so the language filter can't work on it. It is playing unfiltered.");
      } else if (st.mode === "asr" && !told) {
        told = true;
        toast("No captions on this channel, so Hush is listening to it instead (about 10 seconds behind live; a little less precise).");
      } else if (st.mode === "captions" && !told) {
        told = true;
        toast("Language filter on: captions found (about 10 seconds behind live).");
      }
      if (st.behind && !warned) {
        warned = true;
        toast("The filter fell behind on this channel for a moment, so a few words may not have been filtered.");
      }
      this.lfTimer = setTimeout(() => look(), told ? 3e4 : 6e3);
    };
    this.lfTimer = setTimeout(() => look(first), 6e3);
  },
  releaseLiveFilter() {
    clearTimeout(this.lfTimer);
    if (this.liveSid) {
      try {
        navigator.sendBeacon("/api/livefilter/release", new Blob([JSON.stringify({ tab: TAB })], { type: "application/json" }));
      } catch (e) {
      }
    }
    this.liveSid = null;
    this.liveFiltered = false;
  },
  sig() {
    return `${+this.filterOn}|${[...this.cats].sort()}|${this.ranges.map((r) => `${r.id}:${r.start}:${r.end}:${+r.enabled}`).join(",")}`;
  },
  hlsUrl(start2) {
    this.hlsSig = this.sig();
    const q = new URLSearchParams({ start: start2.toFixed(3), tab: TAB, filter: +this.filterOn, cats: [...this.cats].join(",") });
    if (this.audioIndex != null) q.set("audio", this.audioIndex);
    q.set("mode", this.mode);
    return `/api/hls/start/${this.src}/${this.item}?${q}`;
  },
  /** The filter or its words changed: rebuild the stream so the server mutes the right moments. */
  queueHlsRefresh(delay = 1500) {
    if (!this.serverMuted() || !this.info || this.info.live) return;
    clearTimeout(this.hlsTimer);
    this.hlsTimer = setTimeout(() => {
      if (this.serverMuted() && this.sig() !== this.hlsSig) this.startAt(this.now()).then(() => video.play().catch(() => {
      }));
    }, delay);
  },
  async startAt(t, initial = false) {
    var _a;
    const wasPlaying = !video.paused || initial;
    const tok = this.openToken;
    if (this.mode === "direct") {
      if (initial) {
        video.src = `/api/raw/${this.src}/${this.item}`;
        if (t > 0.2) video.addEventListener("loadedmetadata", () => {
          video.currentTime = t;
        }, { once: true });
      } else video.currentTime = t;
      this.offset = 0;
    } else {
      let landing = t;
      if (this.mode === "remux" && t > 0.2) {
        try {
          landing = (await api(`/api/seekpoint/${this.src}/${this.item}?t=${t}&mode=remux`)).start;
        } catch (e) {
        }
      }
      this.offset = landing;
      this.pendingSeek = t - landing > 0.3 ? t - landing : null;
      let url;
      if (this.wantsLiveFilter()) {
        WaitScreen.label("Starting the language filter", 18);
        this.message("Starting the language filter (about 15 seconds)…");
        try {
          url = await this.openLiveFilter();
          this.liveFiltered = true;
        } catch (err) {
          if (tok === this.openToken) this.message(err.message, true);
          return;
        }
      } else {
        this.releaseLiveFilter();
        url = this.hls ? this.hlsUrl(landing) : this.streamUrl(landing);
      }
      if (IS_LG && this.hls && !this.liveFiltered) {
        try {
          const r = await fetch(url, { credentials: "same-origin" });
          if (r.ok && r.url) url = r.url;
        } catch (e) {
        }
      }
      if (tok !== this.openToken) return;
      video.src = url;
    }
    this.message(this.serverMuted() || ((_a = this.info) == null ? void 0 : _a.live) ? "Preparing the stream…" : null);
    this.Audio.reset();
    if (wasPlaying && !initial) video.play().catch(() => {
    });
  },
  now() {
    return this.offset + (video.currentTime || 0);
  },
  seek(t) {
    var _a;
    if ((_a = this.info) == null ? void 0 : _a.live) return;
    this.startAt(Math.max(0, Math.min(t, (this.duration || 1e9) - 0.5)));
  },
  async loadFilter() {
    try {
      this.filter = await api(`/api/filters/${this.info.media_key}`);
      this.ranges = this.filter.ranges;
    } catch (err) {
      this.filter = null;
      this.ranges = [];
      if (err.status !== 404) toast(err.message);
    }
    const saved = store.get(pk("cats"), null);
    const cats = this.categories();
    this.cats = isKids() ? new Set(cats.map((c) => c.id)) : new Set(cats.filter((c) => saved ? saved.includes(c.id) : c.default).map((c) => c.id));
    this.renderMarks();
    this.Audio.reset();
  },
  categories() {
    var _a;
    return ((_a = S.config) == null ? void 0 : _a.categories) || [];
  },
  active(r) {
    return r.enabled !== false && (r.source === "manual" || this.cats.has(r.category));
  },
  activeRanges() {
    return this.ranges.filter((r) => this.active(r));
  },
  rangeAt(t) {
    return this.ranges.find((r) => this.active(r) && t >= r.start && t < r.end);
  },
  /* Overlapping ranges are merged so one range's end never unmutes another. */
  intervals() {
    if (this._iv) return this._iv;
    const out = [];
    for (const r of this.activeRanges().sort((a, b) => a.start - b.start)) {
      const last = out[out.length - 1];
      if (last && r.start <= last.end + 0.02) last.end = Math.max(last.end, r.end);
      else out.push({ start: r.start, end: r.end });
    }
    out.forEach((iv) => iv.id = iv.start.toFixed(3));
    return this._iv = out;
  },
  intervalAt(t) {
    return this.intervals().find((iv) => t >= iv.start && t < iv.end);
  },
  /* ---------- the audio filter ---------- */
  Audio: {
    ctx: null,
    mute: null,
    master: null,
    toneGain: null,
    scheduled: /* @__PURE__ */ new Set(),
    timer: null,
    fallback: false,
    ensure() {
      var _a;
      if (this.ctx || this.fallback) {
        (_a = this.ctx) == null ? void 0 : _a.resume();
        return;
      }
      if (IS_WEBKIT || IS_LG) this.fallback = true;
      else try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" });
        const source = ctx.createMediaElementSource(video);
        this.mute = ctx.createGain();
        this.master = ctx.createGain();
        this.toneGain = ctx.createGain();
        this.toneGain.gain.value = 0;
        const osc = ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.value = 660;
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
    volume(v) {
      if (this.master) this.master.gain.value = v;
      else video.volume = v;
    },
    set(muted, at) {
      if (Player.serverMuted()) {
        video.muted = false;
        return;
      }
      if (!this.ctx) {
        video.muted = muted;
        return;
      }
      const when2 = at != null ? at : this.ctx.currentTime;
      this.mute.gain.setTargetAtTime(muted ? 0 : 1, when2, 4e-3);
      this.toneGain.gain.setTargetAtTime(muted && Player.bleep ? 0.12 : 0, when2, 4e-3);
    },
    reset() {
      if (Player.serverMuted()) {
        Player.queueHlsRefresh();
        return;
      }
      Player._iv = null;
      this.scheduled.clear();
      if (this.ctx) {
        const now = this.ctx.currentTime;
        this.mute.gain.cancelScheduledValues(now);
        this.toneGain.gain.cancelScheduledValues(now);
      }
      this.set(Player.filterOn && !!Player.intervalAt(Player.now()) && !video.paused);
    },
    tick() {
      const P = Player;
      if (P.serverMuted()) return;
      if (!P.filterOn || video.paused || !P.intervals().length) {
        if (this.scheduled.size || (this.ctx ? this.mute.gain.value < 1 : video.muted)) {
          this.scheduled.clear();
          this.set(false);
        }
        return;
      }
      const now = P.now(), rate = video.playbackRate || 1;
      const inside = P.intervalAt(now);
      if (!this.ctx) {
        video.muted = !!inside;
        return;
      }
      if (inside && !this.scheduled.has(inside.id) && this.mute.gain.value > 0.5) {
        this.set(true);
        this.set(false, this.ctx.currentTime + (inside.end - now) / rate);
        this.scheduled.add(inside.id);
      }
      for (const r of P.intervals()) {
        if (r.start <= now || r.start > now + 0.2 || this.scheduled.has(r.id)) continue;
        const t0 = this.ctx.currentTime + (r.start - now) / rate;
        this.set(true, t0);
        this.set(false, this.ctx.currentTime + (r.end - now) / rate);
        this.scheduled.add(r.id);
      }
    }
  },
  /* ---------- UI ---------- */
  /* ---------- mini player: keep watching while you browse ---------- */
  mini: false,
  forceMini: false,
  keepPlaying() {
    const force = this.forceMini;
    this.forceMini = false;
    return force || store.get("mini", true) && !!video.currentSrc && !video.paused && !video.ended && !!this.info;
  },
  /** Shrink to the slot above the sidebar (or the upper-left corner when there is no sidebar). */
  minimize() {
    this.mini = true;
    const p = $("#player");
    p.classList.add("mini", "playing-keep");
    p.classList.toggle("playing", !video.paused);
    document.body.style.overflow = "";
    guide.close();
    if (!$("#panel").hidden) togglePanel(false);
    $("#settings").hidden = true;
    $("#resume-chip").hidden = true;
    this.miniTitle();
    const many = Queue.list.length > 1;
    $("#mini-prev").hidden = $("#mini-next").hidden = !many;
    this.placeMini();
  },
  miniTitle() {
    var _a, _b, _c;
    const queued = (_a = Queue.list[Queue.pos]) == null ? void 0 : _a.title;
    const name = this.chan ? queued || ((_b = this.info) == null ? void 0 : _b.title) || "" : ((_c = this.info) == null ? void 0 : _c.title) || queued || "";
    $("#mini-title").textContent = this.chan ? splitTags(name).title : name;
    $("#mini-title").title = name;
  },
  placeMini() {
    var _a;
    if (!this.mini) return;
    const p = $("#player"), slot = $("#mini-slot");
    if (document.documentElement.classList.contains("tv")) {
      slot.hidden = true;
      slot.style.height = "";
      Object.assign(p.style, { left: "auto", top: "auto", right: "2.5vw", bottom: "4vh", width: "22vw" });
      return;
    }
    const rail = $(".rail");
    const sidebar = !$("#library").hidden && rail && rail.offsetParent !== null && window.innerWidth > 760;
    let left = 16, top = (((_a = $(".topbar")) == null ? void 0 : _a.offsetHeight) || 48) + 10, width = 240;
    if (sidebar) {
      const r = rail.getBoundingClientRect();
      left = r.left + 16;
      top = r.top + 20;
      width = Math.max(160, Math.round(r.width - 32));
      slot.hidden = false;
      slot.style.height = `${Math.round(width * 9 / 16)}px`;
    } else {
      slot.hidden = true;
      slot.style.height = "";
    }
    Object.assign(p.style, { left: `${left}px`, top: `${top}px`, width: `${width}px`, right: "auto", bottom: "auto" });
  },
  expand() {
    this.mini = false;
    const p = $("#player");
    p.classList.remove("mini", "playing-keep");
    Object.assign(p.style, { left: "", top: "", width: "", right: "", bottom: "" });
    $("#mini-slot").hidden = true;
    $("#library").hidden = true;
    $("#tasks").hidden = true;
    $("#prefs").hidden = true;
    document.body.style.overflow = "hidden";
    const back = (S.libraryHash || "").replace(/^#\/?/, "").split("/")[0];
    $("#back-btn").textContent = { live: "Back to Live TV", movies: "Back to Movies", title: "Back to Movies", shows: "Back to TV shows", show: "Back to the show", b: "Back to the folder" }[back] || "Back to library";
    if (this.chan) {
      $("#guide-btn").hidden = false;
      Queue.banner();
    }
  },
  /** Leave mini mode without touching what is playing (used when the player closes or is replaced). */
  endMini() {
    if (!this.mini) return;
    this.mini = false;
    const p = $("#player");
    p.classList.remove("mini", "playing-keep");
    Object.assign(p.style, { left: "", top: "", width: "", right: "", bottom: "" });
    $("#mini-slot").hidden = true;
  },
  showResume(at) {
    const chip = $("#resume-chip");
    $("#resume-text").textContent = `Resumed at ${fmt(at)}`;
    chip.hidden = false;
    clearTimeout(this.chipTimer);
    this.chipTimer = setTimeout(() => {
      chip.hidden = true;
    }, 9e3);
  },
  /** Tell the server whether a Live TV channel played, so dead ones can be hidden. */
  /** A channel that will not play: try another source of the same channel, if the playlists have one. */
  async tryAlternate() {
    try {
      const list = await api(`/api/live/alternates/${this.chan}`);
      const next = list.find((a) => !this.altTried.has(a.key));
      if (!next) return false;
      const cur = Queue.list[Queue.pos];
      Queue.list[Queue.pos] = { ...cur, item: next.item_id, chan: next.key };
      this.message("That source did not answer. Trying another…");
      this.open("url", next.item_id, { alt: true, mini: this.mini });
      return true;
    } catch (e) {
      return false;
    }
  },
  /** Sound but no picture (a TV that cannot show the copied video): after a few seconds, say so and switch to the compatible stream. */
  watchPicture() {
    clearTimeout(this.pictureTimer);
    const key = `${this.src}/${this.item}/${this.mode}`;
    this.pictureTimer = setTimeout(() => {
      var _a, _b, _c, _d;
      const p = (_a = this.info) == null ? void 0 : _a.probe;
      if (this.mini || video.paused || !((_b = p == null ? void 0 : p.video) == null ? void 0 : _b.length) || `${this.src}/${this.item}/${this.mode}` !== key) return;
      let frames = null;
      try {
        const q = (_c = video.getVideoPlaybackQuality) == null ? void 0 : _c.call(video);
        frames = q ? q.totalVideoFrames : null;
      } catch (e) {
      }
      if (video.videoWidth > 0 && (frames === null || frames > 0)) return;
      const box = video.getBoundingClientRect();
      (_d = window.hushReport) == null ? void 0 : _d.call(window, { kind: "no-picture", message: `playing without a picture (mode ${this.mode}${this.hls ? ", hls" : ""}, codec ${p.video[0].codec}, video ${video.videoWidth}x${video.videoHeight}, shown ${Math.round(box.width)}x${Math.round(box.height)}, frames ${frames}, readyState ${video.readyState})` });
      if (this.mode === "remux" && !this.triedTranscode) {
        this.triedTranscode = true;
        this.mode = "transcode";
        this.message("No picture. Switching to a compatible stream…");
        this.startAt(this.now()).then(() => video.play().catch(() => {
        }));
      }
    }, 5e3);
  },
  report(ok) {
    if (!this.chan || this.reported === ok) return;
    this.reported = ok;
    api(`/api/live/channels/${this.chan}/report`, { method: "POST", body: { ok } }).catch(() => {
    });
  },
  message(text, isError = false) {
    if (isError) WaitScreen.stop();
    const m = $("#stage-msg");
    m.hidden = !text;
    m.textContent = text || "";
    m.classList.toggle("error", isError);
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
      style: `left:${r.start / d * 100}%;width:${Math.max(0.15, (r.end - r.start) / d * 100)}%`
    })));
  },
  frame() {
    var _a;
    if (this.mini) return;
    const t = this.now(), d = this.duration || 1;
    $("#t-now").textContent = fmt(t);
    $("#tl-played").style.width = `${Math.min(100, t / d * 100)}%`;
    $("#tl-head").style.left = `${Math.min(100, t / d * 100)}%`;
    $("#timeline").setAttribute("aria-valuenow", Math.round(t));
    $("#timeline").setAttribute("aria-valuetext", `${fmt(t)} of ${fmt(d)}`);
    if (video.buffered.length) {
      const end = this.offset + video.buffered.end(video.buffered.length - 1);
      $("#tl-buffer").style.width = `${Math.min(100, end / d * 100)}%`;
    }
    const inside = this.filterOn && !video.paused ? this.rangeAt(t) : null;
    $("#filter-btn").classList.toggle("muting", !!inside);
    this.renderSubs(t);
    const cur = $(".range.current");
    const id = inside == null ? void 0 : inside.id;
    if (cur && cur.dataset.id !== id) cur.classList.remove("current");
    if (id) (_a = $(`.range[data-id="${id}"]`)) == null ? void 0 : _a.classList.add("current");
  },
  /* ---------- subtitles (censored on screen too) ---------- */
  async loadSubs(track) {
    this.subCues = null;
    $("#subs").replaceChildren();
    if (!track) return;
    try {
      const vtt = await api(`/api/subtitle/${this.src}/${this.item}/${track}`);
      this.subCues = parseVTT(vtt);
    } catch (err) {
      toast(`Subtitles couldn't load: ${err.message}`);
    }
  },
  renderSubs(t) {
    var _a;
    if (!this.subCues) return;
    const cue = this.subCues.find((c) => t >= c.start && t <= c.end);
    const box = $("#subs");
    if ((box.dataset.cue || "") === String((_a = cue == null ? void 0 : cue.start) != null ? _a : "") && box.dataset.f === String(this.filterOn)) return;
    box.dataset.cue = cue ? String(cue.start) : "";
    box.dataset.f = String(this.filterOn);
    if (!cue) {
      box.replaceChildren();
      return;
    }
    const words = /* @__PURE__ */ new Set();
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
    var _a, _b, _c, _d;
    const status = $("#panel-status");
    const hasFilter = !!this.filter;
    const running = this.job && (this.job.status === "running" || this.job.status === "queued");
    $("#cats").hidden = !hasFilter;
    $("#range-tools").hidden = !hasFilter;
    $("#panel-foot").hidden = !hasFilter;
    const eng = ((_a = S.config) == null ? void 0 : _a.engines) || {};
    if ((_b = this.info) == null ? void 0 : _b.live) {
      status.replaceChildren(h("p", {}, "This is a live stream, so it can't be scanned or filtered. It plays as it is."));
      $("#cats").hidden = $("#range-tools").hidden = $("#panel-foot").hidden = true;
      $("#ranges").replaceChildren();
      return;
    }
    if (running) {
      status.replaceChildren(
        h("p", {}, `Scanning this title. ${jobText(this.job)}. You can keep watching; the filter turns on when it's ready.`),
        h("div", { class: "progress" }, h("i", { style: `width:${Math.round(this.job.progress * 100)}%` })),
        h("div", { class: "actions" }, h("button", { class: "btn ghost", type: "button", onclick: () => this.cancelScan() }, "Cancel scan"))
      );
    } else if (!hasFilter) {
      const failed = ((_c = this.job) == null ? void 0 : _c.status) === "error" ? h("p", { class: "error" }, jobText(this.job)) : null;
      status.replaceChildren(
        h("p", {}, eng.whisper ? "This title hasn't been scanned. Hush listens to the dialogue and marks every word on your list, then mutes those moments while you watch." : "This title hasn't been scanned. Hush reads the subtitle track, marks every word on your list, then mutes those moments while you watch."),
        failed,
        h(
          "div",
          { class: "actions" },
          h("button", { class: "btn primary", type: "button", onclick: () => this.scan() }, "Scan this title"),
          eng.whisper && ((_d = this.info) == null ? void 0 : _d.probe.subtitles.length) ? h("button", { class: "btn ghost", type: "button", onclick: () => this.scan("subtitles") }, "Quick scan from subtitles") : null
        ),
        !eng.whisper ? h("p", { class: "hint" }, "For titles without subtitles, install faster-whisper on the server to scan the audio itself.") : null,
        h(
          "div",
          { class: "actions" },
          h(
            "label",
            { class: "btn ghost", style: "display:inline-flex" },
            "Load a filter file",
            h("input", { type: "file", accept: ".json,application/json", hidden: true, onchange: (e) => this.importFile(e.target.files[0]) })
          )
        )
      );
    } else {
      const n = this.activeRanges().length;
      const how = { whisper: "from the dialogue audio", subtitles: "from the subtitles", manual: "by hand" }[this.filter.engine] || "";
      status.replaceChildren(h("p", {}, `${plural(n, "moment")} will be ${this.bleep ? "covered with a tone" : "muted"}. Scanned ${how}.`));
    }
    if (!hasFilter) {
      $("#ranges").replaceChildren();
      return;
    }
    const counts = {};
    for (const r of this.ranges) counts[r.category] = (counts[r.category] || 0) + 1;
    $("#cat-list").replaceChildren(...this.categories().map((c) => h(
      "label",
      { class: "chip" },
      h("input", { type: "checkbox", checked: this.cats.has(c.id), onchange: (e) => {
        e.target.checked ? this.cats.add(c.id) : this.cats.delete(c.id);
        store.set(pk("cats"), [...this.cats]);
        this.renderMarks();
        this.renderPanel();
        this.Audio.reset();
      } }),
      c.label,
      h("span", { class: "n" }, String(counts[c.id] || 0))
    )));
    this.renderRanges();
    $("#export-json").href = `/api/filters/${this.info.media_key}/export?format=json`;
    $("#export-edl").href = `/api/filters/${this.info.media_key}/export?format=edl&cats=${[...this.cats].join(",")}`;
  },
  renderRanges() {
    const reveal = $("#reveal").checked;
    const labels = Object.fromEntries(this.categories().map((c) => [c.id, c.label]));
    const list = this.ranges.filter((r) => r.source === "manual" || this.cats.has(r.category));
    $("#ranges").replaceChildren(...list.map((r) => h(
      "li",
      {
        class: `range ${r.enabled === false ? "off" : ""}`,
        "data-id": r.id
      },
      h("button", { class: "when", type: "button", onclick: () => {
        this.selected = r.id;
        this.seek(r.start - 2);
        this.renderRanges();
      }, "aria-label": `Play from ${fmt(r.start)}` }, fmt(r.start)),
      h(
        "div",
        {},
        h("div", { class: "ctx" }, ...contextNodes(r, reveal)),
        h("span", { class: "cat" }, r.source === "manual" ? "Marked by you" : labels[r.category] || r.category)
      ),
      h(
        "div",
        { class: "ops" },
        h("input", {
          type: "checkbox",
          checked: r.enabled !== false,
          "aria-label": r.enabled === false ? "Not filtered. Filter this moment" : "Filtered. Let this moment play",
          title: "Filter this moment",
          onchange: (e) => {
            r.enabled = e.target.checked;
            this.changed();
          }
        }),
        h("button", {
          class: "icon-btn",
          type: "button",
          "aria-label": "Delete this moment",
          title: "Delete",
          onclick: () => {
            this.ranges = this.ranges.filter((x) => x !== r);
            this.changed();
          },
          html: `<svg viewBox="0 0 24 24">${ICONS.trash}</svg>`
        })
      ),
      this.selected === r.id ? h(
        "div",
        { class: "nudge" },
        h("span", {}, `${fmtPrecise(r.start)} to ${fmtPrecise(r.end)}`),
        h("button", { type: "button", onclick: () => this.nudge(r, "start", -0.1) }, "Start earlier"),
        h("button", { type: "button", onclick: () => this.nudge(r, "start", 0.1) }, "Start later"),
        h("button", { type: "button", onclick: () => this.nudge(r, "end", -0.1) }, "End sooner"),
        h("button", { type: "button", onclick: () => this.nudge(r, "end", 0.1) }, "End later")
      ) : null
    )));
  },
  nudge(r, edge, delta) {
    r[edge] = Math.max(0, Math.round((r[edge] + delta) * 1e3) / 1e3);
    if (r.end - r.start < 0.05) r[edge === "start" ? "start" : "end"] -= delta;
    this.changed();
    this.seek(r.start - 1.5);
  },
  saveTimer: null,
  changed() {
    this.ranges.sort((a, b) => a.start - b.start);
    this.renderMarks();
    this.renderPanel();
    this.Audio.reset();
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(async () => {
      try {
        this.filter = await api(`/api/filters/${this.info.media_key}`, {
          method: "PUT",
          body: { source_id: this.src, item_id: this.item, title: this.info.title, duration: this.duration, ranges: this.ranges }
        });
        this.ranges = this.filter.ranges;
        this.renderMarks();
        this.queueHlsRefresh(200);
      } catch (err) {
        toast(`Couldn't save: ${err.message}`);
      }
    }, 600);
  },
  mark() {
    if (isKids()) return;
    const t = this.now();
    if (this.markStart == null) {
      this.markStart = t;
      $("#mark-btn").textContent = "End mark here";
      toast("Marking. Press M again where it should end.");
      return;
    }
    const [s, e] = [Math.min(this.markStart, t), Math.max(this.markStart, t)];
    this.markStart = null;
    $("#mark-btn").textContent = "Mark a moment";
    if (e - s < 0.2) {
      toast("That mark was too short.");
      return;
    }
    if (!this.filter) this.filter = { engine: "manual", ranges: [] };
    this.ranges.push({
      id: Math.random().toString(36).slice(2, 12),
      start: s,
      end: e,
      words: [],
      category: "manual",
      context: "",
      source: "manual",
      enabled: true
    });
    toast(`Marked ${fmt(s)} to ${fmt(e)}`);
    this.changed();
  },
  async scan(engine) {
    try {
      this.job = await api("/api/analyze", { method: "POST", body: { source_id: this.src, item_id: this.item, title: this.info.title, engine } });
      this.renderPanel();
      Jobs.poll();
    } catch (err) {
      toast(err.message);
    }
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
    } catch (err) {
      toast(err.message);
    }
  },
  onJobs(list) {
    var _a;
    if (!this.info || $("#player").hidden) return;
    const j = list.find((x) => x.media_key === this.info.media_key);
    if (!j) return;
    const was = (_a = this.job) == null ? void 0 : _a.status;
    this.job = j;
    if (j.status === "done" && was && was !== "done") {
      this.loadFilter().then(() => this.renderPanel());
      toast("Language filter is ready");
    } else if (!$("#panel").hidden || j.status !== was) this.renderPanel();
  }
};
function parseVTT(text) {
  const cues = [];
  const ts = (s) => {
    const p = s.trim().split(":").map(Number);
    return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
  };
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
  const phrases = [...words].filter(Boolean).sort((a, b) => b.length - a.length).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "[\\s,.!?-]+"));
  if (!phrases.length) return [text];
  const re = new RegExp(`(^|[^\\p{L}])(${phrases.join("|")})(?=$|[^\\p{L}])`, "giu");
  let last = 0, m;
  while (m = re.exec(text)) {
    const start2 = m.index + m[1].length;
    out.push(text.slice(last, start2), h("span", { class: "bleeped" }, "•".repeat(Math.min(6, Math.max(3, m[2].length)))));
    last = start2 + m[2].length;
  }
  out.push(text.slice(last));
  return out;
}
const COMMON = new Set("a an the of my oh for to son go sake swear with have had having get got off you it in on up out good holy lord christ jesus god gosh".split(" "));
const hide = (w) => w.replace(new RegExp("\\p{L}+", "gu"), (word) => word[0] + "•".repeat(word.length - 1));
function contextNodes(r, reveal) {
  if (!r.context) return [r.source === "manual" ? `${fmtPrecise(r.start)} to ${fmtPrecise(r.end)}` : (r.words || []).join(" ")];
  const flagged = new Set(Player.ranges.flatMap((x) => x.words || []).map((w) => w.toLowerCase().replace(/[^\p{L}\p{N}']/gu, "")).filter((w) => !COMMON.has(w)));
  const parts = r.context.split(/⟦|⟧/);
  return parts.map((p, i) => {
    if (i % 2) return h("mark", {}, reveal ? p : hide(p));
    return reveal ? p : p.replace(/[\p{L}']+/gu, (w) => flagged.has(w.toLowerCase()) ? hide(w) : w);
  });
}
$("#play-btn").addEventListener("click", togglePlay);
function togglePlay() {
  Player.Audio.ensure();
  if (video.paused) video.play().catch((e) => Player.message(`Playback couldn't start: ${e.message}`, true));
  else video.pause();
}
video.addEventListener("click", togglePlay);
video.addEventListener("play", () => {
  $("#player").classList.add("playing");
  $("#play-btn").setAttribute("aria-label", "Pause");
  Player.Audio.ensure();
  Player.Audio.reset();
  idle.bump();
});
video.addEventListener("pause", () => {
  $("#player").classList.remove("playing");
  $("#play-btn").setAttribute("aria-label", "Play");
  Player.Audio.reset();
  idle.show();
});
video.addEventListener("seeked", () => Player.Audio.reset());
video.addEventListener("ratechange", () => Player.Audio.reset());
video.addEventListener("waiting", () => Player.Audio.reset());
video.addEventListener("playing", () => {
  WaitScreen.stop();
  Player.message(null);
  Player.Audio.reset();
  Player.report(true);
  if (!Progress.armed) Progress.arm();
  Player.watchPicture();
});
video.addEventListener("pause", () => {
  if (!video.ended) Progress.save(true);
});
$("#resume-restart").addEventListener("click", () => {
  $("#resume-chip").hidden = true;
  Player.seek(0);
  setTimeout(() => Progress.save(true), 600);
});
function applyPendingSeek() {
  const ps = Player.pendingSeek;
  if (ps == null || video.readyState < 2) return;
  const ok = video.seekable.length && video.seekable.end(video.seekable.length - 1) > ps;
  if (!ok) {
    Player.pendingSeek = null;
    return;
  }
  if (video.buffered.length && video.buffered.end(video.buffered.length - 1) > ps + 0.3) {
    Player.pendingSeek = null;
    video.currentTime = ps;
  }
}
["progress", "canplay", "timeupdate"].forEach((ev) => video.addEventListener(ev, applyPendingSeek));
video.addEventListener("ended", () => {
  var _a;
  $("#player").classList.remove("playing");
  Progress.save(true, true);
  if (autoplay() && !((_a = Player.info) == null ? void 0 : _a.live)) Queue.next(true);
});
$("#autoplay-toggle").addEventListener("change", (e) => {
  store.set("autoplay", e.target.checked);
  toast(e.target.checked ? "Autoplay on" : "Autoplay off");
});
video.addEventListener("error", () => {
  var _a;
  if (!Player.info) return;
  if (Player.mode === "direct") {
    Player.mode = Player.info.probe.video.length ? "transcode" : "audio";
    Player.startAt(video.currentTime || 0).then(() => video.play().catch(() => {
    }));
    return;
  }
  if (Player.mode === "remux" && !Player.triedTranscode) {
    Player.triedTranscode = true;
    Player.mode = "transcode";
    Player.message("Switching to a compatible stream…");
    Player.startAt(Player.now()).then(() => video.play().catch(() => {
    }));
    return;
  }
  Player.report(false);
  if (Player.chan) {
    Player.tryAlternate().then((ok) => {
      if (!ok) Player.message("This channel is not answering. Try another one.", true);
    });
    return;
  }
  const code = ((_a = video.error) == null ? void 0 : _a.code) ? ` (error ${video.error.code})` : "";
  const safari = /^((?!chrome|android|crios|fxios).)*safari/i.test(navigator.userAgent);
  Player.message(safari && Player.mode !== "direct" ? `Safari can't play Hush's live streams yet${code}. Open this page in Chrome, Firefox or Edge, or use "Watch on another player".` : `This file couldn't be played${code}. Check that the server can still reach it.`, true);
});
(function loop() {
  let last = 0;
  const tick = (now) => {
    if (now - last >= 100 && !$("#player").hidden && !document.hidden) {
      last = now;
      Player.frame();
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
})();
$("#back10").addEventListener("click", () => Player.seek(Player.now() - 10));
$("#fwd10").addEventListener("click", () => Player.seek(Player.now() + 10));
$("#back-btn").addEventListener("click", () => go(S.libraryHash || "#/"));
$("#mini-btn").addEventListener("click", () => {
  Player.forceMini = true;
  go(S.libraryHash || "#/");
});
$("#mini-play").addEventListener("click", () => togglePlay());
$("#mini-prev").addEventListener("click", () => Queue.prev());
$("#mini-next").addEventListener("click", () => Queue.next());
$("#mini-title").addEventListener("click", () => Player.src && go(`#/p/${Player.src}/${Player.item}`));
$("#mini-expand").addEventListener("click", () => Player.src && go(`#/p/${Player.src}/${Player.item}`));
$("#mini-close").addEventListener("click", () => Player.close(false));
$("#player").addEventListener("dblclick", () => {
  if (Player.mini && Player.src) go(`#/p/${Player.src}/${Player.item}`);
});
$("#mini-toggle").checked = store.get("mini", true);
$("#mini-toggle").addEventListener("change", (e) => {
  store.set("mini", e.target.checked);
  toast(e.target.checked ? "Mini player on" : "Mini player off");
});
window.addEventListener("resize", () => Player.placeMini());
$("#volume").value = store.get("volume", 1);
$("#volume").addEventListener("input", (e) => {
  Player.Audio.volume(Number(e.target.value));
  store.set("volume", Number(e.target.value));
});
$("#filter-btn").addEventListener("click", () => {
  var _a;
  if (isKids()) return;
  Player.filterOn = !Player.filterOn;
  store.set(pk("filterOn"), Player.filterOn);
  Player.applyFilterButton();
  Player.Audio.reset();
  toast(Player.filterOn ? "Filter on" : "Filter off. Every word will play.");
  if (((_a = Player.info) == null ? void 0 : _a.live) && Player.chan) Player.startAt(0).then(() => video.play().catch(() => {
  }));
});
$("#mode-select").addEventListener("change", (e) => {
  Player.bleep = e.target.value === "bleep";
  store.set(pk("mode"), e.target.value);
  Player.Audio.reset();
  Player.renderPanel();
});
$("#sub-select").addEventListener("change", (e) => Player.loadSubs(e.target.value));
$("#audio-select").addEventListener("change", async (e) => {
  const t = Player.now();
  Player.audioIndex = Number(e.target.value);
  try {
    const info = await api(`/api/media/${Player.src}/${Player.item}?audio=${Player.audioIndex}`);
    Player.mode = info.mode === "direct" ? "direct" : info.mode;
  } catch (e2) {
    Player.mode = "remux";
  }
  if (Player.mode === "direct") {
    video.src = `/api/raw/${Player.src}/${Player.item}`;
    video.currentTime = t;
    video.play().catch(() => {
    });
  } else Player.startAt(t);
});
$("#settings-btn").addEventListener("click", (e) => {
  const s = $("#settings");
  s.hidden = !s.hidden;
  e.currentTarget.setAttribute("aria-expanded", String(!s.hidden));
});
function enterFullscreen() {
  var _a, _b, _c, _d;
  if (document.fullscreenElement || document.webkitFullscreenElement) return;
  const el = document.documentElement;
  try {
    const p = (_a = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen) == null ? void 0 : _a.call(el);
    (_b = p == null ? void 0 : p.catch) == null ? void 0 : _b.call(p, () => {
    });
    (_d = (_c = navigator.keyboard) == null ? void 0 : _c.lock) == null ? void 0 : _d.call(_c, ["Escape"]).catch(() => {
    });
  } catch (e) {
  }
}
function exitFullscreen() {
  var _a;
  (_a = document.exitFullscreen || document.webkitExitFullscreen) == null ? void 0 : _a.call(document);
}
$("#fs-btn").addEventListener("click", () => document.fullscreenElement || document.webkitFullscreenElement ? exitFullscreen() : enterFullscreen());
if (IS_TV_DEVICE) {
  ["keydown", "click"].forEach((t) => document.addEventListener(t, enterFullscreen, true));
}
function togglePanel(open) {
  const p = $("#panel");
  p.hidden = open === void 0 ? !p.hidden : !open;
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
    Player.ranges = Player.filter.ranges;
    Player.renderMarks();
    Player.renderPanel();
    Player.Audio.reset();
    toast("Word list reapplied");
  } catch (err) {
    toast(err.message);
  }
});
$("#external-btn").addEventListener("click", async () => {
  try {
    const r = await api(`/api/external/${Player.src}/${Player.item}?cats=${[...Player.cats].join(",")}`);
    $("#external-url").value = r.url;
    $("#external-dialog").showModal();
    $("#external-url").select();
  } catch (err) {
    toast(err.message);
  }
});
$("#copy-url").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("#external-url").value);
    toast("Link copied");
  } catch (e) {
    $("#external-url").select();
    toast("Press Ctrl+C to copy");
  }
});
(() => {
  const tl = $("#timeline"), tip = $("#tl-tip");
  const at = (e) => {
    const r = tl.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (Player.duration || 0);
  };
  let dragging = false;
  tl.addEventListener("pointerdown", (e) => {
    dragging = true;
    tl.setPointerCapture(e.pointerId);
  });
  tl.addEventListener("pointerup", (e) => {
    if (dragging) {
      dragging = false;
      Player.seek(at(e));
    }
  });
  tl.addEventListener("pointermove", (e) => {
    const t = at(e), r = tl.getBoundingClientRect();
    const hit = Player.ranges.find((x) => Player.active(x) && t >= x.start - Player.duration * 4e-3 && t <= x.end + Player.duration * 4e-3);
    tip.hidden = false;
    tip.style.left = `${e.clientX - r.left}px`;
    tip.classList.toggle("word", !!hit);
    tip.textContent = hit ? `${fmt(t)}  muted: ${hide((hit.words || []).join(" ")) || "your mark"}` : fmt(t);
    if (dragging) $("#tl-played").style.width = `${t / (Player.duration || 1) * 100}%`;
  });
  tl.addEventListener("pointerleave", () => tip.hidden = true);
  tl.addEventListener("keydown", (e) => {
    if (IS_TV_DEVICE || TV.on) return;
    if (e.key === "ArrowLeft") {
      Player.seek(Player.now() - 5);
      e.preventDefault();
    }
    if (e.key === "ArrowRight") {
      Player.seek(Player.now() + 5);
      e.preventDefault();
    }
  });
})();
const idle = {
  timer: null,
  bump() {
    this.show();
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      if (!video.paused && $("#panel").hidden && $("#settings").hidden) $("#player").classList.add("idle");
    }, 3e3);
  },
  show() {
    $("#player").classList.remove("idle");
    clearTimeout(this.timer);
  }
};
$("#player").addEventListener("pointermove", () => idle.bump());
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (IS_TV_DEVICE || TV.on) hideCursorNow();
  if (mediaKey(e)) return;
  if ((TV.on || IS_TV_DEVICE) && TV.handleKey(e)) return;
  if ($("#player").hidden || Player.mini || e.target.matches("input:not([type=checkbox]):not([type=range]), select, textarea") || e.ctrlKey || e.metaKey || e.altKey) return;
  if (document.querySelector("dialog[open]")) return;
  const k = normKey(e).toLowerCase();
  if (Player.chan) {
    if (/^[0-9]$/.test(k)) {
      e.preventDefault();
      Queue.digit(k);
      idle.bump();
      return;
    }
    const tv = IS_TV_DEVICE || TV.on;
    const zapKeys = {
      pageup: () => Queue.zap(-1),
      pagedown: () => Queue.zap(1),
      b: () => Queue.recall(),
      g: () => guide.toggle(),
      i: () => Queue.banner()
    };
    if (!tv) {
      zapKeys.arrowup = () => Queue.zap(-1);
      zapKeys.arrowdown = () => Queue.zap(1);
    }
    if (zapKeys[k]) {
      e.preventDefault();
      zapKeys[k]();
      idle.bump();
      return;
    }
  }
  const map = {
    n: () => Queue.next(),
    p: () => Queue.prev(),
    s: () => Queue.toggleShuffle(),
    r: () => Queue.cycleRepeat(),
    " ": togglePlay,
    k: togglePlay,
    f: () => $("#fs-btn").click(),
    m: () => Player.mark(),
    h: () => $("#filter-btn").click(),
    j: () => Player.seek(Player.now() - 10),
    l: () => Player.seek(Player.now() + 10),
    ...IS_TV_DEVICE || TV.on ? {} : { arrowleft: () => Player.seek(Player.now() - 10), arrowright: () => Player.seek(Player.now() + 10) },
    escape: () => !$("#guide").hidden ? guide.close() : !$("#panel").hidden ? togglePanel(false) : !$("#settings").hidden ? $("#settings").hidden = true : null
  };
  if (e.target === $("#timeline") && (k === "arrowleft" || k === "arrowright")) return;
  if (map[k]) {
    e.preventDefault();
    map[k]();
    idle.bump();
  }
}, true);
const WaitScreen = {
  timer: null,
  showTimer: null,
  t0: 0,
  expected: 10,
  weather: null,
  weatherAt: 0,
  start(label, expected = 10) {
    this.stop();
    if (Player.mini) return;
    this.t0 = Date.now();
    this.expected = expected;
    $("#wait-label").textContent = label;
    this.showTimer = setTimeout(() => {
      $("#wait-screen").hidden = false;
      this.tick();
      this.loadWeather();
      this.timer = setInterval(() => this.tick(), 1e3);
    }, 700);
  },
  label(text, expected) {
    $("#wait-label").textContent = text;
    if (expected) this.expected = expected;
  },
  tick() {
    const now = /* @__PURE__ */ new Date(), s = Math.floor((Date.now() - this.t0) / 1e3);
    $("#wait-clock").textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    $("#wait-date").textContent = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
    $("#wait-count").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    $("#wait-fill").style.width = `${Math.min(95, s / Math.max(1, this.expected) * 100)}%`;
  },
  async loadWeather() {
    if (!this.weather || Date.now() - this.weatherAt > 6e5) {
      try {
        this.weather = await api("/api/weather");
        this.weatherAt = Date.now();
      } catch (e) {
        this.weather = null;
      }
    }
    const w = this.weather, el = $("#wait-weather");
    el.textContent = w && w.configured && !w.unavailable ? `${w.place}: ${w.temp}${w.unit}, ${w.text.toLowerCase()} · high ${w.high}° low ${w.low}°` : "";
  },
  stop() {
    clearTimeout(this.showTimer);
    clearInterval(this.timer);
    this.timer = this.showTimer = null;
    const el = $("#wait-screen");
    if (el) el.hidden = true;
  }
};
const TVSelect = {
  el: null,
  select: null,
  active() {
    return IS_TV_DEVICE || TV.on;
  },
  open(select) {
    var _a, _b, _c;
    if (this.el) return;
    const host = select.closest("dialog") || document.body;
    const label = select.getAttribute("aria-label") || ((_b = (_a = select.closest("label")) == null ? void 0 : _a.textContent) == null ? void 0 : _b.trim()) || "Choose";
    const opts = [...select.options].filter((o) => !o.disabled);
    this.select = select;
    const list = h("div", { class: "tvsel-list", role: "listbox" }, ...opts.map((o) => h("button", {
      class: "tvsel-opt",
      type: "button",
      role: "option",
      "aria-selected": String(o.value === select.value),
      onclick: () => this.choose(o.value)
    }, o.textContent)));
    this.el = h("div", { class: "tvsel", role: "dialog", "aria-label": label }, h("div", { class: "tvsel-box" }, h("h2", {}, label), list));
    host.append(this.el);
    (_c = list.querySelector('[aria-selected="true"]') || list.firstChild) == null ? void 0 : _c.focus({ preventScroll: false });
  },
  choose(value) {
    const s = this.select;
    if (s && s.value !== value) {
      s.value = value;
      s.dispatchEvent(new Event("input", { bubbles: true }));
      s.dispatchEvent(new Event("change", { bubbles: true }));
    }
    this.close();
  },
  close() {
    var _a;
    const s = this.select;
    (_a = this.el) == null ? void 0 : _a.remove();
    this.el = null;
    this.select = null;
    s == null ? void 0 : s.focus({ preventScroll: true });
  }
};
document.addEventListener("mousedown", (e) => {
  var _a, _b;
  const s = (_b = (_a = e.target).closest) == null ? void 0 : _b.call(_a, "select");
  if (s && TVSelect.active() && !s.disabled) {
    e.preventDefault();
    TVSelect.open(s);
  }
}, true);
const TV = {
  on: false,
  init() {
    var _a;
    this.on = (_a = store.get("tv", null)) != null ? _a : TVUA.test(navigator.userAgent);
    this.apply();
    const watch = new MutationObserver(() => {
      clearTimeout(this.obsTimer);
      this.obsTimer = setTimeout(() => this.focusSoon(0), 350);
    });
    ["#catalog-view", "#browser-view", "#tasks", "#prefs"].forEach((id) => watch.observe($(id), { childList: true, subtree: true }));
  },
  set(on) {
    this.on = on;
    store.set("tv", on);
    this.apply();
    if (on && !location.hash.startsWith("#/p/")) go("#/home");
    else route();
  },
  apply() {
    document.documentElement.classList.toggle("tv", this.on);
    $("#tv-toggle").setAttribute("aria-pressed", String(this.on));
    Player.placeMini();
    if (this.on) this.focusSoon(200);
  },
  navCurrent(view) {
    var _a;
    const group = { home: "home", movies: "movies", title: ((_a = Catalog.cameFrom) == null ? void 0 : _a.replace("#/", "")) || "movies", shows: "shows", show: "shows", live: "live", b: "folders", folders: "folders", mylist: "mylist" }[view];
    $$("#tv-nav a").forEach((a) => a.setAttribute("aria-current", String(a.hash === `#/${group}`)));
  },
  /* ---------- spatial navigation ---------- */
  visible(el) {
    if (!el.isConnected || el.hidden) return false;
    if (el.offsetParent === null && !el.getClientRects().length) return false;
    return el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0;
  },
  roots() {
    if (TVSelect.el) return [TVSelect.el];
    const dlg = document.querySelector("dialog[open]");
    if (dlg) return [dlg];
    for (const id of ["#profile-picker", "#login"]) if (!$(id).hidden) return [$(id)];
    if (!$("#guide").hidden) return [$("#guide")];
    if (!$("#panel").hidden) return [$("#panel")];
    if (!$("#player").hidden && !Player.mini) return [$("#controls")];
    const r = [...document.querySelectorAll(".topbar, #tv-nav, #library:not([hidden]), #tasks:not([hidden]), #prefs:not([hidden])")];
    if (Player.mini) r.push($("#player"));
    return r;
  },
  focusables(roots) {
    const sel = 'a[href], button:not([disabled]):not(.star):not(.x), input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea, [tabindex]:not([tabindex="-1"])';
    return roots.flatMap((root) => [...root.querySelectorAll(sel)]).filter((el) => this.visible(el));
  },
  focusFirst() {
    const roots = this.roots();
    const main = roots.filter((r) => {
      var _a;
      return (_a = r.matches) == null ? void 0 : _a.call(r, "#library, #tasks, #prefs, dialog, .guide, .panel, #controls");
    });
    const list = this.focusables(main.length ? main : roots);
    const target = list.find((el) => el.matches(".card, .chan, .entry a, .lt:not(:disabled), .shelf-row a, .tv-nav a")) || list[0];
    target == null ? void 0 : target.focus({ preventScroll: true });
  },
  focusSoon(delay = 250) {
    if (!this.on) return;
    clearTimeout(this.focusTimer);
    this.focusTimer = setTimeout(() => {
      const a = document.activeElement;
      if (a && a !== document.body && this.visible(a) && a.closest("#app")) return;
      if (!$("#player").hidden && !Player.mini) {
        $("#stage").focus({ preventScroll: true });
        return;
      }
      this.focusFirst();
    }, delay);
  },
  move(dir) {
    const cands = this.focusables(this.roots());
    const cur = document.activeElement;
    if (!cur || cur === document.body || !cands.includes(cur)) {
      this.focusFirst();
      return;
    }
    const c = cur.getBoundingClientRect(), cx = c.left + c.width / 2, cy = c.top + c.height / 2;
    let best = null, bestScore = Infinity;
    for (const el of cands) {
      if (el === cur || cur.contains(el) || el.contains(cur)) continue;
      const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, dx = x - cx, dy = y - cy;
      let primary, cross;
      if (dir === "right") {
        if (r.left < c.right - c.width * 0.4 && dx <= 0) continue;
        if (dx <= 1) continue;
        primary = dx;
        cross = Math.abs(dy);
      } else if (dir === "left") {
        if (dx >= -1) continue;
        primary = -dx;
        cross = Math.abs(dy);
      } else if (dir === "down") {
        if (dy <= 1) continue;
        primary = dy;
        cross = Math.abs(dx);
      } else {
        if (dy >= -1) continue;
        primary = -dy;
        cross = Math.abs(dx);
      }
      const score = primary + cross * 2.4;
      if (score < bestScore) {
        bestScore = score;
        best = el;
      }
    }
    if (best) {
      best.focus({ preventScroll: true });
      best.scrollIntoView({ block: dir === "up" || dir === "down" ? "center" : "nearest", inline: "nearest" });
    } else if (dir === "down") window.scrollBy({ top: 220 });
    else if (dir === "up") window.scrollBy({ top: -220 });
  },
  /* ---------- Back ---------- */
  back() {
    var _a;
    if (TVSelect.el) {
      TVSelect.close();
      return;
    }
    const tlb = $("#timeline");
    if ((tlb == null ? void 0 : tlb.dataset.adjust) === "1") {
      tlb.dataset.adjust = "0";
      return;
    }
    if (!$("#profile-picker").hidden) {
      if (!$("#profiles-cancel").hidden) $("#profiles-cancel").click();
      return;
    }
    if (!$("#login").hidden) return;
    const dlg = document.querySelector("dialog[open]");
    if (dlg) {
      dlg.close();
      return;
    }
    if (!$("#guide").hidden) {
      guide.close();
      $("#guide-btn").focus();
      return;
    }
    if (!$("#panel").hidden) {
      togglePanel(false);
      return;
    }
    if (!$("#settings").hidden) {
      $("#settings").hidden = true;
      return;
    }
    if (!$("#player").hidden && !Player.mini) {
      if ((_a = document.activeElement) == null ? void 0 : _a.closest("#controls")) {
        $("#stage").focus();
        return;
      }
      go(S.libraryHash || "#/home");
      return;
    }
    const hash = location.hash.replace(/^#\/?/, "").split("/");
    const [view, src] = [hash[0], hash[1]];
    if (view === "title") go(Catalog.cameFrom && Catalog.cameFrom !== "#/title" ? Catalog.cameFrom : "#/movies");
    else if (view === "show") go("#/shows");
    else if (view === "b") {
      const parent = S.dirParent[S.currentDir];
      if (S.currentDir) go(parent ? `#/b/${S.source}/${parent}` : `#/b/${S.source}`);
      else go("#/folders");
    } else if (view && view !== "home") go("#/home");
  },
  /** Returns true when the key was handled here. */
  handleKey(e) {
    var _a, _b, _c, _d, _e, _f, _g, _h;
    const k = normKey(e);
    const typing = (_b = (_a = e.target).matches) == null ? void 0 : _b.call(_a, "input:not([type=checkbox]):not([type=range]), textarea");
    const isBack = k === "Escape" || k === "GoBack" || k === "BrowserBack" || e.keyCode === 10009 || e.keyCode === 461 || k === "Backspace" && !typing;
    if (k === "Enter" && e.target.tagName === "SELECT" && !e.target.disabled) {
      e.preventDefault();
      TVSelect.open(e.target);
      return true;
    }
    if (k === "Enter" && e.target.id === "timeline") {
      e.preventDefault();
      const on = e.target.dataset.adjust !== "1";
      e.target.dataset.adjust = on ? "1" : "0";
      if (on) toast("Left and right to skip 10 seconds. Press OK when done.");
      idle.bump();
      return true;
    }
    const overlay = document.querySelector("dialog[open]") || !$("#guide").hidden || !$("#panel").hidden || !$("#settings").hidden;
    const playerOpen = !$("#player").hidden && !Player.mini;
    if (isBack) {
      e.preventDefault();
      this.back();
      return true;
    }
    const dir = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" }[k];
    if (!dir) {
      if (k === "Enter" && playerOpen && !overlay && !((_c = document.activeElement) == null ? void 0 : _c.closest("#controls"))) {
        e.preventDefault();
        togglePlay();
        idle.bump();
        return true;
      }
      return false;
    }
    if (e.repeat) {
      const now = performance.now();
      if (now - (this.lastStep || 0) < 90) {
        e.preventDefault();
        return true;
      }
      this.lastStep = now;
    }
    if (typing && (dir === "left" || dir === "right")) return false;
    if ((_e = (_d = e.target).matches) == null ? void 0 : _e.call(_d, "input[type=range]")) return false;
    if (playerOpen && !overlay) {
      e.preventDefault();
      const ctl = (_f = document.activeElement) == null ? void 0 : _f.closest("#controls");
      const hidden = $("#player").classList.contains("idle");
      if (!ctl || hidden) {
        idle.bump();
        (((_g = Player.lastControl) == null ? void 0 : _g.isConnected) && Player.lastControl.closest("#controls") ? Player.lastControl : $("#play-btn")).focus({ preventScroll: true });
        return true;
      }
      const tl = $("#timeline");
      if (document.activeElement === tl && tl.dataset.adjust === "1") {
        if (dir === "left" || dir === "right") {
          Player.seek(Player.now() + (dir === "left" ? -10 : 10));
          idle.bump();
          return true;
        }
        tl.dataset.adjust = "0";
      }
      this.move(dir);
      idle.bump();
      if ((_h = document.activeElement) == null ? void 0 : _h.closest("#controls")) Player.lastControl = document.activeElement;
      return true;
    }
    e.preventDefault();
    this.move(dir);
    return true;
  }
};
$("#tv-toggle").addEventListener("click", () => TV.set(!TV.on));
$("#tv-exit").addEventListener("click", () => TV.set(false));
const MEDIA_KEYCODES = {
  415: "MediaPlay",
  19: "MediaPause",
  10252: "MediaPlayPause",
  413: "MediaStop",
  417: "MediaFastForward",
  412: "MediaRewind",
  427: "ChannelUp",
  428: "ChannelDown",
  33: "ChannelUp",
  34: "ChannelDown",
  457: "Info",
  458: "Guide",
  403: "ColorF0Red",
  404: "ColorF1Green",
  405: "ColorF2Yellow",
  406: "ColorF3Blue"
};
function mediaKey(e) {
  if (!video.currentSrc || !Player.info) return false;
  const k = MEDIA_KEYCODES[e.keyCode] || e.key;
  if ((e.keyCode === 33 || e.keyCode === 34) && (Player.mini || $("#player").hidden)) return false;
  const act = {
    MediaPlayPause: () => togglePlay(),
    MediaPlay: () => video.paused && togglePlay(),
    MediaPause: () => !video.paused && togglePlay(),
    MediaStop: () => Player.close(false),
    MediaTrackNext: () => Queue.next(),
    MediaTrackPrevious: () => Queue.prev(),
    MediaFastForward: () => Player.seek(Player.now() + 30),
    MediaRewind: () => Player.seek(Player.now() - 30),
    ChannelUp: () => Player.chan && Queue.zap(1),
    ChannelDown: () => Player.chan && Queue.zap(-1),
    Info: () => Queue.banner(),
    Guide: () => Player.chan && guide.toggle(),
    ColorF0Red: () => $("#filter-btn").click(),
    ColorF1Green: () => $("#panel-btn").click(),
    ColorF2Yellow: () => Player.chan && guide.toggle(),
    ColorF3Blue: () => $("#mini-btn").click()
  }[k];
  if (!act) return false;
  e.preventDefault();
  act();
  idle.bump();
  return true;
}
const Remote = {
  ws: null,
  retry: 0,
  stateTimer: null,
  soonTimer: null,
  lastSent: "",
  status_: "",
  enabled() {
    return store.get("remote", TVUA.test(UA));
  },
  name() {
    return store.get("screenName", "") || (TV.on ? "TV" : "Screen");
  },
  id() {
    let i = store.get("screenId");
    if (!i) {
      i = Math.random().toString(36).slice(2, 12);
      store.set("screenId", i);
    }
    return i;
  },
  status(text) {
    this.status_ = text;
    const el = $("#remote-status");
    if (el) el.textContent = text;
  },
  start() {
    if (!this.enabled()) {
      this.stop();
      return;
    }
    if (this.ws && this.ws.readyState <= 1) return;
    this.connect();
  },
  stop() {
    clearInterval(this.stateTimer);
    if (this.ws) {
      this.ws.onclose = null;
      try {
        this.ws.close();
      } catch (e) {
      }
      this.ws = null;
    }
    this.status("Off");
  },
  connect() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/remote/ws`);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.lastSent = "";
      ws.send(JSON.stringify({ type: "hello", role: "screen", id: this.id(), name: this.name() }));
      this.push(true);
      clearInterval(this.stateTimer);
      this.stateTimer = setInterval(() => this.push(false), 2e3);
      this.status(`Connected as "${this.name()}"`);
    };
    ws.onmessage = (ev) => {
      let m;
      try {
        m = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (m.type === "cmd") this.exec(m.cmd, m.args || {});
    };
    ws.onclose = () => {
      clearInterval(this.stateTimer);
      this.ws = null;
      this.status("Reconnecting…");
      if (this.enabled()) setTimeout(() => this.start(), Math.min(15e3, 1e3 * 2 ** this.retry++));
    };
  },
  state() {
    var _a;
    const active = !!Player.info && !!video.currentSrc && !$("#player").hidden;
    const q = Queue.list[Queue.pos];
    const chan = active && Player.chan ? { num: Queue.pos + 1, name: (q == null ? void 0 : q.title) || "", logo: (q == null ? void 0 : q.logo) || null } : null;
    return {
      active,
      playing: active && !video.paused,
      live: active && !!((_a = Player.info) == null ? void 0 : _a.live),
      title: !active ? "" : chan ? splitTags(chan.name).title : Player.info.title || "",
      mediaKey: active ? Player.info.media_key : null,
      position: active ? Math.round(Player.now() * 10) / 10 : 0,
      duration: active ? Math.round(Player.duration || 0) : 0,
      volume: Number($("#volume").value),
      filterOn: Player.filterOn,
      mini: Player.mini,
      channel: chan,
      tv: TV.on,
      view: location.hash,
      queue: Queue.list.length,
      shuffle: Queue.shuffle,
      repeat: Queue.repeat
    };
  },
  push(force) {
    if (!this.ws || this.ws.readyState !== 1) return;
    const s = JSON.stringify({ type: "state", state: this.state() });
    if (!force && s === this.lastSent) return;
    this.lastSent = s;
    this.ws.send(s);
  },
  soon() {
    clearTimeout(this.soonTimer);
    this.soonTimer = setTimeout(() => this.push(true), 150);
  },
  pressKey(key) {
    var _a;
    if (!TV.on && ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter", "Escape"].includes(key) && $("#player").hidden) TV.set(true);
    const a = document.activeElement;
    const target = a && a !== document.body ? a : document.body;
    if (key === "Enter") {
      const clickable = (_a = target.closest) == null ? void 0 : _a.call(target, "a[href], button, summary, label, [role=button]");
      if (clickable && !clickable.disabled) {
        clickable.click();
        return;
      }
    }
    target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  },
  exec(cmd, a) {
    const playing = !!video.currentSrc && !!Player.info;
    const num = (v, d = 0) => Number.isFinite(Number(v)) ? Number(v) : d;
    switch (cmd) {
      case "key":
        this.pressKey(String(a.key || ""));
        break;
      case "playpause":
        if (playing) togglePlay();
        break;
      case "play":
        if (playing && video.paused) togglePlay();
        break;
      case "pause":
        if (playing && !video.paused) togglePlay();
        break;
      case "seek":
        if (playing) Player.seek(Player.now() + num(a.delta));
        break;
      case "seekto":
        if (playing) Player.seek(num(a.t));
        break;
      case "next":
        Queue.next();
        break;
      case "prev":
        Queue.prev();
        break;
      case "channel":
        if (Player.chan) Queue.zap(num(a.delta, 1) >= 0 ? 1 : -1);
        break;
      case "digits":
        for (const d of String(a.digits || "").slice(0, 4)) if (/\d/.test(d)) Queue.digit(d);
        break;
      case "volume": {
        const v = a.value != null ? num(a.value) : Number($("#volume").value) + num(a.delta);
        $("#volume").value = Math.max(0, Math.min(1, v));
        $("#volume").dispatchEvent(new Event("input", { bubbles: true }));
        break;
      }
      case "mute": {
        const vol = $("#volume");
        if (Number(vol.value) > 0) {
          this.lastVolume = Number(vol.value);
          vol.value = 0;
        } else vol.value = this.lastVolume || 1;
        vol.dispatchEvent(new Event("input", { bubbles: true }));
        break;
      }
      case "filter":
        if (playing) $("#filter-btn").click();
        break;
      case "stop":
        Player.close(false);
        break;
      case "home":
        go("#/home");
        break;
      case "guide":
        if (Player.chan) guide.toggle();
        break;
      case "mini":
        if (playing) $("#mini-btn").click();
        break;
      case "tv":
        TV.set(a.on !== false);
        break;
      case "nav":
        if (typeof a.hash === "string" && a.hash.startsWith("#/") && !a.hash.startsWith("#/p/")) go(a.hash);
        break;
      case "open":
        if (a.src && a.item) {
          Queue.set([{ src: String(a.src), item: String(a.item), title: String(a.title || ""), chan: a.chan || null, logo: a.logo || null, groups: a.groups || [] }]);
          Queue.loadMore = null;
          go(`#/p/${a.src}/${a.item}`);
        }
        break;
      default:
        break;
    }
    this.soon();
  }
};
["play", "pause", "ended", "loadedmetadata", "volumechange"].forEach((ev) => video.addEventListener(ev, () => Remote.soon()));
window.addEventListener("hashchange", () => Remote.soon());
$("#remote-btn").addEventListener("click", () => {
  var _a;
  $("#remote-enable").checked = Remote.enabled();
  $("#remote-name").value = store.get("screenName", "") || "";
  $("#remote-url").value = `${location.origin}/remote`;
  Remote.status(Remote.enabled() ? ((_a = Remote.ws) == null ? void 0 : _a.readyState) === 1 ? `Connected as "${Remote.name()}"` : "Connecting…" : "Off");
  $("#remote-dialog").showModal();
});
$("#remote-enable").addEventListener("change", (e) => {
  store.set("remote", e.target.checked);
  Remote.start();
});
$("#remote-name").addEventListener("change", (e) => {
  store.set("screenName", e.target.value.trim());
  if (Remote.enabled()) {
    Remote.stop();
    Remote.start();
  }
});
$("#remote-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("#remote-url").value);
    toast("Address copied");
  } catch (e) {
    $("#remote-url").select();
    toast("Press Ctrl+C to copy");
  }
});
let cursorTimer;
function hideCursorNow() {
  clearTimeout(cursorTimer);
  document.documentElement.classList.add("hide-cursor");
}
function showCursorBriefly() {
  document.documentElement.classList.remove("hide-cursor");
  clearTimeout(cursorTimer);
  if (IS_TV_DEVICE || TV.on) cursorTimer = setTimeout(hideCursorNow, 3500);
}
document.addEventListener("mousemove", showCursorBriefly, { passive: true });
if (IS_TV_DEVICE) hideCursorNow();
function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}
async function route() {
  var _a, _b, _c;
  requestAnimationFrame(() => Player.placeMini());
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  const [view, src, id] = [parts[0], parts[1], parts.slice(2).join("/")];
  TV.navCurrent(view);
  if (!view) {
    go("#/home");
    return;
  }
  if (isKids() && (["b", "tasks", "folders", "profiles", "downloads"].includes(view) || view === "live" && !((_b = (_a = S.profile) == null ? void 0 : _a.settings) == null ? void 0 : _b.allow_live))) {
    go("#/home");
    return;
  }
  $("#tasks").hidden = view !== "tasks";
  $("#prefs").hidden = view !== "settings";
  if (view !== "p") S.libraryHash = location.hash || "#/";
  if (view === "p" && src && id) {
    if (Player.mini && src === Player.src && id === Player.item) Player.expand();
    else Player.open(src, id);
    return;
  }
  if (!$("#player").hidden && !Player.mini) {
    if (Player.keepPlaying()) Player.minimize();
    else Player.close(false);
  }
  if (view === "tasks") {
    $("#library").hidden = true;
    Tasks.open();
    return;
  }
  if (view === "settings") {
    $("#library").hidden = true;
    $("#prefs").hidden = false;
    TV.focusSoon();
    WeatherCard.load();
    const app = window.HushApp;
    $("#app-card").hidden = !app;
    if (app) $("#app-info").textContent = `Hush app ${app.version()} · connected to ${app.server()}`;
    const e = (_c = S.config) == null ? void 0 : _c.encoder;
    $("#enc-info").textContent = !e ? "Unknown" : e.encoder === "libx264" ? "The processor (CPU) re-encodes video when a screen can't play a file as it is. No GPU was found; with one, set video_encoder: auto." : `${e.gpu || e.encoder} re-encodes video when needed (${e.encoder}).`;
    return;
  }
  $("#library").hidden = false;
  const inCatalog = ["home", "movies", "shows", "show", "title", "live", "folders", "profiles", "mylist", "downloads"].includes(view);
  $("#catalog-view").hidden = !inCatalog;
  $("#browser-view").hidden = inCatalog;
  $$("#rail-links a").forEach((a) => {
    if (!inCatalog) a.removeAttribute("aria-current");
  });
  if (inCatalog) {
    Catalog.open(view, src);
    return;
  }
  if (view === "b" && src) {
    browse(src, id || "");
    return;
  }
  const first = S.sources.find((s) => !s.error);
  if (first) browse(first.id);
  else {
    $("#crumbs").replaceChildren();
    $("#entries").replaceChildren();
    showEmpty("Add your first source", "Point Hush at a NAS share, a folder, a DLNA server, Jellyfin or Plex. You can also paste a link to a single video on the left.");
  }
}
window.addEventListener("hashchange", route);
async function start() {
  $("#login").hidden = true;
  try {
    await Profiles.load();
  } catch (e) {
    return;
  }
  if (Profiles.data.needs_pick) {
    Profiles.show(true);
    return;
  }
  $("#app").hidden = false;
  Profiles.apply();
  try {
    [S.config] = await Promise.all([api("/api/config"), loadSources()]);
  } catch (e) {
    return;
  }
  route();
  Jobs.poll();
  Remote.start();
  Catalog.watch();
}
(async () => {
  TV.init();
  try {
    const s = await api("/api/session");
    S.authRequired = s.auth_required;
    $("#logout-btn").hidden = !s.auth_required;
    s.logged_in ? start() : showLogin();
  } catch (e) {
    showLogin();
  }
})();
