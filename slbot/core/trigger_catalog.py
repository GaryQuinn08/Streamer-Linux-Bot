"""Nombres legibles y alcance comprobable de los eventos de automatización."""
PLATFORMS = {
    "*": "Todas", "tiktok": "TikTok", "twitch": "Twitch", "youtube": "YouTube",
    "kick": "Kick", "manual": "Manual", "system": "Sistema",
}
EVENTS = {
    "gift": ("Regalo", ("tiktok",)),
    "follow": ("Nuevo seguidor", ("tiktok", "twitch", "kick")),
    "chat": ("Mensaje de chat", ("tiktok", "twitch", "youtube", "kick")),
    "command": ("Comando de chat (!)", ("tiktok", "twitch", "youtube", "kick")),
    "donation": ("Donación", ("youtube",)),
    "bits": ("Bits", ("twitch",)),
    "points": ("Canje de puntos", ("twitch",)),
    "sub": ("Suscripción o membresía", ("twitch", "youtube", "kick", "tiktok")),
    "like": ("Me gusta", ("tiktok",)),
    "share": ("Compartir directo", ("tiktok",)),
}
CHAT_PERMISSIONS = {
    "everyone": "Cualquier persona",
    "staff": "Solo titular o moderador",
    "owner": "Solo titular del chat",
}


def event_label(key):
    return EVENTS[key][0] if key in EVENTS else key


def event_hint(event, platform):
    if event not in EVENTS:
        return "Evento avanzado: solo funciona si algún conector o el sistema emite este código."
    expected = EVENTS[event][1]
    if event == "like" or event == "share":
        return "Disponible como disparador con el puente TikFinity si entrega este evento."
    supported = ", ".join(PLATFORMS[p] for p in expected)
    if platform not in ("*", "manual") and platform not in expected:
        return f"{PLATFORMS.get(platform, platform)} no entrega este evento en la beta. Fuentes previstas: {supported}."
    return f"Fuentes de este evento: {supported}."
