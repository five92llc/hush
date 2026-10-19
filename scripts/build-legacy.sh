#!/usr/bin/env bash
# Make hush/web/app.legacy.js: app.js translated for older TV browsers (LG webOS 5 (Chrome 68), NetCast (Chrome 79)).
# Run it after changing app.js; a test fails when the copy is out of date.
set -euo pipefail
cd "$(dirname "$0")/.."
SUM="$(shasum -a 256 hush/web/app.js | cut -d' ' -f1)"
npx -y esbuild@0.21.5 hush/web/app.js --target=chrome64 --charset=utf8 --banner:js="/* app.legacy.js - built from app.js (sha256 ${SUM}) by scripts/build-legacy.sh. Do not edit. */" --outfile=hush/web/app.legacy.js
echo "built hush/web/app.legacy.js from app.js ${SUM:0:12}"
