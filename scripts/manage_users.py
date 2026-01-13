#!/usr/bin/env python3
"""User management CLI for rotary phone web admin.

Usage:
    python scripts/manage_users.py add <username>
    python scripts/manage_users.py delete <username>
    python scripts/manage_users.py list
"""

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path so we can import rotary_phone
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import bcrypt
except ImportError:
    print("Error: bcrypt is not installed. Install it with:")
    print("  uv pip install bcrypt")
    sys.exit(1)

from rotary_phone.database.database import Database
from rotary_phone.database.models import User


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hashed password
    """
    # Cost factor of 12 (2^12 = 4096 rounds)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def add_user(db: Database, username: str) -> None:
    """Add a new user.

    Args:
        db: Database instance
        username: Username to add
    """
    # Check if user already exists
    existing = db.get_user_by_username(username)
    if existing:
        print(f"Error: User '{username}' already exists")
        sys.exit(1)

    # Prompt for password
    print(f"Creating user: {username}")
    password = getpass.getpass("Enter password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        print("Error: Passwords do not match")
        sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters")
        sys.exit(1)

    # Hash password
    password_hash = hash_password(password)

    # Create user
    user = User(
        username=username, password_hash=password_hash, created_at=datetime.utcnow()
    )

    try:
        user_id = db.add_user(user)
        print(f"✓ User '{username}' created successfully (ID: {user_id})")
    except Exception as e:
        print(f"Error creating user: {e}")
        sys.exit(1)


def delete_user(db: Database, username: str) -> None:
    """Delete a user.

    Args:
        db: Database instance
        username: Username to delete
    """
    # Check if user exists
    existing = db.get_user_by_username(username)
    if not existing:
        print(f"Error: User '{username}' not found")
        sys.exit(1)

    # Confirm deletion
    confirm = input(f"Delete user '{username}'? (yes/no): ")
    if confirm.lower() not in ("yes", "y"):
        print("Cancelled")
        sys.exit(0)

    # Delete user
    deleted = db.delete_user(username)
    if deleted:
        print(f"✓ User '{username}' deleted successfully")
    else:
        print(f"Error: Failed to delete user '{username}'")
        sys.exit(1)


def list_users(db: Database) -> None:
    """List all users.

    Args:
        db: Database instance
    """
    users = db.list_users()

    if not users:
        print("No users found")
        return

    print(f"\nFound {len(users)} user(s):\n")
    print(f"{'ID':<6} {'Username':<20} {'Created At'}")
    print("-" * 60)

    for user in users:
        created_str = user.created_at.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{user.id:<6} {user.username:<20} {created_str}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage users for rotary phone web admin"
    )
    parser.add_argument(
        "command", choices=["add", "delete", "list"], help="Command to execute"
    )
    parser.add_argument("username", nargs="?", help="Username (required for add/delete)")
    parser.add_argument(
        "--db",
        default="data/rotary_phone.db",
        help="Path to database file (default: data/rotary_phone.db)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.command in ("add", "delete") and not args.username:
        print(f"Error: username required for '{args.command}' command")
        sys.exit(1)

    # Initialize database
    db = Database(args.db)
    db.init_db()

    # Execute command
    if args.command == "add":
        add_user(db, args.username)
    elif args.command == "delete":
        delete_user(db, args.username)
    elif args.command == "list":
        list_users(db)


if __name__ == "__main__":
    main()
