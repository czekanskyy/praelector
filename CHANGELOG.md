# Changelog

## [0.3.0](https://github.com/czekanskyy/praelector/compare/v0.2.0...v0.3.0) (2026-09-25)


### Features

* **engine:** admit synthesis only when a slot is free ([#44](https://github.com/czekanskyy/praelector/issues/44)) ([99a6c82](https://github.com/czekanskyy/praelector/commit/99a6c82e18b5765cb0e4871f2c30398f2e05338a))
* **engine:** build spoken runs from the current chapter text ([#43](https://github.com/czekanskyy/praelector/issues/43)) ([117b8b3](https://github.com/czekanskyy/praelector/commit/117b8b32bf431bf52bb7efe484a1bcc8bbe2c119))
* **engine:** build the m4b command and its chapter tags ([#48](https://github.com/czekanskyy/praelector/issues/48)) ([d4e2b75](https://github.com/czekanskyy/praelector/commit/d4e2b752831d310598b8b7812486151ffec59dde))
* **engine:** choose complete chapters and list their chunks ([#49](https://github.com/czekanskyy/praelector/issues/49)) ([27022e4](https://github.com/czekanskyy/praelector/commit/27022e4db278de66ee5626d795f50945dcc9f242))
* **engine:** copy each included chapter to a numbered wav ([#69](https://github.com/czekanskyy/praelector/issues/69)) ([f63e586](https://github.com/czekanskyy/praelector/commit/f63e586c0262148178a2d37d64b20b98e2196acf))
* **engine:** encode an m4b from a concat list and tags ([#70](https://github.com/czekanskyy/praelector/issues/70)) ([9e937bd](https://github.com/czekanskyy/praelector/commit/9e937bd8111b071bcbfe8ae33184d12cabbaaa23))
* **engine:** estimate remaining time from smoothed chunk rates ([#45](https://github.com/czekanskyy/praelector/issues/45)) ([94059ac](https://github.com/czekanskyy/praelector/commit/94059ac9017aa508e796a4716a454ef49ff71762))
* **engine:** export a partial book to an m4b without a binary ([#74](https://github.com/czekanskyy/praelector/issues/74)) ([5643a18](https://github.com/czekanskyy/praelector/commit/5643a18b6376a0806a2841998110fe7e2ddede19))
* **engine:** fetch ffmpeg only after the LGPL build is accepted ([#53](https://github.com/czekanskyy/praelector/issues/53)) ([b4d4258](https://github.com/czekanskyy/praelector/commit/b4d4258047033a7e4561a05880f4b539422301e9))
* **engine:** keep a job on the plan's state diagram ([#40](https://github.com/czekanskyy/praelector/issues/40)) ([ada25be](https://github.com/czekanskyy/praelector/commit/ada25bed438a05e592a2a6340992482527512bf0))
* **engine:** keep a single job slot and delete audio only on request ([#47](https://github.com/czekanskyy/praelector/issues/47)) ([59fa514](https://github.com/czekanskyy/praelector/commit/59fa51447aa12a2abda38dcddd5a71f2dd41552a))
* **engine:** look for ffmpeg in settings, then PATH, then the data dir ([#54](https://github.com/czekanskyy/praelector/issues/54)) ([f944231](https://github.com/czekanskyy/praelector/commit/f9442314d5730e72c55f9fc01c65b43ce52d0519))
* **engine:** name a retained chapter wav with its book number ([#52](https://github.com/czekanskyy/praelector/issues/52)) ([a280361](https://github.com/czekanskyy/praelector/commit/a28036134f5a5436f10c8a65065119dd6ad2eb30))
* **engine:** pause, resume, and cancel a job over http ([#73](https://github.com/czekanskyy/praelector/issues/73)) ([aa7bd27](https://github.com/czekanskyy/praelector/commit/aa7bd272dfd539ccd95f8cf1d382faeb435c2de5))
* **engine:** persist each job transition before the new record ([#41](https://github.com/czekanskyy/praelector/issues/41)) ([5f35c52](https://github.com/czekanskyy/praelector/commit/5f35c5275315573a0b9ecc96e5d751332335d982))
* **engine:** publish a chunk only after its duration matches ([#46](https://github.com/czekanskyy/praelector/issues/46)) ([0dc5017](https://github.com/czekanskyy/praelector/commit/0dc5017eb42ea0fef49ede1a4287bf0b5b23a324))
* **engine:** publish a fake chunk once its wav duration matches ([#57](https://github.com/czekanskyy/praelector/issues/57)) ([f41a9aa](https://github.com/czekanskyy/praelector/commit/f41a9aa2a375eca723574ee23d9a7e687f4168b6))
* **engine:** quarantine chunk files that do not match their sidecar ([#62](https://github.com/czekanskyy/praelector/issues/62)) ([0dbf452](https://github.com/czekanskyy/praelector/commit/0dbf452099bd202b628bf199724570a68ccd1436))
* **engine:** queue one job over http ([#77](https://github.com/czekanskyy/praelector/issues/77)) ([f4bc724](https://github.com/czekanskyy/praelector/commit/f4bc7247ec2db22d1623461d7bbab40d6dde477a))
* **engine:** read job history and replay events since a seq ([#67](https://github.com/czekanskyy/praelector/issues/67)) ([35b408a](https://github.com/czekanskyy/praelector/commit/35b408a9a19513f0e5b03f67592ad2adb6545631))
* **engine:** rebuild the chunk index from sidecars on open ([#66](https://github.com/czekanskyy/praelector/issues/66)) ([0d5fd22](https://github.com/czekanskyy/praelector/commit/0d5fd2205c29ccf61bf52e936b2caf744d1d94b6))
* **engine:** record omitted chapters and their place on the timeline ([#51](https://github.com/czekanskyy/praelector/issues/51)) ([cba2326](https://github.com/czekanskyy/praelector/commit/cba232670e91c856dd533193aa720996157c4a73))
* **engine:** render a running job with the fake voice in one pass ([#68](https://github.com/czekanskyy/praelector/issues/68)) ([a35263e](https://github.com/czekanskyy/praelector/commit/a35263ef4379a107bc9619c9cf7030016cea1622))
* **engine:** render only the speech chunks that are not reusable ([#58](https://github.com/czekanskyy/praelector/issues/58)) ([2277bf3](https://github.com/czekanskyy/praelector/commit/2277bf31c91cddeaddf8974841ac8cc30051ec68))
* **engine:** render the active job through the job manager ([#72](https://github.com/czekanskyy/praelector/issues/72)) ([98c1102](https://github.com/czekanskyy/praelector/commit/98c11022b8c82d6749b2ba318b3547f5131c673d))
* **engine:** replay job events the client has not seen yet ([#56](https://github.com/czekanskyy/praelector/issues/56)) ([54cb167](https://github.com/czekanskyy/praelector/commit/54cb1679f8f2cb323e34ef4f69fbecdbdf4bdd43))
* **engine:** resume a job at the first speech chunk that is not done ([#59](https://github.com/czekanskyy/praelector/issues/59)) ([eba181b](https://github.com/czekanskyy/praelector/commit/eba181be1b8c672ea70dd8420702be200e841fdc))
* **engine:** reuse a chunk only when the wav matches its sidecar ([#38](https://github.com/czekanskyy/praelector/issues/38)) ([affeff5](https://github.com/czekanskyy/praelector/commit/affeff54b5ff33242885e97d18927eb87f08d5b5))
* **engine:** rewrite the job plan as one jsonl file ([#42](https://github.com/czekanskyy/praelector/issues/42)) ([3f524e3](https://github.com/czekanskyy/praelector/commit/3f524e30cc5bf36e26af5be709468d1c3417781b))
* **engine:** run an m4b argument list through the ffmpeg tool ([#63](https://github.com/czekanskyy/praelector/issues/63)) ([f12f669](https://github.com/czekanskyy/praelector/commit/f12f669609d4216b5dcb92688f0b26817082b8e4))
* **engine:** stand in for speech with a sine of chars over fourteen ([#55](https://github.com/czekanskyy/praelector/issues/55)) ([2ae1049](https://github.com/czekanskyy/praelector/commit/2ae10495dc1dd86e5e9db46aa1e42b9a784c132c))
* **engine:** store voice profiles with one slot each ([#76](https://github.com/czekanskyy/praelector/issues/76)) ([687d0b9](https://github.com/czekanskyy/praelector/commit/687d0b9e1f1721cd3e9097f75b4f25307ba61751))
* **engine:** write the silence between sentences as a wav ([#50](https://github.com/czekanskyy/praelector/issues/50)) ([bcb8925](https://github.com/czekanskyy/praelector/commit/bcb8925b91895a4cadad8dc188e9f407b4f128f3))


### Documentation

* **docs:** describe the tts worker protocol and the fake backend ([#71](https://github.com/czekanskyy/praelector/issues/71)) ([915ac8f](https://github.com/czekanskyy/praelector/commit/915ac8f1a86b65583f6ad5e03b781d78f87beb50))
* **docs:** record plugins, job reads, and the injected m4b encode ([#75](https://github.com/czekanskyy/praelector/issues/75)) ([9de7061](https://github.com/czekanskyy/praelector/commit/9de70612ffafc1d5492b56275f63a7fca11697c5))
* **docs:** record reconcile, crash reuse, and the ffmpeg hand-off ([#65](https://github.com/czekanskyy/praelector/issues/65)) ([20dc50c](https://github.com/czekanskyy/praelector/commit/20dc50c76b824593be6f19e876405afe9dfefa7e))
* **plan:** mark the milestones that are actually in the tree ([#60](https://github.com/czekanskyy/praelector/issues/60)) ([4bbf80a](https://github.com/czekanskyy/praelector/commit/4bbf80af362de2042b497c47dd5b5212c587341d))

## [0.2.0](https://github.com/czekanskyy/praelector/compare/v0.1.0...v0.2.0) (2026-09-24)


### Features

* **desktop:** supervise the engine sidecar from the Tauri shell ([42b3259](https://github.com/czekanskyy/praelector/commit/42b32595e1ac1348dc5aa9b5a840c75ce8fbd637))
* **engine-tts:** describe OmniVoice and require Polish ref text ([#34](https://github.com/czekanskyy/praelector/issues/34)) ([eec1864](https://github.com/czekanskyy/praelector/commit/eec1864d13f988cd55b5686a95940808c1ac5783))
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
* **ui:** add the app shell, i18n catalogues, and the engine clients ([5e8f1f8](https://github.com/czekanskyy/praelector/commit/5e8f1f8baa2684d0acdb3b6cade05eb8a168428e))
* **ui:** list and create projects on the Library screen ([ef907a3](https://github.com/czekanskyy/praelector/commit/ef907a3a62ff030a842657a6d8ca305921c2c466))


### Documentation

* add PRD and implementation plan ([2349f42](https://github.com/czekanskyy/praelector/commit/2349f42088ca833297a0f76ff17f659481e97c3e))

## Changelog

The format is based on [Conventional Commits](https://www.conventionalcommits.org/), and this file is generated and managed by [release-please](https://github.com/googleapis/release-please) — do not edit it by hand.
