# Guided setup interview

Run this on first use (when `P profile status` says `SETUP: NOT DONE`) or when the user asks for `/prospect setup`.

## How to run the interview
- Assume the user is **new to all of this**. Use plain English, short messages, and explain any term the first time it comes up (e.g. "a *connector* lets Claude use one of your accounts, like Gmail, with your permission").
- **One part at a time.** Never dump every question in one message.
- Use **AskUserQuestion** for choices (it shows buttons). For open answers, ask in a normal message, at most 3 short numbered questions, and wait for the reply.
- Anything can be skipped. If they say "skip" or "not sure", use the default and say what you chose.
- **Save after every part** (profile file + settings), so stopping halfway loses nothing.
- When re-running setup, show what's already saved for each part and ask "Keep this or change it?" rather than starting from blank.
- You never type passwords, create accounts, or click "Connect" for them. You open the right page and they do it.

Throughout, `P` is the tool command and `PROFILE` is the profile file path printed by `P profile init`. Fill in the profile by editing its lines (Edit tool) and replacing "(not answered yet)" with their answers, in their own words, kept short.

---

## Part 0 - Welcome
Run `P profile init`. Then tell them, in your own words:
- What this does:
  1. it filters a Google Maps business list;
  2. it researches each business (contact name and job title, emails, whether it's a good fit);
  3. it builds a spreadsheet, and can write first emails in Gmail if they want.
- Setup takes about 5 minutes. They can skip anything and change it later with `/prospect setup`.
- Their answers are saved privately on this computer in the profile folder (give the path). That folder is separate from the skill, so it's never included if they share the skill.

## Part 1 - What are you automating?
AskUserQuestion with two questions:
1. "What would you like Claude to do for you?" (header `Goal`)
   - **Research prospects**: turn a Google Maps scraper file into a researched list with contacts, emails and a Suitable / Review / Delete status.
   - **Research + write emails**: the same, plus Claude writes a personal first email to each good prospect in your Gmail.
   - **Not sure yet**: explain the two options in 3 lines, then ask again.
2. "What will you start from?" (header `Your list`)
   - **A Google Maps scraper file**: a .csv/.xlsx export with names, addresses, phones and websites.
   - **Just business names**: a list of names, as a file or pasted into the chat. Claude looks up each business's website, address, phone and category first. That's slower than a scraper file, and works best with a town or area.
   - **Nothing yet**: explain both options. A "scraper" tool (open-source scrapers, or services such as Outscraper or Apify) exports Google Maps results as a spreadsheet; or they can simply collect business names. Setup can be finished now.

Save the goal in the profile under "What I'm automating". Also ask (open question): "Roughly how many businesses a day are you hoping to contact?"

## Part 2 - About you and who you're targeting
Ask in one message:
1. What's your business called, and what do you offer? One or two sentences is perfect.
2. Who are you trying to reach? Types of businesses, and which towns, areas or countries.
3. Any kinds of businesses you never want on your list?

Save the answers to "About me and my business" and "Who I'm targeting". If they chose **Research + write emails**, also ask for their name (for signing emails) and their website.

## Part 3 - What makes a good prospect (Suitable / Review / Delete)
1. Read the eligibility rules file (path in `P profile status` → "Eligibility rules"). It's their personal copy.
2. Adapt it to their answers:
   - put their "never target" list under **Delete**;
   - describe their ideal prospect under **Suitable**;
   - keep any of the starter rules that still make sense.
   Keep the same three headings and format.
3. Show a summary of at most 7 bullets saying what becomes Suitable, Review and Delete. Then AskUserQuestion "Do these rules look right?" with **Looks good** / **I want to change something**. Repeat until it looks good.
4. Save the file with Write.

## Part 4 - Cleaning up the scraper file
Explain in one line: before any research, unwanted rows can be removed automatically, and every removed row is listed with its reason on a "Filtered out" tab.

AskUserQuestion (multiSelect) "Which rows should be removed automatically?" (header `Filters`):
- **Permanently closed (Recommended)**
- **Duplicates (Recommended)**: same Google listing, phone number or website.
- **Too few reviews**: fewer than a number you choose.
- **Certain categories**: e.g. remove "Supermarket", or keep only "Plumber".

Then save. Use exactly these settings:
- Closed: `P settings set filters.drop_permanently_closed true` (or `false`).
- Duplicates: `P settings set filters.dedupe_on '["place_id","phone","website_domain"]'` (or `'[]'` if unticked).
- Too few reviews: ask for the number, then `P settings set filters.min_reviews <N>`.
- Categories: ask which to remove and/or which to keep only, then:
  - `P settings set filters.exclude_if_category_contains '["supermarket","bank"]'`
  - `P settings set filters.keep_only_if_category_contains '["plumber"]'`

Then ask (open): "Do you already have your own filtering steps, for example in notes or a video? Describe them and I'll set up the ones I can." Map what you can to the filters above. Write the full description under "My filtering steps" in the profile. If a step can't be automated with these filters, say so plainly. It stays in the profile, and the user can apply it in Google Sheets.

## Part 5 - Browser for Facebook checks
Explain: many businesses show their email only on their Facebook page, and Facebook hides it unless you're logged in. Claude checks those pages in a browser where *you* are logged in. It only reads pages; it never posts, messages, likes or types passwords.

**Work out which browsers are available:**
- **Built-in browser**: available if tools named `mcp__Claude_Browser__...` exist (the Claude desktop app).
- **Claude in Chrome**: try ToolSearch `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__get_page_text`. If they load, call `tabs_context_mcp`. If it says the extension isn't connected, Chrome is "not connected yet".

AskUserQuestion "Which browser should Claude use for Facebook checks?" (header `Browser`). Only offer what can work:
- **Built-in browser (Recommended)**: if available. Nothing to install, and it's kept separate from your everyday Chrome, so your personal logins stay apart.
- **Claude in Chrome**: uses your own Chrome through the Claude extension (needs a paid Claude plan).
- **Skip Facebook checks**: Facebook pages get listed in the sheet for you to check by hand.

**If they choose Chrome and it isn't connected**, guide them step by step and wait for "done" after each step:
1. In Chrome, open https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn and click **Add to Chrome**.
2. Click the puzzle-piece icon in Chrome's toolbar, pin **Claude**, open it, and sign in with the same Claude account they use here.
3. If they use the `claude` terminal app: type `/chrome` and choose **Enabled** (or restart with `claude --chrome`). In the desktop app, come back here once it's signed in.
4. Check again with `tabs_context_mcp`. If it's still not connected, offer the built-in browser instead (if available) or skip for now.

**Log in to Facebook.** Open https://www.facebook.com/ in the chosen browser:
- built-in: `mcp__Claude_Browser__navigate`;
- Chrome: `tabs_create_mcp`, then `navigate`.

Ask them to log in on that page themselves, then answer AskUserQuestion "Are you logged in to Facebook?" with **Done** / **Skip for now**.

On Done, check with `get_page_text`: if the page still shows a login form ("Log in", "Create new account"), say so and let them retry.

Save:
- `P settings set browser.name built-in` (or `chrome` / `none`);
- `P settings set browser.facebook_checks true` (or `false`).

## Part 6 - LinkedIn (optional)
Explain plainly:
- By default, Claude finds contacts by **searching Google for LinkedIn profiles**. No LinkedIn login is needed, and there's no risk to any account. This works well for most businesses.
- **Optional extra:** Claude can also look businesses up on LinkedIn while logged in, for the ones Google misses.
- **Honest warning:** LinkedIn's rules don't allow automated browsing, or more than one account per person, and it restricts accounts it suspects. If they turn this on, they should use a **separate ("burner") account they can afford to lose, never their main profile**. Claude keeps it slow, limits it to a set number of lookups a day, and stops immediately at any security check.

AskUserQuestion "Turn on logged-in LinkedIn lookups?" (header `LinkedIn`):
- **No, Google search is enough (Recommended)**
- **Yes, with a separate account**

**If yes:**
1. They need a browser. If they skipped Part 5, ask them to pick one now (same choices).
2. If they don't have a separate account yet, they create it themselves at https://www.linkedin.com/signup (Claude can't create accounts). With Chrome, suggest they make a separate Chrome profile for it (Chrome menu → profile icon → **Add**), so their main LinkedIn stays logged in elsewhere. With the built-in browser, nothing extra is needed: it's already separate.
3. Open https://www.linkedin.com/login in the chosen browser. They log in themselves and say **Done**. Check with `get_page_text` that it's no longer the sign-in page.
4. AskUserQuestion "How many LinkedIn lookups per day, at most?": **15** / **25 (Recommended)** / **40**.
5. Save:
   - `P settings set linkedin.browser_lookups true`
   - `P settings set linkedin.daily_limit <N>`

