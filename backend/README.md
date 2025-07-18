# backend

- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)

## Installation

```bash
uv sync
```

## Usage

```bash
source .venv/bin/activate

uv run uvicorn main:app --reload

# OR traditional
uvicorn main:app --reload
```

## Project Structure

```plaintext
.
└── backend
    ├── README.md
    └── backend/
        ├── README.md
        ├── pyproject.toml
        ├── uv.lock
        ├── .env.example
        └── app/
            └── main.py
```

## Environment Variables

From `env.example` create an `.env` file

## Generate a Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"

# Or use the OpenSSL command:
openssl rand -hex 32

# Both generate a 32-byte hex string. Copy the output and use it as your SECRET_KEY in the auth file.
```

### Note: `bcrypt 4.3.0+` has breaking changes with passlib

[Back to Top](#backend)
