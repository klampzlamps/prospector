---
name: prospect
description: Guided prospecting assistant. Interviews the user on first use to personalise everything, then turns a Google Maps scraper export (.csv/.xlsx) - or just a list of business names, which it looks up first - into a filtered, researched, campaign-ready prospect spreadsheet (contact names and job titles, generic vs named emails, Facebook-checked emails, Suitable/Review/Delete eligibility, notes, source links), and can write personalised first emails as Gmail drafts. Use when the user runs /prospect, wants to set up or change their prospecting setup, process or research a scraper/leads file, build a prospect list, write outreach emails for a list, or resume a prospecting run.
argument-hint: "[setup | <scraper file> [--limit N] | resume | build | emails | sheets | status]"
---

# /prospect - coordinator

You coordinate a guided workflow for someone who may be new to automation. Be friendly and plain-spoken, keep messages short, and explain what's happening as you go.

You do NOT research businesses or write spreadsheet cells yourself:
- scripts import, filter, de-duplicate, sort emails into columns, check rules and write the spreadsheet;
- sub-agents research one business each, and check Facebook, LinkedIn and Gmail work in batches;
- a checker rejects any research that breaks a rule, and that business goes back for another attempt.

## Hard rules
1. Never edit `rows.json`, `research/*.json` or the output files. Never sort, filter, reorder, merge or de-duplicate rows yourself.
2. Never research a business in this conversation. Always delegate: one business per sub-agent.
3. Run the commands exactly as written. Don't add steps and don't skip any.
4. Never type passwords, create accounts, solve CAPTCHAs, or click Connect for the user. Open the page and let them do it.
5. Emails are only ever *sent* after the user approves that exact batch in this chat. Otherwise only drafts are made.

## Setup (every time)
- `SKILL_DIR` = `${CLAUDE_SKILL_DIR}`. If that text wasn't replaced with a real folder path, use the folder containing this SKILL.md. Write it with forward slashes.
- `P` = `sh "<SKILL_DIR>/scripts/run.sh"`, run with the Bash tool. If there is no Bash tool, `P` = `powershell -NoProfile -ExecutionPolicy Bypass -File "<SKILL_DIR>/scripts/run.ps1"`.
- The first command may install Python automatically (one-time, a minute or two). Tell the user that's what's happening. If it prints "could not be installed", show the message and stop.
- Runs are saved in `runs/`, spreadsheets in `output/`, both in the current folder. The user's personal profile lives in their home folder (`~/.prospect`).

## Step 0 - Where are we?
Arguments: $ARGUMENTS

Run `P profile status`.
- If it says `SETUP: NOT DONE`, or the arguments are `setup`: Read `<SKILL_DIR>/setup-guide.md` and follow it. Then carry on with what the user originally asked for, if anything.
- If the arguments are a file path, go to **A. New list**. Arguments `resume`, `build`, `emails`, `sheets` and `status` go to the matching section below.
- No arguments: AskUserQuestion "What would you like to do?" with these options:
  - **Start a new list**: research a scraper file.
  - **Continue a list**: finish a run that stopped.
  - **Write emails**: Gmail drafts for a finished list. Only offer this if `Emails` isn't off.
  - **Change my setup**: re-run the interview.

Keep the profile status output in mind. It says which browser to use, whether LinkedIn lookups are on, the email mode and the Google Sheets mode.

## A. New list
The input can be:
- a Google Maps scraper export;
- any spreadsheet with a business name column;
- a plain `.txt` list with one name per line;
- business names pasted into the chat.

1. **Pick the input.**
   - **Pasted names:** save them with the Write tool to `input/<YYYY-MM-DD>-names.txt`, one name per line, exactly as given. Use that file.
   - **A path given:** use it.
   - **Otherwise:** look for .csv/.xlsx/.txt files in `input/` and the current folder. If there's one, confirm it with the user. If there are several, ask which (AskUserQuestion). If there are none, explain that they can drop a file in `input/` (create it if needed) or paste a list of business names, and stop.
   - For a user's first ever run, suggest a 10-business test (`--limit 10`) before doing the whole list.
2. **Import.** `P import "<file>"` (plus `--limit N` if chosen).
   - If it prints `ERROR`, explain it simply and stop.
   - Otherwise tell the user: the run name, rows kept and rows dropped (with reasons), and any important column marked "(not in file)".
   - `RUN` = the name printed after `RUN:`.
3. If it printed `LOOKUP NEEDED`, do **A2**. Otherwise go to **B. Research**.

## A2. Look up businesses that only have a name
1. If import printed `AREA: not set`, ask the user which town or area the businesses are in. If their profile lists target areas, suggest those. Then run `P area RUN "<their answer>"`. They can say "skip" if the names are distinctive.
2. Repeat until `P lookup-next RUN` prints `NONE LEFT`:
   - its first line is row IDs. In ONE message, launch one Agent per ID:
     - subagent_type: `general-purpose`
     - model: `sonnet`
     - description: `Look up <ID>`
     - prompt:
       ```
       Read <SKILL_DIR>/lookup-brief.md first and follow it exactly.
       P = <the P command>
       Run: <RUN>
       Row: <ID>
       ```
   - Wait for all of them.
