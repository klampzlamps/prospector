# Prospect research brief (one business)

You research ONE business and save what you find as a JSON file. A checker script tests the file against the rules below. You are finished only when it prints `PASS`. Do the steps in order; don't skip any and don't add any.

Your prompt gives you `P` (the command that runs the tool), `Run` and `Row`. Run each `P ...` command with the Bash tool (or PowerShell if `P` starts with `powershell`), exactly as written.

## Never
- Never guess or invent a name, job title or email. Never build an address from a pattern (firstname@domain). Everything you record must have been seen on a page or search result, and you record that URL.
- Never log in, sign up, send a message, follow, like or submit a form anywhere.
- Never edit `rows.json`, another row's file, or the scripts.
- Never mention anyone you found on the company website in `notes`, `eligibility.justification`, `audit_notes` or `action_notes`. That means not by name and not by role ("the owner"). Their details belong only in the contact fields.
- Never put URLs or email addresses in those text fields. URLs go in the URL fields; the builder puts them in the SOURCE LINKS column.

## Step 1 - Load the row
`P row <Run> <Row>`
- If it says the row **already PASSES**, reply with the Step 9 line and stop.
- If it says **A PREVIOUS ATTEMPT FAILED**, Read the existing file, fix only the problems listed (doing any research they need), save it, and go to Step 8.
- Otherwise start from the TEMPLATE it prints. You'll save it to the path it shows.

Also Read the **eligibility rules** file whose path the `row` command printed. These are the user's own rules. If it printed a user profile path, Read that file's "Who I'm targeting" section too, so your notes focus on what matters to this user.

## Step 2 - Is it still trading?
Decide this from the evidence you gather in Steps 3-6 (set it before saving):
- **closed**: clear evidence it has shut down for good (Google says "Permanently closed", the website says closed or retired, the company is dissolved). Then:
  - set all three `contact_search` outcomes, `facebook.status` and `google_email_search.outcome` to `skipped_business_closed`;
  - set eligibility to `Delete`, with the evidence;
  - you can skip the contact and email research and go to Step 7.
- **trading**: clear signs of activity in the last 12 months.
- **unclear**: no recent evidence either way. This can't be `Suitable`.

## Step 3 - Website scan
If the row has a website (or you found one with a quick search), run `P scan <Run> <Row>`. Add `--url <url>` if you found the site yourself, and set `website_url` to it.
- Read the saved page files for the about, team and contact pages.
- `people_seen_on_website`: every staff member, owner or team member named on the site.
- Emails the scan lists that belong to THIS business go in `emails` with `found_on` `website` and `source_url` set to the page they were on. Ignore addresses belonging to web designers, plugins or other companies.
- Remember the Facebook link if the site has one.
- If the site won't load, try WebFetch once. If that also fails, set the website step outcome to `not_found` with the URL in `urls`, and write "Website unreachable" in `audit_notes`.
- If there's no website at all, set `website_url` to null and the website step to `skipped_no_website`.

## Step 4 - Contact name and job title (strict order: website, then Google, then LinkedIn)
A **priority contact** is either:
- a marketing person (marketing manager, director, head or coordinator), or
- an owner (owner, co-owner, founder, proprietor or managing director; at a small firm, also CEO, president, principal or partner).

If you find both, choose the marketing person.

1. **website**: the pages from Step 3.
2. **google**: WebSearch, e.g. `"<Business Name>" owner`, `"<Business Name>" <town> founder`, `"<Business Name>" marketing manager`. Good sources are Companies House or state-registry officer lists, local news, award pages, interviews, a Facebook "About" section and directories.
3. **linkedin**: WebSearch `site:linkedin.com/in "<Business Name>"`, and the same search adding `owner OR founder OR marketing`. Use the name and title shown in the search result. Don't open or log in to LinkedIn; the search result is your source.

Set each step's outcome:
- `found_priority`: you found a marketing or owner person here. Every LATER step becomes `not_needed`, and you stop.
- `found_other`: you found someone, but not marketing or owner. Carry on to the next step.
- `not_found`: you looked and found nobody. Carry on.
- `skipped_no_website`: website step only, when there is no website.

