"""Customer address-book formatting."""

def display_name(contact: dict[str, str]) -> str:
    return contact["name"].strip() or contact["email"]
