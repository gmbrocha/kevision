# Demo Script — Revision Review Tool

A walkthrough for showing the app to a non-technical estimator over Teams or in person. Designed to be skimmed live during the call.

## Before the call (5 min setup)

Scan a workspace and start the GUI so there's no waiting on scan during the demo:

```powershell
python -m revision_tool scan revision_sets workspace_demo
python -m revision_tool serve workspace_demo --port 5000
```

Open `http://127.0.0.1:5000` in one browser tab. Keep a File Explorer window open pointed at `workspace_demo\outputs\` for the end. Keep Excel ready to open a CSV.

If sharing a single screen over Teams, drag the browser, File Explorer, and terminal onto the monitor you plan to share, and keep this script on the other monitor.

## Opening pitch (30 seconds)

> "So the problem we've been chewing on: when you get a stack of revision drawings, you're spending most of your time on two things — figuring out which version of every sheet is the *latest*, and then finding every clouded change so you can price it. That's all hand work right now. What I want to show you is a little local app that does the boring parts so you can just sit down and review."
>
> "This whole thing runs on your laptop. Nothing leaves your machine. No cloud, no login, no subscription."

## The walkthrough — six stops

### 1. Start from a folder of PDFs (no app)

Flip to File Explorer. Show `revision_sets/` with folders like `Revision #1 - Drawing Changes`, `Revision #2 - Mod 5 grab bar supports`, etc.

> "Whatever the architect sends you lands in a folder like this. You don't organize anything — you just drop the package in and we take it from there."

### 2. The Dashboard — "where am I right now?"

Open the app. Point at the **Pricing Readiness** row:

> "These four tiles answer every question you'd be asking when you sit down: how close am I to a clean pricing list, how much is left to look at, did we pick the right latest version of each sheet, and is there anything weird I need to deal with first."

Hover each card:

- **Ready for Pricing** → "These are the rows that will show up in the final spreadsheet. Zero right now because I haven't reviewed anything yet."
- **Candidates to Review** → "65. These are the clouded changes the scanner found." Then casually: "It actually found 235 originally — we filtered out the noise, sheet-index pages, room labels, that kind of stuff, so you don't waste time on those."
- **Conformed Sheets** → "70 latest sheets. 57 got superseded by later revisions. Click here and I'll show you."

### 3. The Conformed page — "did we pick the right latest version?"

Click **Conformed Sheets**.

> "This is your gut-check. One card per sheet. The big image is the *latest* version — whatever we decided wins. These little chips at the bottom are the older versions that got superseded."

Pick any card, hover it:

> "So AE113 has Rev 2 as the latest, and here's the Rev 1 version that got bumped. If I look at the thumbnail and it's clearly the wrong version, you'd catch it instantly."

Show the toggle at the top:

> "Default shows only sheets that actually got revised — 22 of them — because that's where mistakes would happen. If you want to see every sheet, flip it to All."

Click into a card → lands on the sheet detail page with the clouded regions highlighted.

> "Click any sheet and you can see exactly where the clouds are. Same thing you'd do in Bluebeam."

### 4. The Review Queue — "what's left to look at"

Click **Queue** in the top nav.

> "This is where you spend most of your time. The scanner pulled 65 real candidates; they're all here waiting."

Click into any one with decent text (pick a hot-water-pipe or masonry one).

> "Here's what the scanner grabbed. Here's the crop from the actual drawing. You just read it, fix the text if OCR goofed, and hit Approve or Reject."

Approve one. Then navigate to another — show the **Save + Next Pending** button:

> "Approve this one, it drops you straight into the next one. Same keyboard shortcut stuff you'd expect."

Click back to Dashboard briefly:

> "See — Ready for Pricing went from 0 to 1. Candidates to Review dropped by 1. Numbers move as you work."

### 5. Attention items — "the scanner flagged these as weird"

If the Needs Attention card is still red, click it.

> "These are ones where the scanner isn't confident — the text is garbled, or it couldn't find a detail callout. We flag them so you don't accidentally approve garbage. You can still approve them, you just have to eyeball them first."