**If no:** `P settings set linkedin.browser_lookups false`.

## Part 7 - Emails (only if their goal includes emails)
Explain: for each **Suitable** business with an email, Claude can write a short, personal first email and put it in their Gmail.
- **Drafts (recommended):** Claude saves drafts; you read them and press Send yourself.
- **Send:** Claude sends them, but only after you approve each batch in this chat.

**Check the Gmail connector.** ToolSearch `gmail create draft`. If a tool ending in `create_draft` appears, Gmail is connected.

**If it's not connected:**
1. If the tools `mcp__mcp-registry__search_mcp_registry` and `mcp__mcp-registry__suggest_connectors` exist (load them with ToolSearch `select:mcp__mcp-registry__search_mcp_registry,mcp__mcp-registry__suggest_connectors` if needed):
   - search with `["gmail"]`;
   - call `suggest_connectors` with the Gmail result's `directoryUuid` and keywords `["email"]`. This shows a **Connect** button;
   - tell them to click it, sign in with the Google account they send email from, and allow access.
2. Otherwise give the steps:
   - open https://claude.ai/customize/connectors (in the desktop app you can also click **+** next to the message box → **Connectors** → **Browse connectors**);
   - find **Gmail** → **Connect**;
   - sign in to Google → **Allow**.
3. Wait for "done", then check again with ToolSearch. If it still isn't there, they may need to start a new Claude Code session (or type `/mcp` in the terminal app to check). Save email writing as off for now, note it in the profile, and carry on.

