import pyperclip


def read_clipboard() -> str:
    try:
        text = pyperclip.paste()
    except Exception as exc:
        raise ValueError(
            "Could not read the clipboard. No supported clipboard mechanism was "
            "found on this platform."
        ) from exc

    if not text:
        raise ValueError("Clipboard is empty. Copy some text first.")

    return text
