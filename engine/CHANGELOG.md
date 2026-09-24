# Changelog

## [0.2.0](https://github.com/czekanskyy/praelector/compare/v0.1.0...v0.2.0) (2026-09-24)


### Features

* **engine:** add GPU device detection behind /v1/gpu/devices ([98362b5](https://github.com/czekanskyy/praelector/commit/98362b566ddba8c642a098becaa1eb029298a466))
* **engine:** admit TTS workers up to the budget slot count ([#31](https://github.com/czekanskyy/praelector/issues/31)) ([e979895](https://github.com/czekanskyy/praelector/commit/e9798956d9f24c1c11f483763744c737f63bbe51))
* **engine:** apply accepted suggestions onto one block ([#22](https://github.com/czekanskyy/praelector/issues/22)) ([11f3b2b](https://github.com/czekanskyy/praelector/commit/11f3b2bce693f47adb9641d57c851f255064024f))
* **engine:** cache a model file only after its checksum matches ([#33](https://github.com/czekanskyy/praelector/issues/33)) ([13a4846](https://github.com/czekanskyy/praelector/commit/13a48468a0f8d5d0bf9aaeeae25789dac948b706))
* **engine:** compute how many TTS workers a GPU can hold ([#25](https://github.com/czekanskyy/praelector/issues/25)) ([79aae7f](https://github.com/czekanskyy/praelector/commit/79aae7f0574a024135a1e9bb39aa11faf24f7705))
* **engine:** export a reader epub with pronunciation spans ([#24](https://github.com/czekanskyy/praelector/issues/24)) ([dfe2879](https://github.com/czekanskyy/praelector/commit/dfe2879c07d1a90c3ef572ac790fd22822ec8747))
* **engine:** fall back to the narrator when a voice slot has no sample ([#36](https://github.com/czekanskyy/praelector/issues/36)) ([e77e262](https://github.com/czekanskyy/praelector/commit/e77e2623efad48c2e891e1a4fb58a86991ad8bbe))
* **engine:** ingest a voice sample through an injected ffmpeg ([#35](https://github.com/czekanskyy/praelector/issues/35)) ([27e284c](https://github.com/czekanskyy/praelector/commit/27e284c2b961af38a6d1529822da8d52c875fc00))
* **engine:** install a locked TTS runtime into the data directory ([#28](https://github.com/czekanskyy/praelector/issues/28)) ([4439920](https://github.com/czekanskyy/praelector/commit/4439920c1d23cabb3d53d62f1bae21136209d6dc))
* **engine:** let a lexicon rule override a heuristic reading ([#21](https://github.com/czekanskyy/praelector/issues/21)) ([374d576](https://github.com/czekanskyy/praelector/commit/374d57626b7fd28a9aed3f945e2ea42d7f31b841))
* **engine:** look up a TTS backend and refuse a language it does not speak ([#32](https://github.com/czekanskyy/praelector/issues/32)) ([7546957](https://github.com/czekanskyy/praelector/commit/7546957edb192b41929c79977b48615bcfaf029f))
* **engine:** pack spoken text into reusable plan chunks ([#37](https://github.com/czekanskyy/praelector/issues/37)) ([2ea5231](https://github.com/czekanskyy/praelector/commit/2ea523112718cf4a02d00271220d42e1c80aee19))
* **engine:** parse the TTS worker wire protocol ([#29](https://github.com/czekanskyy/praelector/issues/29)) ([e84f55d](https://github.com/czekanskyy/praelector/commit/e84f55d2c9547bc0dc4fed68b37d71c7cb33714e))
* **engine:** pause GPU admissions when VRAM drops below the reserve ([#26](https://github.com/czekanskyy/praelector/issues/26)) ([69c129a](https://github.com/czekanskyy/praelector/commit/69c129a3219c84e3aa99efff1898539f305a63a3))
* **engine:** read and write EPUB without EbookLib ([49b3620](https://github.com/czekanskyy/praelector/commit/49b3620c1f6b18855ebd85fdf09334aac67d3a0f))
* **engine:** recommend a TTS runtime flavour and detect a mismatch ([#27](https://github.com/czekanskyy/praelector/issues/27)) ([c70dc66](https://github.com/czekanskyy/praelector/commit/c70dc669e825a23c4c0a473671265bd451369d13))
* **engine:** sidecar skeleton, loopback auth, error codes, and the TTS worker ([33482a7](https://github.com/czekanskyy/praelector/commit/33482a7990d0b69b2a11cc0078aa710a98329a90))
* **engine:** spawn a TTS worker and kill it when it stalls ([#30](https://github.com/czekanskyy/praelector/issues/30)) ([5bfd1d4](https://github.com/czekanskyy/praelector/commit/5bfd1d427e6cdefc7466b8cec64749a87d7ea1da))
* **engine:** store accepted readings as spans and speak from them ([#23](https://github.com/czekanskyy/praelector/issues/23)) ([a792d00](https://github.com/czekanskyy/praelector/commit/a792d008820e477a7eeb312beabfbc7d3f991c05))
* **engine:** store chapters and edit them as plain text ([9f65417](https://github.com/czekanskyy/praelector/commit/9f65417868796875126fe071a7f41272078ab9a3))
* **engine:** suggest readings and dialogue splits without rewriting the page ([#16](https://github.com/czekanskyy/praelector/issues/16)) ([94a0dfc](https://github.com/czekanskyy/praelector/commit/94a0dfc056ae5421cfd7f1de21b850109c58d386))
* **engine:** tag dialogue with speaker gender from the speech verb ([#20](https://github.com/czekanskyy/praelector/issues/20)) ([3f5e591](https://github.com/czekanskyy/praelector/commit/3f5e591a7f399fb3bed49b561278acffaa59257c))
