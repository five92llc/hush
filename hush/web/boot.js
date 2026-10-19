/* Starts the Hush app. Old TV browsers (LG webOS 5 and older) cannot read the newest JavaScript, so when the normal
   script does not start (its first line sets window.__hushBooted) they get app.legacy.js, a copy translated for them. */
(function () {
  var me = document.currentScript || document.getElementById("boot");
  function load(src, then) {
    var s = document.createElement("script");
    s.src = src; s.async = false;
    s.onload = s.onerror = function () { if (then) then(); };
    document.head.appendChild(s);
  }
  document.addEventListener("DOMContentLoaded", function () {              // like a deferred script: after the page exists
    var modern = me.getAttribute("data-modern"), legacy = me.getAttribute("data-legacy");
    if (/[?&]legacy=1/.test(location.search)) { load(legacy); return; }   // for testing
    window.__hushTrying = true;                                            // a SyntaxError from this attempt is expected on old TVs: do not report it
    load(modern, function () { window.__hushTrying = false; if (!window.__hushBooted) load(legacy); });
  });
})();
