# Verification results — 2026-11-13

- Backend: `python -m pytest -q`: **84 passed**.
- All original 68 tests pass after adapting the mocked-fake-audio tests to the FFmpeg decode-first pipeline.
- New tests cover actual WAV/MP3/WebM-Opus/Ogg/FLAC/M4A/AIFF FFmpeg decode, invalid file rejection, offset-voting fingerprint matching, HTTP WebM recognition, preference ranking, feedback, similar-song ranking, RLS route ownership via dependency mocks, and Spotify Now Playing via mocked Spotify API.
- Frontend: `tsc --noEmit --pretty false --incremental false`: **passed**.
- Next.js production build: **NOT VERIFIED**. Build could not download `@next/swc-linux-x64-gnu` from npm registry (network `EAI_AGAIN`); bundled SWC binary in original ZIP is Windows-only. Do not interpret this as a successful production build.
- Frontend Vitest test execution: **not verified** due native Rollup/ESBuild platform dependency in Windows ZIP; run `npm ci && npm test` on developer machine.
- PostgreSQL migration SQL: **not executed on live Supabase**. Test with a database backup first.
- Recognition against real licensed recordings: **not tested**; no benchmark collection or audio catalog was supplied.
- Spotify OAuth and user Now Playing: test uses mocked API response; **not tested with a real Spotify account**.
- Seed: 15 metadata entries, with 4 MusicBrainz release citations. Audio and fingerprints are intentionally absent.
- No commercial ad serving or audio advertising has been enabled.