### 6. Export — the deliverable

Click **Export** in the top nav, hit **Run Export**.

Then open a terminal and show the CLI version for the cleaner summary:

```powershell
python -m revision_tool export workspace_demo --force-attention
```

> "When you're done reviewing, one button. This is what drops out."

Walk through the plain-English summary line by line:

> "X rows ready for pricing → that's the spreadsheet. Y candidates still being reviewed. Conformed set, latest/superseded counts. Anything that got filtered as noise is listed here so you can see nothing was hidden from you."

Flip to File Explorer → `workspace_demo\outputs\`:

> "Every one of these is a CSV you open in Excel. Or this — " (point to `conformed_preview.pdf`) " — is a single PDF that stitches together all the latest sheets in order, with red banners on any old version that got superseded, so you've got one clean drawing set."

Double-click `pricing_change_log.csv` to open it in Excel:

> "**This** is the file you'd hand to an estimator. Sheet, detail ref, scope description, approved status, which revision it came from."

## Questions to ask him (save 10 min for this)

After the demo, shut up and ask these in order:

1. "Does this match what you actually do when revisions come in? What's different?"
2. "If I dropped you into this tomorrow morning, where would you start? The queue? The conformed view? Somewhere else?"
3. "Look at that pricing log. What's missing that an estimator would want in there?" *(detail titles, quantities, room numbers, cost codes, takeoff refs...)*
4. "Of the 65 candidates on screen — without reading the text, just by looking — how many of these feel like real scope vs. garbage? Ballpark."
5. "What's the biggest time-sink we *didn't* touch?" *(architect clarifications? coordinating with subs? the Bluebeam comparison itself?)*
6. "If you had to pick one thing for me to work on next, what is it?"

## Likely questions & answers

| He asks | You say |
| --- | --- |
| "Does this work on Bluebeam files?" | "Any PDF. Bluebeam just exports PDFs." |
| "What if it misses a clouded change?" | "It will. That's why Review Queue exists — you're still the last pair of eyes. But it cuts the first 80% of the boring sorting work." |
| "Can I add my own notes?" | "Yes — every item has a Reviewer Notes field. They come out in the CSV." |
| "Is my data going anywhere?" | "No. Local only. There's optional ChatGPT integration for clarifying weird items, but it's off by default and has to be turned on with a key." |
| "What happens when Rev 3 shows up?" | "Drop it in the folder, re-run scan. Anything you already approved stays approved. Only new stuff shows up in the queue." |
| "What if the text is OCR'd wrong?" | "You edit it right there in the review panel before approving. The corrected text is what goes into the pricing log, not the OCR." |
| "Can you do [X]?" | "Not yet. Let's add it to the list." **(Write it down in front of him — non-techies notice.)** |

## Tone notes

- **Never say "the scanner", "the exporter", "the queue"** as if they're objects he needs to know about. Say "it grabs", "it spits out", "the list of stuff to look at".
- **When something goes wrong in the demo, say so and move on.** "That one's garbage — yep, that's why reject exists. Next."
- **Stop when the numbers on the dashboard update.** That's the "oh shit, I get it" moment — give him a second to absorb it before talking again.
- **End with him owning a TODO**, not you. "So if you could send me five or six real-world pricing items from a past project in the format you'd actually want them in, that's what I'll build next."

## Teams screen-sharing cheat sheet

1. In the Teams meeting controls bar, click the **Share** icon (monitor-with-arrow, top-right of the call window).
2. A tray pops up with tiles. With two monitors you'll see **Screen #1** and **Screen #2** as separate tiles. Pick the screen *opposite* from the one with this script on it.
3. Shared screen gets a red/yellow border to confirm.
4. Stop sharing via the floating Teams toolbar at the top, or `Ctrl+Shift+E`.

Gotcha: newly opened windows (Excel, File Explorer) may open on whichever monitor was last active, not the shared one. If one pops up on the wrong side, just drag it over — no panic.
