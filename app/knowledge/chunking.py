import re


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    paragraphs = [part.strip() for part in re.split(r"\n+", text)]
    return "\n\n".join(part for part in paragraphs if part)


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")

    cleaned = clean_text(text)
    if len(cleaned) <= chunk_size:
        return [cleaned]

    paragraphs = cleaned.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
            overlap = current[-chunk_overlap:] if chunk_overlap else ""
            candidate = f"{overlap}\n\n{paragraph}".strip()
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                start = 0
                while start < len(candidate):
                    end = min(start + chunk_size, len(candidate))
                    chunks.append(candidate[start:end])
                    if end == len(candidate):
                        break
                    start = end - chunk_overlap
                current = ""
        else:
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                chunks.append(paragraph[start:end])
                if end == len(paragraph):
                    break
                start = end - chunk_overlap
            current = ""

    if current:
        chunks.append(current)

    return [chunk.strip() for chunk in chunks if chunk.strip()]
