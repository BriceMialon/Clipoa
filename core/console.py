"""Sortie console robuste (Windows).

Sous Windows, la console et les fichiers de log redirigés utilisent souvent
l'encodage local (cp1252) : un simple ``print`` contenant un emoji ou certains
caractères fait alors planter l'appel avec ``UnicodeEncodeError``. On bascule
stdout/stderr en UTF-8 et on remplace ce qui ne passe pas au lieu de planter.
"""
import sys


def ensure_utf8_console() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:  # pythonw / lanceur sans console
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            enc = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
            if enc != "utf8":
                reconfigure(encoding="utf-8", errors="replace")
            elif getattr(stream, "errors", "") == "strict":
                reconfigure(errors="replace")
        except Exception:
            pass
