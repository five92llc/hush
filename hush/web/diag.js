/* Loaded first, written for old browsers (smart TVs): reports script errors to the server's log and shows them
   on screen, so a blank TV is never a mystery. Also fills in browser features some TVs lack. */
(function () {
  "use strict";
  var sent = 0;
  function report(info) {
    if (sent++ > 12) return;
    info.ua = navigator.userAgent; info.hash = location.hash;
    try {
      var x = new XMLHttpRequest();
      x.open("POST", "/api/client-error", true);
      x.setRequestHeader("Content-Type", "application/json");
      x.send(JSON.stringify(info));
    } catch (e) { /* nothing more to do */ }
  }
  function banner(text) {
    try {
      var el = document.getElementById("fatal");
      if (!el) {
        el = document.createElement("div"); el.id = "fatal";
        el.setAttribute("role", "alert");
        el.style.cssText = "position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#7a2a1c;color:#fff;font:16px/1.4 sans-serif;padding:10px 16px";
        document.body.appendChild(el);
      }
      el.textContent = "Hush hit a problem on this screen: " + text + "  (it was reported to the server)";
    } catch (e) { /* body not ready */ }
  }
  window.hushReport = report;                                 // lets app.js tell the server about things like a missing picture
  window.addEventListener("error", function (e) {
    if (!e.message) return;                                   // a failed image or script load, not a script error
    if (window.__hushTrying && /SyntaxError/.test(e.message)) { e.preventDefault(); return; }   // boot.js is about to load the translated copy
    if (/^ResizeObserver loop/.test(e.message)) { e.stopImmediatePropagation(); return; }   // a harmless browser notice, not a fault
    report({ kind: "error", message: String(e.message).slice(0, 300), file: String(e.filename || "").split("/").pop(), line: e.lineno, col: e.colno,
      stack: String((e.error && e.error.stack) || "").slice(0, 700) });
    banner(String(e.message).slice(0, 160));
  });
  window.addEventListener("unhandledrejection", function (e) {
    var r = e.reason || {};
    report({ kind: "rejection", message: String(r.message || r).slice(0, 300), stack: String(r.stack || "").slice(0, 700) });
  });

  /* ---- fill in what older TV browsers lack ---- */
  var E = Element.prototype;
  if (!E.replaceChildren) {
    var rc = function () {
      while (this.firstChild) this.removeChild(this.firstChild);
      for (var i = 0; i < arguments.length; i++) {
        var n = arguments[i];
        this.appendChild(n && n.nodeType ? n : document.createTextNode(String(n)));
      }
    };
    E.replaceChildren = rc; DocumentFragment.prototype.replaceChildren = rc;
  }
  if (!String.prototype.replaceAll) String.prototype.replaceAll = function (a, b) { return a instanceof RegExp ? this.replace(a, b) : this.split(a).join(b); };
  if (!Array.prototype.flat) Array.prototype.flat = function (d) {
    d = d === undefined ? 1 : Math.floor(d);
    return (function f(a, n) { return a.reduce(function (o, v) { return o.concat(Array.isArray(v) && n > 0 ? f(v, n - 1) : [v]); }, []); })(this, d);
  };
  if (!Array.prototype.flatMap) Array.prototype.flatMap = function (fn, t) { return Array.prototype.map.call(this, fn, t).flat(); };
  if (!Object.fromEntries) Object.fromEntries = function (it) { var o = {}; Array.from(it).forEach(function (kv) { o[kv[0]] = kv[1]; }); return o; };
  if (!String.prototype.matchAll) String.prototype.matchAll = function (re) {
    var g = new RegExp(re.source, re.flags.indexOf("g") < 0 ? re.flags + "g" : re.flags), out = [], m;
    while ((m = g.exec(this)) !== null) { out.push(m); if (m[0] === "") g.lastIndex++; }
    return out[Symbol.iterator]();
  };
  if (!Array.prototype.at) Array.prototype.at = function (i) { i = Math.trunc(i) || 0; if (i < 0) i += this.length; return this[i]; };
  if (!Element.prototype.append) Element.prototype.append = function () { for (var i = 0; i < arguments.length; i++) this.appendChild(arguments[i] && arguments[i].nodeType ? arguments[i] : document.createTextNode(String(arguments[i]))); };

  /* flex "gap" arrived in Chromium 84: when it is missing the style sheet spaces things with margins instead */
  document.addEventListener("DOMContentLoaded", function () {
    var d = document.createElement("div");
    d.style.cssText = "display:flex;flex-direction:column;row-gap:1px;position:absolute;visibility:hidden";
    d.appendChild(document.createElement("i")); d.appendChild(document.createElement("i"));
    document.body.appendChild(d);
    var ok = d.scrollHeight === 1;
    document.body.removeChild(d);
    if (!ok) document.documentElement.className += " no-flex-gap";
  });
})();
