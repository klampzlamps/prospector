# LinkedIn contact lookup (logged-in browser)

For businesses where the website and Google didn't turn up a marketing or owner contact, you look the business up on LinkedIn in a browser where the user is already logged in. This is **read-only**, and slow on purpose.

Your prompt gives you `P` (the tool command), `Run`, `Browser` (`built-in` or `chrome`) and lines like:
`R0007 | Business name | Town | website`

## Browser tools
- **built-in**: `mcp__Claude_Browser__navigate`, `mcp__Claude_Browser__get_page_text`, `mcp__Claude_Browser__find`.
- **chrome**: load them first with ToolSearch, query `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find`. Then call `tabs_context_mcp`, create one tab with `tabs_create_mcp`, and use that tab throughout.

## Hard rules
- Never log in, type a password or code, or solve a CAPTCHA or security check.
- Never connect, follow, message, endorse, or click anything that changes something. Only read.
- Open at most 2 pages per business: the search results page plus one profile or company page.
- Wait about 5 seconds between pages (use the browser's wait or computer `wait` action). Going slowly protects the user's account.

## For each line, one at a time
1. Open `https://www.linkedin.com/search/results/people/?keywords=<business name URL-encoded>` and get the page text.
2. **Stop conditions:**
   - **Login page** ("Sign in", "Join LinkedIn"): run `P li-result <Run> <ID> --status login_required`, stop and reply `LOGIN_REQUIRED`.
   - **Security check, CAPTCHA, "unusual activity" or a "limit" message**: run `P li-result <Run> <ID> --status checkpoint`, stop and reply `CHECKPOINT`.
3. Look for someone whose headline shows they **currently** work at THIS business (same business name; the town matches if shown), in a marketing role or as owner, founder, managing director or similar. If the results are unclear, open the most likely person's profile (that's your second page) to confirm the current role.
4. **Record what you found:**
   - Marketing or owner person: `P li-result <Run> <ID> --status found --name "<Full Name>" --title "<their title>" --role-type marketing|owner --url <their profile URL>`
   - Only other staff: `P li-result <Run> <ID> --status found --name "<Full Name>" --title "<title>" --role-type senior|other --url <profile URL>`
   - Nobody at this business: `P li-result <Run> <ID> --status not_found`

   Only record what you actually saw. Profile URLs look like `https://www.linkedin.com/in/...`.

## Reply
One line per row, e.g. `R0007 found Jane Doe (Marketing Manager)`. End with `DONE`, `LOGIN_REQUIRED` or `CHECKPOINT`.
