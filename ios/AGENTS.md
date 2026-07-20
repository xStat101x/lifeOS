# LifeOS iOS — Agent Rules

The iOS app (in this `/ios` directory) is the **primary client** for LifeOS.
Design source of truth: `../docs/SPEC.md` (esp. §4 architecture, §10 day-close,
§18 notifications, §20 sync). This file holds iOS-specific conventions only.

## Stack & conventions
- **SwiftUI + Swift.** No UIKit unless a specific feature genuinely requires it.
- **Local store: GRDB (SQLite)** via Swift Package Manager. Do NOT use Core Data
  or SwiftData. The on-device schema mirrors the server's §6 shape so state is
  deterministic and syncable (§20).
- **Offline-first.** All daily logging and rank/XP display must work fully offline.
  Logs are written locally with **client-generated UUIDs** and queued for later push.
  The server's recompute is canonical on sync (§20); the phone reconciles on connect.
- The app is a client against the existing Python API in `../server` — do not
  re-implement scoring on-device beyond what §20 requires for offline display.

## Build & test
- Build and test from the command line with `xcodebuild`
  (scheme `LifeOS`, an iOS Simulator destination). Run tests before declaring a slice done.
- **Simulator only for now.** No code signing, no Apple Developer account, no
  physical-device features yet. **HealthKit, EventKit, and push notifications are
  deferred to their own later slices** — do NOT add their capabilities/entitlements now.

## Xcode project hygiene
- The `LifeOS` source folder is a synchronized/buildable folder — create new Swift
  files **inside it** so Xcode picks them up automatically.
- Do NOT hand-edit `project.pbxproj`. If a change genuinely requires editing the
  project file or adding a target/capability, STOP and flag it for me to do in Xcode.

## Workflow
- Small, reviewable commits. Pause for review before committing.
- Keep decisions in `../DECISIONS.md` and progress in `../PROGRESS.md` (monorepo —
  one shared log across server, ios, and web).