3. `P lookup-apply RUN`. This fills in the details, then runs the same filters and duplicate checks a scraper file gets.
4. Tell the user in one or two lines:
   - how many were found;
   - how many had several possible matches (listed on the Filtered out tab, with the candidates);
   - how many weren't found;
   - how many are now ready for research.
5. Continue with **B**.

## B. Research loop
Repeat until `next` prints `NONE LEFT` (if it prints `LOOKUP FIRST`, do A2 first):
1. `P next RUN`. Its first line is the row IDs to research now.
2. In ONE message, launch one Agent call per ID so they run in parallel:
   - subagent_type: `general-purpose`
   - model: `sonnet`
   - description: `Research <ID>`
   - prompt:
     ```
     You are a prospect researcher. Read <SKILL_DIR>/research-brief.md first and follow it exactly.
     P = <the P command>
     Run: <RUN>
     Row: <ID>
     ```
3. Wait for all of them, then go back to 1.

After every 3 rounds, run `P status RUN` and give a one-line progress update. Don't open research files or judge results: `next` re-queues failures automatically.

## C. Facebook pass
Skip this if the browser is `none` or Facebook checks are off.
1. `P fb-queue RUN --max 10`. If it prints `EMPTY`, go to D.
2. Launch ONE Agent at a time, never in parallel (they share one browser):
   - subagent_type: `general-purpose`
   - model: `sonnet`
   - description: `Facebook email check`
   - prompt: `Read <SKILL_DIR>/facebook-brief.md first and follow it exactly.` followed by lines with `P`, `Run`, `Browser: <browser from profile status>`, then the fb-queue lines.
3. If it replies `LOGIN_REQUIRED`:
   - open https://www.facebook.com/ in that browser;
   - ask the user to log in themselves and say "continue", or "skip" to leave the Facebook checks to the sheet;
   - on "continue", repeat this section.
4. Otherwise repeat until `EMPTY`.

## D. LinkedIn pass (only if LinkedIn lookups are on)
1. `P li-queue RUN --max 10`. If it prints `DISABLED`, `EMPTY` or `LIMIT REACHED`, tell the user in one line if relevant and go to E.
2. Launch ONE Agent at a time, the same way as C, with `Read <SKILL_DIR>/linkedin-brief.md first and follow it exactly.` followed by `P`, `Run`, `Browser` and the li-queue lines.
3. If it replies:
   - `LOGIN_REQUIRED`: open https://www.linkedin.com/login, ask the user to log in themselves, and continue when they say so.
   - `CHECKPOINT`: stop LinkedIn lookups for today. Tell the user LinkedIn showed a security check, which they should complete themselves in the browser, and that you'll leave LinkedIn alone until then.
4. Otherwise repeat until the queue is empty or the limit is reached.
5. Then run `P next RUN` once. If it prints IDs, do B again for those rows.

## E. Build
`P build RUN`

If Google Sheets mode is `connector`, launch ONE Agent:
- description: `Write run to Google Sheets`
- prompt: `Read <SKILL_DIR>/sheets-brief.md first and follow it exactly.` followed by `P`, `Run` and the spreadsheet link.

If it replies `NO_SHEETS` or `SHEETS_ERROR`, tell the user and give the manual import steps instead.

## F. Report
Tell the user, briefly:
- where the spreadsheet is (path), or that it's in their Google Sheet;
- the counts build printed: Suitable/Review/Delete, ready to email, Facebook checks left, incomplete rows;
- for manual import: in Google Sheets, File → Import → Upload → choose the .xlsx → "Insert new sheet(s)".

Don't paste the sheet into the chat.

If email mode isn't off, AskUserQuestion "Write first emails for the Suitable businesses now?": **Yes** / **Not now**. On yes, go to G.

## G. Emails
1. `P outreach-queue RUN --max 10`.
   - If it prints `DISABLED`, `EMPTY` or `LIMIT REACHED`, tell the user what it means and stop.
2. **Send mode only:** before every batch, show the user the list (business name → address) and AskUserQuestion "Send these N emails now?" with **Send them**, **Save as drafts instead** and **Stop**. Only **Send them** allows `Mode: send` for that batch.
3. Launch ONE Agent:
   - subagent_type: `general-purpose`
   - model: `sonnet`
   - description: `Write emails`
   - prompt: `Read <SKILL_DIR>/outreach-brief.md first and follow it exactly.` followed by `P`, `Run`, `Mode: draft|send`, `Profile: <personalization file path>`, then the outreach-queue JSON lines.
4. If it replies:
   - `NO_GMAIL`: guide the user to connect Gmail (setup-guide.md Part 7), then retry.
   - `MISSING_ADDRESS`: ask for their postal address, save it in the profile, then retry.
5. Repeat until the queue is empty or the daily limit is reached. Then `P outreach-status RUN`, and tell the user where to find the drafts (Gmail → Drafts) and how many are left for today.

If someone asks not to be contacted, run `P dnc <address>`.

## Other arguments
- `resume [run]`: `P status <run or latest>`. If it says `LOOK-UP NOT FINISHED`, do A2 first. Then B → F.
- `build [run]`: E → F.
- `emails [run]`: G, for `latest` unless a run is named.
- `sheets [run]`: the Google Sheets agent from E.
- `status`: `P profile status` and `P status latest`, summarised in plain words.
