# /prospect: your guided prospecting assistant

Turn a Google Maps business list into a researched, ready-to-email prospect spreadsheet, and optionally get personal first emails waiting in your Gmail drafts. You don't need any technical knowledge. The first time you use it, Claude interviews you for about 5 minutes and sets everything up with you.

## What you need
- **Claude Code**: the **Code** tab in the Claude desktop app (easiest), or the `claude` terminal app. A paid Claude plan is needed for the optional Chrome extension.
- **A list of businesses**, in any of these forms:

  | You have | What happens |
  |---|---|
  | A Google Maps scraper export (`.csv` / `.xlsx`) | Used directly. Fastest. |
  | A spreadsheet with just a business name column, or a `.txt` with one name per line | Claude **looks up** each business's website, address, phone, category and whether it's still open, then carries on as normal. |
  | Names you paste into the chat | Saved to `input/` as a list, then looked up the same way |

  Names-only lists work best with a town or area. If your list doesn't include one, Claude asks for it. Names matching several businesses (e.g. "Quality Plumbing" in a big city) go on the **Filtered out** tab with the possible matches listed, so you can add detail and re-run.

Everything else gets set up during the interview. Python is installed automatically if it's missing.

## Getting started
1. Open this folder in Claude Code.
2. Type `/prospect`. The first time, it walks you through setup:

   | Part | What it asks or sets up |
   |---|---|
   | Your goal | Research prospects only, or research + write emails |
   | About you | Your business, what you offer, who you want to reach, who to avoid |
   | Good-prospect rules | Your personal Suitable / Review / Delete rules, drafted from your answers for you to approve |
   | Filters | What to remove automatically: closed businesses, duplicates, few reviews, categories |
   | Browser | For Facebook checks: the app's **built-in browser** (no install) or **Claude in Chrome** (guided install). You log in to Facebook yourself. |
   | LinkedIn (optional) | Logged-in lookups with a separate account, with a daily limit (see below) |
   | Emails (optional) | Connect Gmail, then set your tone, signature, address and daily limit |
   | Google Sheets | Import the file yourself, or let Claude add each run to your Google Sheet |
3. Put your file in the `input/` folder (or paste business names into the chat) and type `/prospect` again. Your first run is a 10-business test, so you can check the results before doing a whole list.

Other things you can type:

| Command | What it does |
|---|---|
| `/prospect` | A menu: start a list, continue one, write emails, change setup |
| `/prospect setup` | Redo or change any part of the interview |
| `/prospect resume` | Carry on a run that stopped |
| `/prospect emails` | Write Gmail drafts for the latest finished list |
| `/prospect status` | Show your setup and the latest run's progress |

