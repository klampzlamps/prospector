# Business look-up brief (one business, from its name)

You start with just a business name (and usually a town or area). Find the basic public details a Google Maps listing would show:
- official name
- its own website
- address (or the town it serves)
- phone number
- category
- whether it's still open
- Google rating and review count, if a search result shows them

A checker tests your file. You're finished only when it prints `PASS`.

Your prompt gives you `P` (the tool command), `Run` and `Row`. Run each `P ...` command with the Bash tool (or PowerShell if `P` starts with `powershell`), exactly as written.

## Never
- Never guess or invent a detail. Everything you record must have been seen on a page or search result, and that URL goes in `sources`.
- **Never mix two businesses.** Similar names are common. Every detail must belong to the same business.
- Never log in to anything.
- Never edit `rows.json`, other rows' files, or the scripts.

## Step 1 - Load the row
`P lookup-row <Run> <Row>`
- It shows the name, the area (if known), where to save your file, and a TEMPLATE.
- If it says the row **already PASSES**, reply with the Step 6 line and stop.
- If it says **A PREVIOUS ATTEMPT FAILED**, Read the existing file, fix only the listed problems, save it, and go to Step 5.

## Step 2 - Search
WebSearch, recording every query in `queries`:
1. `"<name>" <area>`
2. `"<name>" <area> phone` or `"<name>" <area> address`
3. If the name is generic (e.g. "Quality Plumbing"), add the category or a likely street/district.

Useful sources:
- the business's own website (contact page and footer);
- details shown in search results (address, phone, rating, "Permanently closed");
- its Facebook page;
- directories (Yell, Yelp, Checkatrade, Trustpilot);
- Companies House or a state business register.

If you find its website, `P scan <Run> <Row> --url <website>` reads its pages and shows emails, social links and contact details. Read the saved contact/about page text for the address and phone.

## Step 3 - Is it the right business?
It's a match only if:
- the name matches (ignore Ltd/LLC, "&" vs "and", "The"), **and**
- it's in or serves the area (when an area is given), **and**
- two independent sources agree on at least one detail: phone, address or website.

Then choose `match`:
- `found`: you're confident it's this business.
- `ambiguous`: several different businesses fit and you can't tell which. List each in `candidates` as `{"name", "town" or "address", "url"}`. Don't pick one.
- `not_found`: after at least 3 different searches, nothing fits.

## Step 4 - Fill in the template
- `official_name`: the name as the business writes it, e.g. "Smith Plumbing & Heating Ltd".
- `website`: its **own** website only, as a full URL. A Facebook page goes in `facebook`. Directory listings (Yell, Checkatrade...) aren't websites: leave `website` as `""` and put them in `sources`.
- `address`: the full street address, if it has a public one. Service-area businesses often don't: leave it `""` and fill `town`.
- `town`: the town or city it's based in, or mainly serves.
- `phone`: exactly as published.
- `category`: short, e.g. "Plumber", "Hair salon".
- `rating` / `reviews`: only if a search result shows the Google rating or review count; otherwise `null`.
- `closed`: `"permanent"` or `"temporary"` only if a source says so; otherwise `""`.
- `google_maps_url`: only if you saw its Google Maps link.
- `sources`: every page you took a detail from.
- `match_evidence`: one sentence on how you know it's the right business, e.g. "Website footer shows the same Leeds address and phone as its Yell listing."
- `notes`: anything odd (renamed, moved, merged), otherwise `""`.

## Step 5 - Save and check
Save the JSON with the Write tool to the path from Step 1, then run:
`P lookup-validate <Run> --row <Row>`
If it prints `FAIL`, fix every problem listed and run it again, until `PASS` (up to 5 rounds).

## Step 6 - Reply
One line only, for example:
`R0003 PASS | found | Smith Plumbing & Heating Ltd | website yes | phone yes | address yes`
or `R0003 PASS | ambiguous | 3 candidates`
or `R0003 FAIL | <the problems still listed>`
