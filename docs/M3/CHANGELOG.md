# API / DB Changes (Old → New)

This document summarizes the changes made when migrating from the old scripts to the new scripts,
covering API endpoint changes and DB column changes.

---

## 1) proposals_update.py → proposals_update_new.py

### API endpoint changes

- Old: `https://www.lidonation.com/api/catalyst-explorer/proposals`
- New: `https://www.catalystexplorer.com/api/v1/proposals`

Key differences
- New API uses `include=campaign,fund,team,meta_data`
- Fund filter: `filter[fund_id]=<fund_uuid>`

### DB changes (tables / columns)

Tables:
- Old: `proposals`
- New: `proposals_new`

Old script INSERT columns:
- `id, user_id, fund_id, challenge_id, title, title_ja, ideascale_link, ideascale_user, ideascale_id, amount_requested, project_status, funding_status, problem, problem_ja, solution, solution_ja, currency_symbol, currency, alignment_score, feasibility_score, auditability_score`

New script columns (COLUMN_ORDER):
- `id, uuid, fund_uuid, campaign_uuid, user_id, fund_id, challenge_id, title, title_ja, user_name, projectcatalyst_link, ideascale_link, ideascale_user, ideascale_id, amount_requested, amount_received, project_status, funding_status, yes_votes_count, no_votes_count, abstain_votes_count, unique_wallets, problem, problem_ja, solution, solution_ja, currency_symbol, currency, alignment_score, feasibility_score, auditability_score, tags, slug`

Major column differences
- Added: `uuid, fund_uuid, campaign_uuid, user_name, projectcatalyst_link, amount_received, yes_votes_count, no_votes_count, abstain_votes_count, unique_wallets, tags, slug`
- Columns that exist only in the old schema (unused in the new flow) are removed, so the table structure differs.

---

## 2) challenges_update.py → campaigns_new.py

### API endpoint changes

- Old: `https://www.lidonation.com/api/catalyst-explorer/challenges`
- New: `https://www.catalystexplorer.com/api/campaigns`

### DB changes (tables / columns)

Tables:
- Old: `challenges`
- New: `campaigns_new`

Old script INSERT columns:
- `id, fund_id, title, title_ja, proposals_count, amount, currency`

New script columns (COLUMN_ORDER):
- `id, title, title_jp, fund_uuid, slug, excerpt, excerpt_jp, amount, launched_at, awarded_at, color, label`

Major column differences
- Added: `title_jp, fund_uuid, slug, excerpt, excerpt_jp, launched_at, awarded_at, color, label`
- Mapping/changes:
  - `fund_id` → `fund_uuid`
  - `proposals_count, currency` are not included in the new table
  - `title_ja` → `title_jp`

---

## 3) funds_update.py → funds_update_new.py

### API endpoint changes

- Old: `https://www.lidonation.com/api/catalyst-explorer/funds/<fundID>`
- New: `https://www.catalystexplorer.com/api/v1/funds`

Key differences
- Old requires a FundID
- New fetches all Funds with paging

### DB changes (tables / columns)

Tables:
- Old: `funds`
- New: `funds_new`

Old script INSERT columns:
- `id, title, proposals_count, amount, currency, launch_date, currency_symbol, slug`

New script columns (COLUMN_ORDER):
- `id, title, slug, label, description, status, currency, currency_symbol, amount, launched_at, awarded_at, assessment_started_at, hero_img_url, banner_img_url, proposals_count, funded_proposals_count, completed_proposals_count`

Major column differences
- Added: `label, description, status, launched_at, awarded_at, assessment_started_at, hero_img_url, banner_img_url, funded_proposals_count, completed_proposals_count`
- Mapping:
  - `launch_date` → `launched_at`

---

## 4) Scraping / proposal detail update flow

Old:
- `scraping.py`
- `proposal_detail_update.py`

New:
- `proposal_scraping.py`

### Scraping source / API

- Old: IdeaScale (`https://cardano.ideascale.com/`) scraped with Selenium
- New: Project Catalyst (`projectcatalyst.io`) scraped with Playwright

### DB changes (tables / columns)

Main tables
- Old: `proposal_detail` (partial updates to `proposals`)
- New: `proposals_new`

New script updated columns (proposal_scraping.py):
- Core fields
  - `idea_raw_html`
  - `idea_semantic_blocks`
  - `catalyst_id`
  - `project_status`
  - `project_country`
  - `currency`
  - `currency_symbol`
  - `milestones_link`
- Batch mode (`--bat`)
  - `project_status`
  - `currency`
  - `currency_symbol`

Major differences
- Old updates the `proposal_detail` table
- New writes directly into `proposals_new` with richer metadata
