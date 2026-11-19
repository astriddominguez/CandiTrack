"""Utilidades de texto compartidas por los clasificadores."""

from html import unescape

# Caracteres invisibles de relleno que algunas plataformas meten en los correos.
_REMOVE_INVISIBLE = dict.fromkeys(map(ord, "­͏​‌‍⁠﻿"))


def normalize(text: str) -> str:
    """Decodifica entidades HTML (a veces dobles: ``&amp;amp;``), quita caracteres
    invisibles y une todos los espacios y saltos de línea en espacios simples."""
    previous = None
    while previous != text:
        previous, text = text, unescape(text)
    return " ".join(text.translate(_REMOVE_INVISIBLE).split())
