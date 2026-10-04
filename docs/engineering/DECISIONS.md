# Engineering decisions

1. HYBRID: maintain a small source patch series for camera, persistence and network adapters; use existing PhysFS/editor/map infrastructure for authored content. A content-only mod cannot confidently meet the camera and durable world-state requirements. Replacing the engine would discard working cooperative systems and multiplies risk.
2. Pin public master 962a5ce36d10207beef7d8673876e0cebf8e76e4 (commit 2026-02-20; source declares v5.0.2). This is observed public source, NOT a verified statement that the installed/current retail build matches it. Revalidate against the user's installation before using assets or network compatibility.
3. Vanilla gate is blocked, not passed. No integrated Adventure Core or large engine changes. Patch 0001 is staged for after baseline launch; its application was checked but it was not compiled or run.
4. Initial source-build route disables Steam/EOS/PlayFab and commercial audio SDKs. It is a compiler baseline, not the desired shipped experience. Investigate direct-connect first. Public source has SDL_net UDP plus Steam/EOS paths; actual LAN/internet connectivity remains untested. Do not promise Steam invites, crossplay, dedicated server or NAT traversal.
5. Audio is mandatory for the eventual playtest (telegraphs and atmosphere). Silent baseline is insufficient. FMOD requires legitimate SDK access; OpenAL is marked deprecated/unmaintained upstream and is not accepted without runtime validation.
6. Keep upstream files unchanged; package code notices, not retail game assets. BSD-2-Clause applies to the open-source release; third-party components retain their own licenses. Preserve all notices. No assertion that purchased data may be redistributed.
7. Campaign belongs to host. Guests retain identity within that campaign, not unrestricted imported progression. Four-player save ownership, reconnect, host loss and migrations are required before persistence ships. Cross-campaign transfers are deferred.
8. Secrets are separated editorially, not cryptographically. Logs sent to the blind player must contain only opaque issue IDs and timings. Never distribute a developer-content listing as player instructions.

Sources: official repository README.md, INSTALL.md, LICENSE.txt, EDITING.txt, CMakeLists.txt and source files at pinned commit. https://github.com/TurningWheel/Barony

9. User selected Steam and the TheSecondPenguin repository. Import source as a dedicated baseline commit; maintain project work in following commits. Exclude only upstream CI and IDE databases. Keep source origin and commit recorded, preserve all license notices. Steam ownership does not supply Steamworks or FMOD development SDK credentials.
10. Local build environment remains unchanged; add manually dispatched dependency-provisioned compiler CI so the build gate can be attempted after remote access. It is not a runtime gate.

11. On 2026-10-04 the user declined agent access to the personal PC via Jump. Treat personal-desktop remote control as excluded, including replacement tools. Preserve prior runtime investigation as history. A separate interactive Windows host is a candidate requiring legitimate game data, access, cost approval where applicable, and actual input/audio verification; an owner-operated isolated build is the alternative without agent control. Neither has been executed.