## Your personal settings
Your answers are saved **on your computer, in your home folder** (`~/.prospect/`, e.g. `C:\Users\<you>\.prospect\` on Windows). They are never saved inside the skill or this project, so sharing either never shares your details.

| File | What it's for |
|---|---|
| `personalization.md` | Your profile: business, offer, targets, email style. Claude reads it when researching and writing emails. Edit it in any text editor. |
| `eligibility.md` | Your own Suitable / Review / Delete rules |
| `settings.json` | Your choices (filters, browser, limits). Easiest to change with `/prospect setup`. |
| `do-not-contact.txt` | Addresses or whole `@domains` that are never emailed. Tell Claude "add name@x.com to do not contact". |
| `contacted.json` | Everyone already emailed, so nobody gets a second first email |

## What each part does, and why it's reliable
| Step | Who does it | Why it stays reliable |
|---|---|---|
| Import, filter, de-duplicate | Script | Identical every time. Rows keep the scraper's order and are **never sorted**. Every dropped row is listed with its reason. |
| Look-up (names-only lists) | One AI helper per business | Must confirm it's the right business from two sources and record where each detail came from; filters and duplicate checks run again afterwards |
| Research | One AI helper per business | A short, focused job each time, so nothing drifts by row 50 |
| Rule checks | Script | Research that breaks a rule is rejected and redone (up to 3 tries) |
| Facebook / LinkedIn checks | One AI helper in your logged-in browser | Read-only, one page at a time, with daily limits |
| Generic vs named emails | Script | info@ / sales@ → business column; the contact's own address → contact column |
| The spreadsheet | Script | Fixed columns, fixed formatting |
| Emails | One AI helper per batch | Your profile's tone and details, a daily limit, no double-emailing, the do-not-contact list respected. **Drafts by default.** |

Rules every business is checked against:
- Contacts are searched **website → Google → LinkedIn**, stopping once a marketing or owner contact is found.
- **Facebook is always checked**, even if the website already has an email. Google is searched for an email if the website and Facebook have none.
- **People found on the company website are never mentioned in the notes**, by name or by role.
- URLs go only in the SOURCE LINKS column, never in the notes.
- Eligibility is exactly Suitable, Review or Delete, with evidence and a link.
- Every name and email has the link it was found on, so nothing is guessed.

## The spreadsheet columns
| Column | What's in it |
|---|---|
| CONTACT NAME | `Name (Job Title)`, the best marketing or owner contact found |
| BUSINESS E-MAIL ADDRESS | Generic addresses: info@, sales@, the business name @gmail.com |
| CONTACT E-MAIL ADDRESS | Named addresses: john@, j.smith@ |
| ACTIONS | What you need to do: "Ready to email", "Check Facebook page for an email", "Review eligibility" |
| ADVERTISING ELIGIBILITY | Suitable / Review / Delete |
| JUSTIFICATION | The evidence behind the status |
| NOTES | Research notes useful for your pitch |
| SOURCE LINKS | Every verification link, labelled with what it proves |
| AUDIT NOTES | How the research went, and any problems |
| ROW ID | Links back to the research file in `runs/` |

## Connecting tools (the interview does this with you)
- **Built-in browser** (Claude desktop app): nothing to install. It's kept separate from your normal Chrome.
- **Claude in Chrome**:
  1. Install the **Claude** extension from the Chrome Web Store.
  2. Sign in with your Claude account.
  3. In the terminal app, type `/chrome` and choose Enabled.
- **Gmail / Google Sheets connectors**: the interview shows a **Connect** button. Or go to [claude.ai/customize/connectors](https://claude.ai/customize/connectors), or in the desktop app click **+** next to the message box → Connectors.
- Claude never types your passwords and never connects anything without you clicking.

## About LinkedIn
By default, contacts are found by **searching Google for LinkedIn profiles**. That needs no login and puts no account at risk.

Optionally, Claude can also look businesses up on LinkedIn while logged in, for the ones Google misses. LinkedIn's rules don't allow automated browsing or second accounts, and it restricts accounts it suspects. If you turn this on:
- use a **separate account you can afford to lose**, never your main profile;
- Claude keeps lookups slow and limited (25 a day by default);
- Claude stops at any security check, which you complete yourself.

## Sharing it with someone else
The whole skill is the folder `.claude/skills/prospect/`. To share it:
- send that folder; they put it in their own project's `.claude/skills/` folder, or in `~/.claude/skills/` to use it in every project; **or**
- share this whole project folder. The `.gitignore` keeps `input/`, `runs/` and `output/` (your lead data) out of git.

It contains no personal details. Each person's answers are created in their own home folder when they first run `/prospect`.

## Before you send emails
- **Warm up slowly.** A new email address that suddenly sends lots of cold emails lands in spam. Start at 20-30 a day and raise it over a few weeks.
- **Include your postal address and an opt-out line.** Every email written includes both. US law (CAN-SPAM) requires them, and they're expected in the UK.
- **UK:** under PECR, emailing sole traders and most partnerships needs their consent. Limited companies are fine.
- **Honour opt-outs.** If someone says "no thanks", tell Claude to add them to do-not-contact.
# prospector
