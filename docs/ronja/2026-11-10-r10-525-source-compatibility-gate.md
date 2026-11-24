# R10 source gate — archived 525 and RustWorld Zero compatibility (2026-11-10)

**Not a build report.** Read-only GitHub inspection only; Greg/Mac/iPhone are not accessible through authorized local execution at this time.

## Previously available original sources examined

- [GTRCM RustWorld README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md) inventories multiple 525 Swift/Xcode project variants, not a single proven release candidate.
- [Archived Skin SocketCoreService.swift](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/source/DelteFiler/gtrcm/Skin%20IOS/525%20Skin/SocketCoreService.swift), blob `510db6e1830c1a14b416345cc8607ebf503294f6`, uses `NWConnection(host: "localhost", port: 5250, using: .tcp)` and sends newline-delimited JSON. It retries on `.failed` after two seconds; this is not the authenticated RFP/RW0S2 transport to Greg, and the code shown does not implement bounded exponential backoff or application-level receipt/replay control.
- [Archived Skin app entry](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/source/DelteFiler/gtrcm/Skin%20IOS/525%20Skin/_25_SkinApp.swift), blob `b26fdfd61220c123d5008a2d044ccbdcb1adcf23`, is a SwiftUI `@main` entry point; existence of a source entry does not establish a signed/installed app.
- [Archived AppIcon Contents.json](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/source/DelteFiler/gtrcm/Skin%20IOS/525%20Skin/Assets.xcassets/AppIcon.appiconset/Contents.json), blob `ffdfe150be82b5a43726c1349762b6eefcadb81e`, declares idioms/sizes but **no image filenames**. It does not by itself demonstrate a usable icon asset.
- [RustWorld Zero README](https://github.com/martintommerstigen/GTRCM/blob/architecture/rustworld-zero-2026-11-02/rustworld_zero/README.md), blob `4f2ee2b8ea6fc820b4eca676e01b80916f55e564`, explicitly separates Core journal from untrusted Skin inbox and reports prior Greg/Mac Rust tests, while noting 525 was not updated from Zero. This is a *historical report*, not a new R10 live run.

## Operational difference and release gate

The archived 525 Skin's localhost:5250 JSON socket and RustWorld Zero's later HMAC-authenticated inbox are **different protocol regimes**. Neither their common name nor successful transport within one regime proves end-to-end compatibility. GTRCM C02/C06 and Rolf O/K/I require keeping observed bytes, access channel, influence and operational individuation separate.

Before claiming release: choose one authoritative 525 Xcode target, check its actual Swift compile/signing/assets, specify an authenticated versioned RFP or RW0S2 adapter with strict message length, nonce/replay/recipient binding, and test offline/reconnect without duplicate Core writes. Then test real iPhone-to-Greg source/response and preserve both IDs and raw receipts. Until authorized Mac/Xcode/iPhone and Greg access exists, mark **blocked for tested-live**, not done. No app icon or network capability is fabricated in this branch.

**Provenance classification:** original code read, historical compatibility mismatch identified; no new physics, no current-production 525 assertion, no live iPhone build.
