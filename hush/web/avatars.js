/* Profile pictures: simple flat drawings, built in so they look the same on every screen
   (some TVs have no emoji font). Each is drawn on a 64x64 grid and shown on the profile's colour. */
(function () {
  "use strict";
  var D = "#191A2C", CREAM = "#FFF3DC", PINK = "#F4A6B1";
  function svg(inner) { return '<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">' + inner + "</svg>"; }
  function eyes(y, dx, r) { r = r || 2.7; return '<circle cx="' + (32 - dx) + '" cy="' + y + '" r="' + r + '" fill="' + D + '"/><circle cx="' + (32 + dx) + '" cy="' + y + '" r="' + r + '" fill="' + D + '"/>'; }
  function line(d, w) { return '<path d="' + d + '" stroke="' + D + '" stroke-width="' + (w || 2.2) + '" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'; }

  window.AVATAR_SVG = {
    smile: svg('<circle cx="32" cy="33" r="22" fill="#FFE08A"/>' + eyes(29, 7, 3) + line("M22 39q10 11 20 0", 3.2)),
    cool: svg('<circle cx="32" cy="33" r="22" fill="#FFE08A"/><rect x="14" y="24" width="16" height="10" rx="4.5" fill="' + D + '"/><rect x="34" y="24" width="16" height="10" rx="4.5" fill="' + D + '"/>' +
      line("M30 28h4", 3) + line("M23 41q9 8 18 0", 3)),
    cat: svg('<path d="M12 31 L14 8 L30 19Z" fill="#F2B36B"/><path d="M52 31 L50 8 L34 19Z" fill="#F2B36B"/><path d="M17 23 L18 14 L25 19Z" fill="' + PINK + '"/><path d="M47 23 L46 14 L39 19Z" fill="' + PINK + '"/>' +
      '<circle cx="32" cy="37" r="20" fill="#F2B36B"/><ellipse cx="24.5" cy="34" rx="2.6" ry="3.6" fill="' + D + '"/><ellipse cx="39.5" cy="34" rx="2.6" ry="3.6" fill="' + D + '"/>' +
      '<path d="M29.3 40.5h5.4L32 44z" fill="#E07A8A"/>' + line("M32 44q-3 4-7 2M32 44q3 4 7 2", 1.8) + line("M8 38h11M9 44l10-3M56 38H45M55 44l-10-3", 1.4)),
    dog: svg('<ellipse cx="13" cy="31" rx="7" ry="15" fill="#8B5A2B" transform="rotate(12 13 31)"/><ellipse cx="51" cy="31" rx="7" ry="15" fill="#8B5A2B" transform="rotate(-12 51 31)"/>' +
      '<circle cx="32" cy="35" r="19" fill="#E8B77A"/><ellipse cx="32" cy="43" rx="10.5" ry="8.5" fill="' + CREAM + '"/>' + eyes(30, 8) + '<ellipse cx="32" cy="39.5" rx="4.6" ry="3.3" fill="' + D + '"/>' + line("M32 43v3M32 46q-3 3-6 1M32 46q3 3 6 1", 1.8)),
    bear: svg('<circle cx="15" cy="17" r="7.5" fill="#B97A45"/><circle cx="49" cy="17" r="7.5" fill="#B97A45"/><circle cx="15" cy="17" r="3.6" fill="#E2B88A"/><circle cx="49" cy="17" r="3.6" fill="#E2B88A"/>' +
      '<circle cx="32" cy="35" r="21" fill="#B97A45"/><ellipse cx="32" cy="42" rx="10.5" ry="8.5" fill="#E8C59A"/>' + eyes(30, 9) + '<ellipse cx="32" cy="38.5" rx="4.2" ry="3" fill="' + D + '"/>' + line("M32 41.5v3M32 44.5q-3 3-6 1M32 44.5q3 3 6 1", 1.8)),
    fox: svg('<path d="M9 13 L25 25 H39 L55 13 L53 38 Q32 59 11 38Z" fill="#F28C38"/><path d="M13 19 L23 26 L15 31Z" fill="' + D + '" opacity=".85"/><path d="M51 19 L41 26 L49 31Z" fill="' + D + '" opacity=".85"/>' +
      '<path d="M32 54Q21 50 19 38Q32 47 45 38Q43 50 32 54Z" fill="' + CREAM + '"/>' + eyes(33, 8.5, 2.6) + '<circle cx="32" cy="51" r="3.2" fill="' + D + '"/>'),
    panda: svg('<circle cx="16" cy="16" r="8" fill="' + D + '"/><circle cx="48" cy="16" r="8" fill="' + D + '"/><circle cx="32" cy="35" r="21" fill="#FFFFFF"/>' +
      '<ellipse cx="23" cy="32" rx="5.2" ry="7" fill="' + D + '" transform="rotate(20 23 32)"/><ellipse cx="41" cy="32" rx="5.2" ry="7" fill="' + D + '" transform="rotate(-20 41 32)"/>' +
      '<circle cx="23.5" cy="31" r="1.9" fill="#fff"/><circle cx="40.5" cy="31" r="1.9" fill="#fff"/><ellipse cx="32" cy="42" rx="3.8" ry="2.8" fill="' + D + '"/>' + line("M32 44.5q-3 3-6 1.5M32 44.5q3 3 6 1.5", 1.8)),
    rabbit: svg('<ellipse cx="22" cy="15" rx="6.5" ry="14" fill="' + CREAM + '" transform="rotate(-6 22 15)"/><ellipse cx="42" cy="15" rx="6.5" ry="14" fill="' + CREAM + '" transform="rotate(6 42 15)"/>' +
      '<ellipse cx="22" cy="16" rx="3" ry="9.5" fill="' + PINK + '" transform="rotate(-6 22 16)"/><ellipse cx="42" cy="16" rx="3" ry="9.5" fill="' + PINK + '" transform="rotate(6 42 16)"/>' +
      '<circle cx="32" cy="42" r="17" fill="' + CREAM + '"/>' + eyes(40, 8, 2.5) + '<ellipse cx="32" cy="45.5" rx="3.2" ry="2.3" fill="' + PINK + '"/><rect x="30" y="48.5" width="4" height="5.5" rx="1.2" fill="#fff" stroke="' + D + '" stroke-width="1"/>' +
      line("M32 48q-3 2-6 0M32 48q3 2 6 0", 1.5)),
    owl: svg('<path d="M12 21 L16 6 L27 16Z" fill="#8A5A3A"/><path d="M52 21 L48 6 L37 16Z" fill="#8A5A3A"/><ellipse cx="32" cy="37" rx="21" ry="23" fill="#A9744F"/><ellipse cx="32" cy="46" rx="12" ry="14" fill="#E8C59A"/>' +
      '<circle cx="22.5" cy="30" r="9.5" fill="' + CREAM + '"/><circle cx="41.5" cy="30" r="9.5" fill="' + CREAM + '"/><circle cx="22.5" cy="30" r="4.2" fill="' + D + '"/><circle cx="41.5" cy="30" r="4.2" fill="' + D + '"/>' +
      '<circle cx="21.2" cy="28.6" r="1.3" fill="#fff"/><circle cx="40.2" cy="28.6" r="1.3" fill="#fff"/><path d="M28 36h8l-4 7z" fill="#F0B04A"/>'),
    frog: svg('<ellipse cx="32" cy="39" rx="23" ry="17" fill="#7ACB6A"/><circle cx="19.5" cy="24" r="9.5" fill="#7ACB6A"/><circle cx="44.5" cy="24" r="9.5" fill="#7ACB6A"/>' +
      '<circle cx="19.5" cy="24" r="6.3" fill="#fff"/><circle cx="44.5" cy="24" r="6.3" fill="#fff"/><circle cx="20.5" cy="25" r="3.1" fill="' + D + '"/><circle cx="43.5" cy="25" r="3.1" fill="' + D + '"/>' +
      '<circle cx="29" cy="35" r="1.3" fill="' + D + '"/><circle cx="35" cy="35" r="1.3" fill="' + D + '"/>' + line("M16 42Q32 57 48 42", 3) + '<circle cx="14" cy="43" r="3.2" fill="' + PINK + '" opacity=".7"/><circle cx="50" cy="43" r="3.2" fill="' + PINK + '" opacity=".7"/>'),
    lion: svg('<circle cx="32" cy="33" r="27" fill="#D9822B"/><circle cx="14" cy="14" r="6.5" fill="#F6CF8A"/><circle cx="50" cy="14" r="6.5" fill="#F6CF8A"/><circle cx="32" cy="35" r="18" fill="#F6CF8A"/>' +
      '<ellipse cx="32" cy="43.5" rx="8.5" ry="6.5" fill="' + CREAM + '"/>' + eyes(32, 8, 2.6) + '<path d="M28.3 38.2h7.4L32 42.6z" fill="' + D + '"/>' + line("M32 42.6q-3 4.4-7 2.4M32 42.6q3 4.4 7 2.4", 1.8)),
    penguin: svg('<ellipse cx="32" cy="36" rx="20" ry="24" fill="#2B3A67"/><ellipse cx="32" cy="42" rx="12.5" ry="17" fill="#fff"/><circle cx="24.5" cy="25" r="5.4" fill="#fff"/><circle cx="39.5" cy="25" r="5.4" fill="#fff"/>' +
      '<circle cx="25.5" cy="26" r="2.4" fill="' + D + '"/><circle cx="38.5" cy="26" r="2.4" fill="' + D + '"/><path d="M26.5 31h11L32 38.5z" fill="#F0B04A"/><ellipse cx="22" cy="59" rx="7" ry="2.6" fill="#F0B04A"/><ellipse cx="42" cy="59" rx="7" ry="2.6" fill="#F0B04A"/>'),
    robot: svg('<path d="M32 6v10" stroke="#C9CED8" stroke-width="3" stroke-linecap="round"/><circle cx="32" cy="6.5" r="3.8" fill="#F0B04A"/><rect x="7" y="26" width="6" height="14" rx="2.5" fill="#8E96A8"/><rect x="51" y="26" width="6" height="14" rx="2.5" fill="#8E96A8"/>' +
      '<rect x="12" y="15" width="40" height="36" rx="9" fill="#C9CED8"/><rect x="18" y="25" width="11" height="10" rx="3.2" fill="#6AE3FF"/><rect x="35" y="25" width="11" height="10" rx="3.2" fill="#6AE3FF"/>' +
      '<rect x="21" y="40" width="22" height="6" rx="2.4" fill="' + D + '"/>' + line("M26.5 40v6M32 40v6M37.5 40v6", 1.4).replace(D, "#C9CED8")),
    alien: svg('<path d="M32 7C49 7 55 24 51 38C48 49 38 57 32 57C26 57 16 49 13 38C9 24 15 7 32 7Z" fill="#8FD694"/><ellipse cx="22.5" cy="33" rx="6.6" ry="9.2" fill="' + D + '" transform="rotate(-22 22.5 33)"/>' +
      '<ellipse cx="41.5" cy="33" rx="6.6" ry="9.2" fill="' + D + '" transform="rotate(22 41.5 33)"/><circle cx="20.5" cy="29.5" r="1.9" fill="#fff"/><circle cx="43.5" cy="29.5" r="1.9" fill="#fff"/>' + line("M27 48q5 3.5 10 0", 2.4)),
    dino: svg('<path d="M14 20L19 8L25 18Z" fill="#4FA85A"/><path d="M26 16L32 4L38 16Z" fill="#4FA85A"/><path d="M39 18L45 8L50 20Z" fill="#4FA85A"/><rect x="9" y="16" width="46" height="36" rx="15" fill="#6FBF73"/>' +
      '<circle cx="23" cy="31" r="4.2" fill="#fff"/><circle cx="41" cy="31" r="4.2" fill="#fff"/><circle cx="24" cy="31.5" r="2.1" fill="' + D + '"/><circle cx="40" cy="31.5" r="2.1" fill="' + D + '"/>' +
      '<circle cx="28" cy="41" r="1.4" fill="' + D + '"/><circle cx="36" cy="41" r="1.4" fill="' + D + '"/>' + line("M17 44Q32 55 47 44", 2.6) + '<path d="M25 49l2.2 3.4 2.2-3.4M34.6 49l2.2 3.4 2.2-3.4" fill="#fff"/>'),
    ghost: svg('<path d="M13 55V30C13 14 21 7 32 7S51 14 51 30V55L44.5 49L38.5 55L32 49L25.5 55L19.5 49Z" fill="#F5F5FF"/><ellipse cx="24.5" cy="30" rx="3.2" ry="4.4" fill="' + D + '"/><ellipse cx="39.5" cy="30" rx="3.2" ry="4.4" fill="' + D + '"/>' +
      '<ellipse cx="32" cy="41" rx="4.2" ry="5.2" fill="' + D + '"/><circle cx="19" cy="38" r="3.2" fill="' + PINK + '" opacity=".7"/><circle cx="45" cy="38" r="3.2" fill="' + PINK + '" opacity=".7"/>'),
  };
})();
