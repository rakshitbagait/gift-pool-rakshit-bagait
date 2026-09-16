# REASONING.md — GiftPool Design Decisions

## Problem Interpretation

GiftPool is a collaborative shared-expense tool for collecting money toward a fixed gift target. Contributors may pay different amounts (partial, full, extra, or nothing). The system must:

1. Track who paid what (and who recorded it)
2. Compute each member’s balance relative to an equal fair share
3. Suggest a minimal set of transfers so everyone ends up even

No real money movement or payment gateways are required.

## Architecture Decisions

- **FastAPI + Jinja2**: Server-rendered HTML keeps the stack simple for a 2.5-hour MVP. No React/Vue.
- **SQLite + SQLAlchemy**: Zero-config local DB; easy to inspect and reset.
- **Session cookies** (signed with itsdangerous): Avoids JWT complexity while remaining secure for a browser app. HttpOnly + SameSite=Lax.
- **passlib/bcrypt**: Industry-standard password hashing.
- **Decimal for money**: Avoids floating-point errors; amounts quantized to 2 decimal places.

## Authentication Approach

- Registration hashes the password immediately; plain text is never stored.
- Login verifies the hash and issues a timed, signed cookie containing only `user_id`.
- Dependencies (`get_current_user`, `get_pool_membership`, role checkers) enforce authentication and authorization on every protected route.
- Duplicate email is rejected at registration.

## Role and Permission Decisions

Three roles on the `PoolMember` association:

- **Organiser**: Full control (edit conceptually via delete, invite, add/remove members, payments, delete pool). Creator is always organiser.
- **Collaborator**: Can view everything and record payments (including on behalf of others). Useful when the organiser is busy.
- **Member**: Read-only view of the pool, balances, and settlements.

Every pool-scoped route first verifies membership (prevents IDOR). Role checks are applied only after membership is confirmed.

## Database Design

- `User` is independent of pools.
- `Pool` has a foreign key to the organiser user for quick lookup.
- `PoolMember` is the many-to-many association with a `role` enum.
- `Payment` distinguishes `paid_by_member_id` (whose contribution) from `recorded_by_user_id` (who entered it).
- `Invitation` is email-based so users can be invited before or after they register; acceptance creates a `PoolMember` row.

Cascades on pool delete remove members, payments, and invitations.

## Settlement Algorithm

1. Fair share = `target_amount / num_members` (rounded to 2 decimals).
2. Balance = `total_paid - fair_share`.
   - Positive → creditor (should receive)
   - Negative → debtor (owes)
3. Greedy matching: sort debtors and creditors by absolute amount descending; repeatedly transfer `min(debt, credit)` until one side is exhausted.

This produces a small number of transfers and is easy to explain. Amounts are rounded to 2 decimals at each step.

## MVP Trade-offs

- Flash messages via query parameters (no server-side session store beyond the auth cookie).
- No email sending — invitations appear only inside the app.
- No payment editing/deletion UI.
- Organiser cannot change their own role or transfer ownership.
- Tests use an in-memory SQLite engine with dependency overrides.
- Development `SECRET_KEY` fallback is documented and must be replaced in production.

These keep the codebase small and demonstrable while covering all required flows: auth, pools, invitations, payments, balances, and settlements.
