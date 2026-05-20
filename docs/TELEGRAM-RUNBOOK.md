# Telegram Integration Runbook

Operational reference for deploying, verifying, troubleshooting, and rolling back the Telegram Task Bridge feature.

See [Setup Guide](SETUP.md) for the initial BotFather and webhook configuration steps.

---

## Rollout

1. Apply migrations:
   ```bash
   alembic upgrade head
   ```
   Or inside Docker:
   ```bash
   docker exec cmd_api alembic upgrade head
   ```

2. Restart the `api` and `worker` containers to pick up any new worker registrations:
   ```bash
   docker compose up -d --build api worker
   ```

3. Verify the outbox cron job registered. In the `cmd_worker_skills` container logs, look for a line containing `send_pending_telegram_outbox`:
   ```bash
   docker compose logs worker_skills --tail=50 | Select-String "telegram"
   ```

4. Open **Admin Portal → Settings → Telegram Integration**: enable the integration, paste the Bot Token, generate (or paste) a webhook secret, and save.

5. Register the webhook. Either click **Set Webhook** in the Admin Portal, or call the Telegram API directly:
   ```bash
   curl -X POST "https://api.telegram.org/bot$TOKEN/setWebhook" \
     -d "url=https://your-domain.com/api/telegram/webhook" \
     -H "X-Telegram-Bot-Api-Secret-Token: $WEBHOOK_SECRET"
   ```
   Replace `$TOKEN` and `$WEBHOOK_SECRET` with the values from Admin Portal. Never hard-code the token literal in scripts.

6. Verify the webhook is registered:
   ```bash
   curl "https://api.telegram.org/bot$TOKEN/getWebhookInfo"
   ```
   Expect `"url"` to show your endpoint and `"pending_update_count"` to be 0 or low.

7. **Per Squad:** Admin Portal → Department → Telegram tab → click **Generate Bind Code**. Inside the corresponding Telegram group, send:
   ```
   /bind CMD-XXXX
   ```
   The bot confirms the binding in the group.

8. **Per user:** Profile → Telegram → click **Generate Link Code**. In any chat with the bot, send:
   ```
   /link LINK-XXXX
   ```
   The bot confirms via DM.

---

## Verification

After rollout, run these checks to confirm the integration is working end-to-end.

1. **Bot responds:** Send `/help` in a bound Telegram group. The bot should reply with a command summary.

2. **Task creation:** In a bound group, send:
   ```
   /task @member Test task from Telegram
   ```
   Confirm the task appears in CMD Support under the bound Squad's default project.

3. **Notification flow:** Move the task to a done state in CMD Support. Check the bound Telegram group for an outbound notification from the bot.

4. **Diagnostics endpoint:** Call `GET /api/admin/telegram/diagnostics` (or open the Diagnostics card in Admin Portal → Telegram) and check:
   - `outbox_pending` is 0 or draining
   - `webhook_status` is `active`
   - `bindings_active` matches the number of bound groups

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Webhook returns 401 | Wrong secret token | Re-save the webhook secret in Admin → Telegram; re-run `setWebhook` with the new secret |
| Bot doesn't reply in group | Privacy Mode is OFF or bot not added | Send `/setprivacy` to `@BotFather`, select your bot, set to **ENABLED**; re-add the bot to the group |
| Outbox rows stuck in `pending` | `worker_skills` container not running | `docker compose up -d worker_skills`; check `docker compose logs worker_skills` |
| All sends fail with 403 | Bot token revoked or invalidated | Rotate the token via `@BotFather`; re-save the new token in Admin → Telegram |
| `/bind` rejected | Requesting Telegram user not a Squad admin in CMD Support | Check the user's role in Admin Portal → Employees |
| `/link` rejected | MCP token invalid or expired | Regenerate the token from Admin Portal → Employee profile |
| Binding disabled after bot was kicked | Working as designed: kick clears the active binding | Re-add bot, generate a new bind code, re-send `/bind CMD-XXXX` in the group |
| Supergroup migration (chat_id changed) | Telegram sends `migrate_to_chat_id` event | Binding auto-updates via the `migrate_to_chat_id` handler. If it didn't, re-bind manually |
| Tasks not appearing in CMD Support | Bound Squad has no default TaskProject set | Admin Portal → Department → Telegram tab → set default project |

---

## Rollback

### Option A — Disable only (no data loss)

Set `telegram_enabled = false` in **Admin Portal → Settings → Telegram Integration** and save. The bot stops responding, the outbox worker skips, and the webhook receives but ignores updates. All `telegram_*` table data is preserved. Re-enable at any time by toggling back.

This is the recommended approach for temporary outages or bot token rotation.

---

### Option B — Full removal

> **WARNING: BACK UP FIRST. The steps below are destructive and data may be irrecoverable.**
>
> Run the backup before proceeding:
> ```powershell
> powershell .\scripts\backup.ps1
> ```
> Confirm the backup file exists in `.\backups\` before continuing.

1. **Delete the webhook** (stops Telegram from sending new updates):
   ```bash
   curl -X POST "https://api.telegram.org/bot$TOKEN/deleteWebhook?drop_pending_updates=true"
   ```

2. **Disable the outbox cron** to stop the worker from attempting sends. Remove or comment out the `send_pending_telegram_outbox` entry in `app/worker.py` and redeploy:
   ```bash
   docker compose up -d --build worker worker_skills
   ```

3. **Clear Admin Portal settings:** Delete the Bot Token and Webhook Secret from Admin Portal → Settings → Telegram Integration.

4. **Schema rollback (optional, destructive):**
   > **This drops all `telegram_*` tables. All binding, identity, and message history data is permanently deleted unless you have a backup.**
   ```bash
   alembic downgrade 039
   ```
   Verify by checking that the `telegram_group_bindings` table no longer exists.

To restore from backup after a schema rollback:
```powershell
powershell .\scripts\restore.ps1 -BackupDir .\backups\YYYYMMDD_HHMMSS
```

---

## Data Retention and Cleanup

The `telegram_update_log` table grows with every incoming Telegram update. There is no automatic purge. Run a nightly cleanup to keep the table size manageable.

**Recommended: delete rows older than 30 days.**

> **Back up before any mass delete.**

```sql
DELETE FROM telegram_update_log
WHERE received_at < now() - interval '30 days';
```

Similarly, failed `telegram_outbox` rows older than 7 days can be archived or deleted:

```sql
DELETE FROM telegram_outbox
WHERE status = 'failed'
  AND created_at < now() - interval '7 days';
```

To automate cleanup, add a scheduled SQL task or an arq cron function in `app/worker.py` (use `SkillWorkerSettings` queue, same pattern as `send_pending_telegram_outbox`).

---

## Related

- [Setup Guide](SETUP.md) — BotFather setup, webhook configuration, first bind/link steps
- [Architecture](ARCHITECTURE.md) — Telegram data model, outbox worker, secret handling
