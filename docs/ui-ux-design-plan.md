# UI/UX DESIGN PLAN: VoxClone CLI

> **Notes.** The product is a terminal application, so "pages" are *screens* and "sidebar/top-nav" patterns become *menu patterns*. The template's audiences are mapped like this: **Public/Shared** = screens every launch shows; **Admin** = the System menu; **Staff/Employee** = not applicable (no such role in the PDR); **User** = the voice workflows. The default Bootstrap style system does not apply to a terminal; section 7 uses the TDR's terminal stack (Rich + questionary) instead. Inputs: PDR and TDR for VoxClone CLI.

---

## 1. Design Principles

1. **Menu first, no memorization.** The dropdown menu opens at launch. Every feature is reachable by arrow keys and Enter. Sub-commands exist for scripting only.
2. **One decision per screen.** Each prompt asks one thing (choose profile, then choose input, then choose output). Defaults are pre-selected, so repeated use is "Enter, Enter, Enter."
3. **Never silent.** Anything that takes more than about a second shows what it is doing: loading a model, preparing chunks, converting chunk 7 of 42. The user can always tell working from stuck.
4. **Safe by default, escapable everywhere.** Every screen has **Back**; Ctrl+C cancels the current job cleanly and offers Resume; destructive actions (delete profile) ask for confirmation.
5. **Plain language, fix hints included.** Errors say what happened and what to do, with a code for lookup. No stack traces unless `--debug`.
6. **Color helps, never carries meaning alone.** Every state has an icon and a word as well as a color; `NO_COLOR` and `--plain` fully work.

## 2. Wireframe Reference

Layout conventions (patterns, not pixel mockups):

| Audience | Pattern |
|---|---|
| All screens | **Header bar** (app name, active profile, device, resident model) + **dropdown list** body + **hint footer** (key help) |
| Menus | **Vertical dropdown list**, one item highlighted with `❯`; type-to-filter on lists longer than 7 |
| Forms | **Sequential prompts** (question → answer → next); previous answers echoed in a dim summary line |
| Long operations | **Stage panel** with a multi-bar progress display (see 2.3) |
| Results | **Result panel** (boxed) followed by an "after" dropdown (Play again / Open folder path / Back) |
| Tables | `rich` tables (profiles, jobs, outputs) with the cursor list below for actions |

### 2.1 Launch screen (menu already open)

```
╭──────────────────────────────────────────────────────────────╮
│  VoxClone CLI                                   v1.0         │
│  profile: (none)   device: cuda   model: none   VRAM: 7.6 GB free
╰──────────────────────────────────────────────────────────────╯
  What would you like to do?

   ❯ Text  →  my voice
     Recording  →  my voice
     Voice profiles
     Job history
     System
     Exit

  ↑↓ move   Enter select   Esc back   type to filter
```

### 2.2 Dropdown list with sub-options (Voice profiles)

```
  Voice profiles
   ❯ Enroll a new voice from a file
     Enroll a new voice from the microphone
     Preview a profile
     Rename a profile
     Delete a profile
     ← Back
```

### 2.3 Progress panel during Recording → Voice

```
╭─ Converting  interview.wav  →  voice "me" ──────────────────╮
│  ✔ Split into 42 chunks (3.1–4.9 s)             0.4 s       │
│  ✔ Loaded voice-conversion model                6.2 s       │
│  ● Converting on GPU        ███████████░░░░░░  27/42        │
│  ◌ Cleaning on 12 CPU cores (running in background)         │
│  ◌ Joining                                                  │
│  elapsed 00:48   remaining ≈ 00:27                          │
╰──────────────────────────────────────────────────────────────╯
```

### 2.4 Result panel

```
╭─ Done ✔ ────────────────────────────────────────────────────╮
│  Saved:  outputs/recording_me_20261025_101530.wav           │
│  Length: 02:48   Time taken: 03:05   Speed: 1.1× real-time  │
╰──────────────────────────────────────────────────────────────╯
   ❯ Play again
     Convert another
     Back to main menu
```

## 3. Information Architecture (Sitemap)

### 3.1 Public / Shared (shown to every launch)
- Launch screen with the open main menu
- First-run welcome and consent explanation
- Help / keyboard shortcuts
- About (version, engines, licenses)

### 3.2 Admin: System menu
```
System
├── Model status
├── Free GPU memory
├── Doctor (system checks)
├── Settings
│   ├── Device (auto / cuda / cpu)
│   ├── Worker processes (all cores / number)
│   ├── Chunk length (min–max)
│   ├── Crossfade length
│   ├── Default output (save / play / both)
│   ├── Keep model loaded after job (on/off)
│   └── Reset to defaults
├── Storage (sizes) and Clean temp files
└── ← Back
```

