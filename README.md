# GiftPool — Collaborative Shared-Expense Application

GiftPool lets a group of people collect money for a shared gift. Members contribute toward a target amount; the app tracks payments, computes balances, and suggests a settlement plan (who should pay whom).

## Features

- **User authentication**: Register, login, logout with session-based auth and bcrypt password hashing
- **Pool creation**: Create a gift pool with target amount; creator becomes organiser
- **Roles**: Organiser, Collaborator, Member with different permissions
- **Invitations**: Organiser invites registered users by email (in-app only, no email delivery)
- **Payments**: Record partial, full, or over-payments; multiple payments per person; track who recorded each payment
- **Dashboard**: Target, collected, remaining, progress, fair share, per-member balances
- **Settlements**: Greedy algorithm suggests transfers to settle balances
- **Access control**: Membership and role checks on every protected route (prevents IDOR)

## Authentication Flow

1. User registers with name, email, password → password is hashed with bcrypt
2. User logs in → server validates credentials and sets an HttpOnly session cookie (signed with `SECRET_KEY`)
3. Protected routes require a valid session; invalid/expired sessions return 401
4. Logout clears the session cookie

## Collaboration and Roles

| Role          | View pool | Add payments | Manage members / invites | Delete pool |
|---------------|-----------|--------------|---------------------------|-------------|
| Organiser     | ✓         | ✓            | ✓                         | ✓           |
| Collaborator  | ✓         | ✓            | —                         | —           |
| Member        | ✓         | —            | —                         | —           |

Collaborators may record payments on behalf of any member; the authenticated user is stored as `recorded_by_user_id`.

## Database Structure

- **users**: id, name, email, password_hash, created_at
- **pools**: id, name, target_amount, organiser_id, created_at
- **pool_members**: id, pool_id, user_id, role, joined_at
- **invitations**: id, pool_id, invited_email, invited_by_user_id, status, created_at
- **payments**: id, pool_id, paid_by_member_id, recorded_by_user_id, amount, payment_method, note, created_at

SQLite is used for simplicity. Monetary values use `Numeric(12, 2)` / Python `Decimal`.

## Tech Stack

- Backend: FastAPI
- Frontend: HTML5, CSS3, vanilla JS (Jinja2 templates)
- Database: SQLite
- ORM: SQLAlchemy
- Validation: Pydantic
- Auth: Session cookies + passlib/bcrypt

## Installation

```bash
cd gift-pool
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Environment Variables

| Variable       | Description                          | Default (dev only)                                      |
|----------------|--------------------------------------|---------------------------------------------------------|
| `SECRET_KEY`   | Signs session cookies                | `dev-secret-key-change-in-production-giftpool-2024`     |
| `DATABASE_URL` | SQLAlchemy DB URL                    | `sqlite:////tmp/giftpool.db`                               |

**Important**: Set a strong `SECRET_KEY` in production. The fallback is for local development only.

## How to Run

```bash
# From the gift-pool directory (with venv activated)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000 in a browser.

Typical flow:

1. Register two users (e.g. organiser and member)
2. Log in as organiser → Create Pool
3. Invite the second user by email
4. Log in as the second user → Accept invitation
5. Record payments (as organiser/collaborator)
6. View balances and suggested settlements on the pool page

## Tests

```bash
cd gift-pool
pytest tests/ -v
```

Covers:

- Registration / login / duplicate email
- Pool creation and membership restrictions
- Invitation accept flow
- Payment creation, multiple payments, invalid amounts
- Settlement algorithm (fair share, greedy matching)

## Known Limitations (MVP)

- No real email delivery for invitations (in-app only)
- No password reset
- No edit/delete of individual payments
- No payment gateway or real money movement
- Session secret fallback is insecure for production
- Single SQLite file (not suited for high concurrency)
- Flash messages passed via query string (simple, not ideal for sensitive data)

## Project Structure

```
gift-pool/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud.py
│   ├── auth.py
│   ├── dependencies.py
│   ├── services/
│   │   ├── settlement.py
│   │   └── invitations.py
│   ├── templates/
│   └── static/css/
├── tests/
├── requirements.txt
├── README.md
├── REASONING.md
├── AI_LOGS.md
└── .gitignore
```
