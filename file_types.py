"""File classification: which built-in viewer handles a given file.

Kinds: text, code, image, audio, video, pdf, archive, file.
Everything maps to a viewer — text/code open in the text viewer, images in
the image viewer, audio/video in the media player, and everything else in the
hex viewer. No file type is unsupported.
"""

TEXT_EXTS = {
    ".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".tsv", ".log",
    ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".config", ".env", ".gitignore", ".gitattributes", ".dockerignore",
    ".html", ".htm", ".svg", ".srt", ".vtt", ".ics", ".bib", ".tex",
}
CODE_EXTS = {
    ".py", ".pyw", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".c",
    ".cpp", ".cc", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
    ".sh", ".bash", ".zsh", ".bat", ".cmd", ".ps1", ".sql", ".r", ".lua",
    ".swift", ".kt", ".kts", ".m", ".vim", ".el", ".clj", ".hs", ".scala",
    ".css", ".scss", ".less", ".vue", ".svelte", ".toml", ".diff", ".patch",
}
IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff",
    ".tif", ".ppm", ".pgm",
}
AUDIO_EXTS = {
    ".mp3", ".wav", ".flac", ".ogg", ".oga", ".m4a", ".aac", ".wma",
    ".opus", ".mid", ".midi", ".aiff", ".aif",
}
VIDEO_EXTS = {
    ".avi", ".mpg", ".mpeg", ".mp4", ".mov", ".mkv", ".wmv", ".flv",
    ".webm", ".m4v", ".3gp", ".ts", ".vob",
}
PDF_EXTS = {".pdf"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".dmg", ".tgz"}


def classify(name: str, mime: str | None) -> str:
    ext = name[name.rfind(".") :].lower() if "." in name else ""
    if ext in TEXT_EXTS:
        return "text"
    if ext in CODE_EXTS:
        return "code"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in ARCHIVE_EXTS:
        return "archive"
    # Fall back to MIME when the extension is unknown
    if mime:
        if mime.startswith("text/"):
            return "text"
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("audio/"):
            return "audio"
        if mime.startswith("video/"):
            return "video"
        if mime == "application/pdf":
            return "pdf"
        if "zip" in mime or "tar" in mime or "compressed" in mime:
            return "archive"
    return "file"


def viewer_for(kind: str) -> str:
    """Which viewer handles this kind."""
    if kind in ("text", "code"):
        return "text"
    if kind == "image":
        return "image"
    if kind in ("audio", "video"):
        return "media"
    return "hex"