### 3.3 Staff / Employee
**Not applicable.** The PDR defines no staff role.

### 3.4 User: voice workflows
```
Main menu
├── Text → my voice
│   ├── Choose profile
│   ├── Enter text (type/paste, or path to .txt)
│   ├── Emotion (Auto / Calm / Normal / Expressive)
│   ├── Output (Save / Play / Both)
│   └── Run → Result
├── Recording → my voice
│   ├── Choose profile
│   ├── Input (Audio file / Record from microphone now)
│   ├── Output (Save / Play / Both)
│   └── Run → Result
├── Voice profiles  (enroll file · enroll mic · preview · rename · delete)
├── Job history  (list · view · resume · replay · delete)
└── Exit
```

## 4. Key User Flows

### 4.1 First-run setup, enrollment and consent *(replaces "Registration, Login & Password Reset", since there are no accounts)*
1. User runs `docker compose run --rm voxclone`; **menu opens**.
2. First run only: welcome panel explains the tool and the consent rule; user presses Enter.
3. Menu → **Voice profiles → Enroll a new voice from a file** (or microphone).
4. Prompt: *Profile name*. Validation message if the name is taken or has invalid characters.
5. **File path:** user types or tab-completes a path. **Microphone:** a countdown, then a 30 s recording bar with a level meter; user may stop early (≥ 10 s).
6. Tool cleans the sample and shows a **quality panel** (duration, level, noise, clipping) with a plain-language verdict.
7. If quality is poor: dropdown **Use anyway / Re-record / Cancel**.
8. **Consent confirm:** "I own this voice or have the speaker's permission." (Yes / No). No → nothing is saved.
9. Profile saved; dropdown offers **Preview it / Back**.

*Recovery:* wrong file type → `VX-102` with a hint; mic missing → `VX-401` and the file option is offered.

### 4.2 Core Transaction Flow: make speech in my voice

**4.2a Text → my voice**
1. Main menu → **Text → my voice**.
2. Choose profile (dropdown; last used pre-selected; if none exist, offer to enroll).
3. Enter text (multi-line allowed; Enter on an empty line finishes) or a path to a `.txt`.
4. Choose emotion: **Auto** (default) / Calm / Normal / Expressive.
5. Choose output: Save / Play / **Both** (default from settings).
6. Stage panel: *Detecting emotion (loading classifier…)* → *Freeing classifier, loading voice model…* → *Speaking passage 3/8*.
7. Result panel; after-menu: Play again / Another text / Back.
8. *Optional preview:* in Auto mode a table shows each passage and its detected emotion before generation, with **Continue / Change emotion / Cancel**.

**4.2b Recording → my voice**
1. Main menu → **Recording → my voice**.
2. Choose profile.
3. Choose input: **Audio file** (path prompt) or **Record from microphone now** (recording bar, Enter to stop).
4. Choose output.
5. Stage panel (as 2.3): split → load VC model → GPU conversion with a CPU-side background line → join.
6. Result panel with duration, time taken and speed multiple.
7. *Interruption:* Ctrl+C → "Stopping after this chunk…" → panel "Job paused at chunk 17/42. Resume later from Job history."

### 4.3 Error Recovery & Diagnostics *(replaces Ticket Handling, since there is no support desk)*
1. A job fails; the screen shows `✖ Out of memory while converting (VX-301)` and `→ Free GPU memory and resume.`
2. After-menu: **Resume job / Free GPU memory then resume / View log path / Back**.
3. From the main menu, **System → Doctor** runs checks and shows a table: GPU, CUDA, audio in/out, RAM, disk, model cache, each ✔/✖ with a fix hint.
4. **Show log path** prints the log file location for sharing.

## 5. Screen Inventory

**Shared**
- S-01 Launch / main menu
- S-02 First-run welcome and consent explanation
- S-03 Help / shortcuts
- S-04 About

**Voice profiles**
- S-10 Profiles menu
- S-11 Enroll from file (path, name)
- S-12 Enroll from microphone (countdown, recording bar)
- S-13 Sample quality report
- S-14 Consent confirmation
- S-15 Preview profile (playback)
- S-16 Rename profile
- S-17 Delete profile (confirm)

**Text → voice**
- S-20 Choose profile
- S-21 Text entry
- S-22 Emotion choice
- S-23 Emotion preview table (auto mode)
- S-24 Output choice
- S-25 Text job progress panel
- S-26 Result panel (shared with S-35)

