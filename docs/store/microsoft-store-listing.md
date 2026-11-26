# Microsoft Store listing — EPI Recorder

Ready-to-paste text for Partner Center. Everything here describes what the
package actually does; nothing claims more than the file format proves.

Package: `EPIRecorder-<version>-x64.msix` · Category **Developer tools** · Price **Free**

---

## Product name

```
EPI Recorder
```

Reserved name in Partner Center. If "EPI Recorder" is taken, fallbacks in order:
`EPI Recorder — Decision Records`, `EPI Decision Records`, `EPILabs Recorder`.

---

## Short description (max 100 characters)

```
Open and check sealed AI decision records (.epi files) offline. Free, no account.
```

Length: 82 characters.

---

## Description (max 10,000 characters)

```
EPI Recorder opens and checks .epi files: sealed records of what an artificial
intelligence system did when it made a decision.

WHAT A .EPI FILE IS

A .epi file is one decision, recorded and sealed. It holds the timeline of what
the AI system was given and what it did, the decision it reached and the reason
it gave, which model and version answered, and which person approved or
overrode it. The file is signed when it is sealed.

.epi files are produced by developers and vendors who use the open-source
epi-recorder tool. This app is the Windows way to open and check one.

WHAT THIS APP DOES

- Opens a .epi file and shows the decision record as a readable page.
- Checks the file offline, on your machine, with no account and no server:
  whether the contents still match what was sealed, and whether the signature
  matches the key inside the file.
- Adds the "epi" command to any terminal, so you can check a file from the
  command line and script it.
- Opens a .epi file when you double-click it in File Explorer.

WHAT A CHECK PROVES, AND WHAT IT DOES NOT

It proves the file has not changed since it was sealed, and that it was signed
by the key it carries.

It does not prove that every action of the AI system was recorded, that the
decision was correct, or that the person who signed is who they claim to be
until you pin their key separately. It is evidence you can inspect, not a
certificate, and it is not legal advice.

Checking is always free and never requires an account.

FOR REVIEWERS

The window that opens shows the record itself: inputs, the decision, the
reason, the model and version, the approval, and the result of the integrity
and signature checks. Nothing is uploaded. The app does not run in the
background and does not start automatically.

FOR DEVELOPERS

The recorder that creates .epi files is a separate, open-source Python tool:

    pip install epi-recorder

This Store app is for opening and checking files that already exist.

REQUIREMENTS

Windows 10 version 2004 (build 19041) or later, 64-bit.

PRIVACY

The app works offline. It sends nothing anywhere unless you explicitly run a
command that uploads a file. Usage telemetry is off by default. See
https://epilabs.org/privacy

ABOUT

EPI Recorder is open source (Apache-2.0) and built from
https://github.com/mohdibrahimaiml/epi-recorder by EPI Labs. Support and
documentation: https://epilabs.org
```

---

## Feature bullets (4)

```
1. Open a .epi decision record and read it as a normal page.
2. Check a file offline — integrity and signature — with no account and no server.
3. See what the AI system was given, what it decided, why, which model version, and who approved it.
4. Get the "epi" command in any terminal, and open .epi files by double-clicking.
```

---

## Listing properties

| Field | Value |
|---|---|
| Category | **Developer tools** |
| Pricing | **Free** |
| Website | https://epilabs.org |
| Privacy policy | https://epilabs.org/privacy |
| Support | https://epilabs.org |
| Support contact | mohdibrahim@epilabs.org |
| Terms | https://epilabs.org/terms |
| Copyright | © 2026 EPI Labs |
| Languages | English (en-us) |
| Minimum OS | Windows 10 build 19041, x64 |

---

## Age rating (IARC questionnaire)

Answer as a utility with no content. Suggested answers:

| Question area | Answer |
|---|---|
| Type of product | Utility / developer tool, not a game |
| User-generated content | **No.** It displays files the user already has; it does not host or share content |
| Chat, messaging, social features | **No** |
| In-app purchases, subscriptions, ads | **No.** The app is free and has no billing |
| Collects personal information | **No.** No account, no sign-in, no telemetry unless the user turns it on |
| Location, camera, microphone, contacts | **No** |
| Web browser or unrestricted web access | **No** |
| Content that may be unsuitable for minors | **No.** It shows decision records; no imagery, audio or text of its own |
| Expected rating | **3+ / Everyone** |

---

## Restricted capability justification — `runFullTrust`

Paste into the capability declaration in Partner Center:

```
EPI Recorder is a desktop command-line tool packaged with MSIX. It needs full trust to run its bundled executable, read the .epi files the user opens, and write results to the user's working folder. It does not run in the background or start automatically.
```

---

## Notes for the certification reviewer

- The app has two entry points in one package: **EPI Recorder** (Start menu; opens the viewer) and **EPI Recorder command line** (no Start entry; provides the `epi` command).
- To test without a file of your own, download the public sample from https://epilabs.org/insurance/sample-claim-record and open it, or run `epi verify <file>` in a terminal.
- The sample's identity line reads "unknown" by design: the signature is valid, but the reviewer has not pinned the sender's key. That is the honest default, not a failure.
- No network connection is required to open or check a file.

---

## Screenshot plan

Four screenshots, **1920 × 1080**, PNG, saved to `docs/store/screenshots/`.
Use only the public sample files; no personal data, no real customer names, no
terminal history.

| # | File name | What to capture |
|---|---|---|
| 1 | `01-viewer-record.png` | The viewer showing the public sample record: inputs, decision and reason visible in one frame |
| 2 | `02-checks-valid.png` | The same window scrolled to the integrity and signature lines, with the result visible |
| 3 | `03-terminal-verify.png` | A terminal running `epi verify sample.epi --policy strict`, with the report and exit code shown |
| 4 | `04-demo.png` | A terminal running `epi demo --no-browser`, showing the sealed file and the closing panel |

How to take them, on the machine that has the app:

1. Turn on Developer Mode (Settings > System > For developers), then register the unpacked package so the Start menu entry exists.
2. Download `https://epilabs.org/assets/sample.epi` and put it somewhere simple, such as `C:\temp\sample.epi`.
3. Open the viewer, size the window to roughly 16:9, and capture with `Win+Shift+S` or `Alt+PrintScreen`, then save at 1920×1080.
4. For the terminal shots, use Windows Terminal at 1920×1080 with a clean profile (no username in the prompt if you prefer), and clear the screen before running the command.
5. Check each PNG contains no local paths, usernames or unrelated windows before committing.

Do not add screenshots of the Microsoft Store itself, and do not show the
installer's SmartScreen dialog.

---

## Submission checklist (after the package exists)

1. Package identity variables set from Partner Center (`MSIX_IDENTITY_NAME`, `MSIX_PUBLISHER`, `MSIX_PUBLISHER_DISPLAY_NAME`).
2. `Build MSIX (Microsoft Store)` run for the release tag; artifact downloaded.
3. `SHA256SUMS.txt` checked against the `.msix`.
4. Package installed with Developer Mode and tested by hand, including double-clicking a `.epi` file.
5. Listing text above pasted into Partner Center.
6. Screenshots uploaded.
7. `runFullTrust` justification pasted.
8. Submitted for certification. Microsoft signs the package on publication.
