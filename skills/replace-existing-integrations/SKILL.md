---
name: Replace existing integrations
description: >-
  Use when an ISV already has ConnectWise, Autotask, Halo, or other vendor
  clients and is replacing those with Bitlync. Not for first-day Quickstart,
  company-map import, or moving an MSP from one PSA to another.
---
# Replace existing integrations

Public title: **Replace existing integrations**. Not Import. Not Move your PSA. Not Direct in the title. Internal notes may say migration.

The job: they already wrote vendor clients. They change those calls to Bitlync. Bitlync does not ingest their old code or import their tokens.

## Rules

- Check coverage against what Bitlync actually ships. Do not invent objects or routes.
- Reads first. Then writes. Webhooks only if they already exist in product.
- Keep the old vendor clients until Bitlync matches in their environment.
- Use `dry_run` as the shadow pass on writes. Compare shape, do not cut over on a preview.
- Never mint an agreement header. Never write devices (not implemented). Never auto-create an unmatched company.
- Write a line on an existing agreement only. Public word is Agreement, not Contract. Site word for the line is Line item.
- MSP pastes their own keys. Name a missing permission in the connect flow. Do not claim OAuth unless that vendor actually publishes a partner app.
- No Rewst (or other vendor) screenshots in anything that ships.
- Do not add `pass_through`, Proxy, or vault token-import. Those are a different product.
- Do not turn on live PSA POST until HTTP retry is GET-only or vendor-idempotent.

## Phase 1 — Inventory

1. List the vendor APIs they call today (PSA first: ConnectWise, Autotask, Halo).
2. For each, list the operations they use (list/get/create/update/close) and the fields they depend on.
3. Map each to a Bitlync word: Ticket, Company, Contact, Device, Agreement, Line item, Project.
4. Mark gaps honestly. A gap is not a bug. Later or Never stays named.

## Phase 2 — Coverage

1. Confirm the connector is on the Connectors tile and the object is actually listed (pull or push).
2. Run connect. The probe must name a missing permission before they take a support ticket.
3. Customer map is ISV customer to PSA company: sure match auto-maps, leftover asks the MSP to create that company in the ISV, UNMAPPED is a human match. Never auto-create.

## Phase 3 — Reads

Replace list/get first. Same Bitlync call for every vendor. Reads come from the store, not a live hit on every request.

Typical left-to-right:

- ConnectWise `service/tickets` / Autotask `Tickets` / Halo `Tickets` → Ticket
- Company / Account / Client → Company
- Configuration / Asset (documented device) → Device
- Agreement / Contract → Agreement
- Addition / Contract charge → Line item

Keep `.raw` for vendor-only fields they still need. Do not log it. Do not put Hudu passwords on a public docs-read path.

## Phase 4 — Writes

Replace create/update only after reads match.

- Tickets: two-way when the MSP grants it (`psa.ticket.create`, `psa.ticket.update`, `psa.ticket.events`). You can create, update, and close. You can subscribe to events when the MSP changes the ticket in their PSA. Events are not a live PSA watch. Close on a ticket we created stays off unless the MSP turns it on.
- Line items: on an existing agreement only.
- Time on a ticket: hours the caller states, on a linked ticket.
- Company create is a separate grant (`psa.company.create`). Off unless the MSP turns it on. We always match first. If two records match, we refuse. `dry_run`. A company create at a distributor, when that write exists and the MSP granted it, is not a PSA create.

Every write: `dry_run` first, then apply. Same payload in sandbox. If they hit a Never, the 422 is a stable code, one English sentence, and a docs URL.

## Phase 5 — Webhooks

Subscribe with `psa.ticket.events` when the MSP grants it. Events are not a live PSA watch. Do not fake a unified event. If the grant is off, they keep their vendor webhooks.

## Done when

- Their app talks to Bitlync for the inventoried objects
- Old vendor clients are still in the repo until they verify
- Never list was not bypassed
- Connect named any missing permission
- No Rewst pixels, no invented OAuth, no live POST retry duplicates