**Recording → voice**
- S-30 Choose profile
- S-31 Input choice (file / microphone)
- S-32 File path prompt
- S-33 Microphone recording screen
- S-34 Recording job progress panel (stage panel with CPU/GPU lines)
- S-35 Result panel

**Job history**
- S-40 Jobs table and actions
- S-41 Job detail
- S-42 Resume job progress (reuses S-34/S-25)
- S-43 Delete job (confirm, optionally delete output)

**System (admin)**
- S-50 System menu
- S-51 Model status
- S-52 Free GPU memory result
- S-53 Doctor report
- S-54 Settings menu
- S-55 Setting editor (one per setting)
- S-56 Storage report and Clean temp
- S-57 Error panel (reusable, any `VX-` code)

## 6. Status Badge Convention

Every state uses **icon + word + color**.

| State | Icon / Text | Color (Rich style) | Used for |
|---|---|---|---|
| Success | `✔ Done` | green | Job succeeded, check passed, profile saved |
| Running | `● Running` | cyan | Active stage, active chunk |
| Pending / Queued | `◌ Waiting` | yellow | Upcoming stage, queued chunk |
| Loading model | `⇅ Loading` | magenta | Model load/unload in progress |
| Warning | `⚠ Warning` | orange (bright yellow if 8-color terminal) | Low-quality sample, fallback taken |
| Error / Failed | `✖ Failed` | red | Job failed, check failed |
| Cancelled / Paused | `‖ Paused` | blue | Job interrupted, resumable |
| Skipped / Inactive | `– Skipped` | dim grey | Not applicable stage, unloaded model |

Model-status line in the header: `model: none` (dim), `model: tts ✔ loaded` (green), `model: vc ⇅ loading` (magenta).

## 7. Style Guide Basics

**Default framework note:** Bootstrap is **not applicable** (terminal). The system is **Rich + questionary** per the TDR.

| Token | Hex (dark terminal) | Hex (light terminal) | Use |
|---|---|---|---|
| Primary | `#4FC3F7` | `#0277BD` | Headers, selected item marker `❯`, panel borders |
| Secondary | `#B39DDB` | `#5E35B1` | Section titles, model-loading status |
| Success | `#66BB6A` | `#2E7D32` | Success badges |
| Warning | `#FFB74D` | `#E65100` | Warnings |
| Error | `#EF5350` | `#C62828` | Errors |
| Pending | `#FFD54F` | `#F9A825` | Waiting items |
| Muted | `#9E9E9E` | `#616161` | Hints, skipped, footers |
| Text | terminal default | terminal default | Body text |

- **Fonts:** the terminal's monospace font. Recommended in Windows Terminal: **Cascadia Code** or **JetBrains Mono** (both render the box and badge characters).
- **Characters:** box drawing (`╭ ╮ ╰ ╯ │ ─`), `❯ ✔ ✖ ● ◌ ⚠ ⇅ ‖ –`. If the terminal cannot render them, `--plain` swaps to ASCII (`> [OK] [X] * . ! ~ || -`).
- **Spacing:** one blank line between panels; panels width = min(terminal width, 100).
- **Voice and tone:** short sentences, present tense, no jargon in messages (say "voice model", not "checkpoint").

## 8. Accessibility & Responsiveness

**Target:** the terminal equivalent of **WCAG 2.1 AA**.

- **Contrast:** all palette pairs meet ≥ 4.5:1 against typical dark (`#1E1E1E`) and light (`#FFFFFF`) backgrounds; the two palettes in section 7 are selected automatically from the terminal's reported theme where available, else dark.
- **Not color-only:** every status has an icon and a word (section 6).
- **Keyboard only:** all actions reachable with arrows, Enter, Esc and typing; no mouse needed.
- **`--plain` mode:** no boxes, no animation, one status line per event, ASCII icons; suitable for screen readers and logs. Also enabled by `NO_COLOR` (color only) or `VOXCLONE_PLAIN=1`.
- **Motion:** spinners and live bars update at most 10 times per second; `--plain` disables them.
- **Timing:** no timed prompts except the mic recording, which the user starts and may stop.

**Width breakpoints (terminal columns):**

| Columns | Behaviour |
|---|---|
| < 60 | Single column; header shows only app name; progress bars shrink to 20 chars; tables become two-line records |
| 60-99 | Standard layout, panels fill the width |
| 100-139 | Panels capped at 100 columns, left-aligned |
| ≥ 140 | Same as above; job history table shows extra columns (profile, elapsed, speed) |

Resize is handled live (panels re-render on terminal size change).