Fill in `queries` (the exact searches, for Google and LinkedIn) and `urls` (the pages where you found people, or the pages you checked).

**Choose the contact**: the `found_priority` person; otherwise the most senior `found_other` person; otherwise nobody (leave all contact fields null).
- `name` is the name only.
- `job_title` is as stated on the source.
- `role_type` is `marketing`, `owner`, `senior` (other senior staff) or `other`.
- `source` is `website`, `google` or `linkedin`: the step where you found them.
- `source_url` is the page that shows them with their role.

Check they work at THIS business now (same business name and town). Don't use someone a source says has left.

## Step 5 - Emails
**a) Website**: the emails from Step 3.

**b) Facebook. Do this every time, even if the website already gave you an email.**
1. Find the page: use the website's Facebook link, or WebSearch `site:facebook.com "<Business Name>" <town>`. Check it's the same business (name, town, phone).
2. Try to see its email without logging in: WebSearch `"<Business Name>" facebook email` and `site:facebook.com "<Business Name>" "@"`, and WebFetch the page.
3. Set `facebook.page_url`, `facebook.queries` (your searches), `facebook.checked_via` (`fetch`, `search_snippet` or `none`) and `facebook.status`:
   - `checked_email_found`: you saw an email on the page or in its search snippet. Add it to `emails` with `found_on` `facebook` and `source_url` set to the page URL.
   - `checked_no_email`: you could actually read the page's contact details (`checked_via` `fetch`) and there was no email.
   - `needs_browser`: the page exists, but you couldn't see its contact details (login wall, or only search snippets). This is normal; a browser pass checks it later.
   - `no_page_found`: you searched and this business has no page.

**c) Google.** This is required if the website and Facebook gave no email so far. WebSearch `"<Business Name>" email`, `"@<website domain>"` and `"<Business Name>" <town> contact`. Set `google_email_search.outcome` to `found` or `not_found`, and list the `queries`. If you already have an email from the website or Facebook, set it to `not_needed`.

Each email is `{"address": "...", "kind": "...", "found_on": "website|facebook|google", "source_url": "https://..."}`.
- `kind` `generic` means a shared or role mailbox: info@, sales@, office@, bookings@, or the business name @gmail.com.
- `kind` `named` means one person: john@, j.smith@, sarah.jones@.

Only record addresses that belong to this business.

## Step 6 - Advertising eligibility
Follow the eligibility rules file from Step 1. Research it independently: don't rely on the scraper data alone. Confirm with at least one independent source, such as recent website activity, recent reviews or posts, registry status or news.
- `eligibility.status`: exactly `Suitable`, `Review` or `Delete`.
- `justification`: 1-3 sentences giving the specific evidence, with dates where possible. No URLs.
- `evidence_urls`: the pages that support it (at least one).

## Step 7 - Notes
- `notes` (research notes): 1-3 sentences of facts useful for a sales pitch: what they do, size, service area, recent activity, awards. Not the contact-search story (the builder writes that) and not the eligibility reasons (those go in `justification`).
- `audit_notes`: only problems with the research itself, e.g. "Website unreachable", "Email only seen in a Google snippet", "Two similar businesses in the same town". Leave it `""` if there are none.
- `action_notes`: a specific next step for the user, only if the sheet won't already say it. Otherwise `""`.
- `closest_location`: only when the row says closest location is UNKNOWN. Give the town the business is based in or nearest to.

Reminder: no people from the company website, no URLs and no email addresses in these fields.

## Step 8 - Save and check
Save the JSON with the Write tool to the path from Step 1, then run:
`P validate <Run> --row <Row>`
If it prints `FAIL`, fix every problem listed (doing more research if a problem needs it), save, and run it again. Repeat until it prints `PASS`, up to 5 rounds.

## Step 9 - Reply
Reply with one line only, for example:
`R0007 PASS | Suitable | contact: yes (Owner, via website) | emails: 2 | facebook: needs_browser`
or
`R0007 FAIL | <the problems still listed>`
