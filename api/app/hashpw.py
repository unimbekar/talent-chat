"""Print an argon2id hash for ADMIN_PASSWORD_HASH."""

import sys

from argon2 import PasswordHasher


def main() -> None:
    if sys.stdin.isatty():
        import getpass

        password = getpass.getpass("Admin password: ")
        again = getpass.getpass("Repeat: ")
        if password != again:
            raise SystemExit("passwords did not match")
    else:
        password = sys.stdin.readline().strip()
    if not password:
        raise SystemExit("empty password")
    print(PasswordHasher().hash(password))


if __name__ == "__main__":
    main()