**Ask the email choices.** AskUserQuestion:
1. "How should emails be handled?" (header `Emails`): **Gmail drafts (Recommended)** / **Send after I approve each batch**
2. "Most emails per day?" (header `Daily limit`): **20** / **30 (Recommended)** / **50**. Explain: an email address that suddenly sends lots of cold emails lands in spam, so start low and raise it over a few weeks.

Then ask in one message:
1. How should emails be signed? (name, role, business)
2. Your business postal address. Marketing emails legally need one in the US, and it's expected in the UK.
3. In a sentence or two, what should the first email say or offer, and in what tone? (friendly, professional, casual)

Optionally they can paste an example email they like.

Save:
- the answers into the profile's "Emails" section;
- `P settings set outreach.mode draft` (or `send`);
- `P settings set outreach.daily_limit <N>`.

Tell them about the do-not-contact list: if someone replies "no thanks", they just tell Claude "add name@example.com to do not contact" (you run `P dnc <address>`), and that address is never emailed again.

If their target areas include the UK, add one line: under UK rules (PECR), emailing sole traders and most partnerships needs their consent; limited companies are fine.

## Part 8 - Getting the list into Google Sheets
AskUserQuestion "How do you want the finished list in Google Sheets?" (header `Sheets`):
- **I'll import it myself (Recommended)**: 3 clicks in Google Sheets: File → Import → Upload.
- **Claude adds it to my Google Sheet**: needs the Google Sheets connector. Each run is added as new tabs.

**If they want Claude to add it:**
1. Check with ToolSearch `google sheets update values`.
2. If it's missing, connect it exactly like Gmail in Part 7 (search `["google sheets"]`, then `suggest_connectors` with keywords `["spreadsheets"]`, or use the claude.ai connectors page).
3. Ask them to make a blank Google Sheet (open https://sheets.new) and paste its link.
4. Save:
   - `P settings set sheets.mode connector`
   - `P settings set sheets.spreadsheet_url "<link>"`

**Otherwise:** `P settings set sheets.mode manual`.

## Part 9 - Finish
1. Update the profile's "Tools" section and the "Last updated" date.
2. Run `P profile done`, then `P profile status`.
3. Show a short summary of their setup (5-7 lines).
4. Tell them:
   - where their profile is, and that they can edit it in any text editor or re-run `/prospect setup`;
   - how to start: put the scraper file in the `input/` folder (create it if needed) and run `/prospect`.
5. AskUserQuestion "Start a small test run now (10 businesses)?": **Yes, test with 10** / **Not now**.
   - On yes: if they have a file (or want to paste some business names now), go back to SKILL.md and start a new list with `--limit 10`.
   - If they don't have a list yet, tell them to run `/prospect` when they do. They can drop a file in `input/` or paste names into the chat.
