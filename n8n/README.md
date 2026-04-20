# n8n workflow

## Import
1. In n8n UI → **Workflows** → **Import from file** → upload `workflow.json`.
2. Replace `SHEET_ID` in both Google Sheets nodes with the real sheet ID.
3. Set environment variables in n8n:
   - `SCRAPER_BASE` = `https://scraper.yourdomain.com`
   - `TELEGRAM_CHAT_ID` = your chat/group ID
4. Attach credentials:
   - Google Sheets OAuth2
   - Telegram Bot (API token)
5. Activate the workflow.

## Test with 10 rows
Manually trigger (Execute Workflow). Confirm Stage 0 tags propagate to the sheet before leaving it running nightly.

## Error branches
Both IF nodes have a `false` branch left dangling — n8n will stop the item silently there. To persist failures, extend `Write Back` to accept `ERROR: <reason>` by listening on the `false` branch of `Keep Candidates` and writing `Statut scraping = "ERROR: stage1 eliminated"`.
