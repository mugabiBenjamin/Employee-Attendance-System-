# backend

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

Create a `.env` file and add the following environment variables:

```env
# JWT Configuration
SECRET_KEY=your-secret-key
ALGORITHM=HS256

# Database Configuration
DATABASE_URL=sqlite:///./dbname.db
# For PostgreSQL: postgresql://username:password@localhost/dbname
# For MySQL: mysql://username:password@localhost/dbname
```

## Generate a Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"

# Or use the OpenSSL command:
openssl rand -hex 32

# Both generate a 32-byte hex string. Copy the output and use it as your SECRET_KEY in the auth file.
```

## Note -> `bcrypt 4.3.0+` has breaking changes with passlib

```bash
# Install uv if not already installed
pip install uv

# Initialize project with uv
uv init

# Install dependencies
uv add -r pyproject.toml

# Install dev dependencies
uv add --dev pytest pytest-asyncio pytest-cov httpx black isort flake8 mypy pre-commit ipython
```
