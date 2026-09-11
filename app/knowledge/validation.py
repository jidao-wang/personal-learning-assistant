from dataclasses import dataclass
from pathlib import Path

from app.core.errors import ValidationError


@dataclass
class ValidatedUpload:
    filename: str
    extension: str
    text: str
    size_bytes: int


def validate_upload(
    filename: str | None,
    content: bytes,
    max_size: int,
) -> ValidatedUpload:
    if not filename or not filename.strip():
        raise ValidationError("文件名不能为空")

    safe_name = Path(filename).name
    extension = Path(safe_name).suffix.lower()
    if extension not in {".txt", ".md"}:
        raise ValidationError("只支持 .txt 和 .md 文件")
    if len(content) > max_size:
        raise ValidationError("单个文件不能超过 10 MB")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("文件必须使用 UTF-8 编码") from exc

    text = text.replace("\x00", "").strip()
    if not text:
        raise ValidationError("空文件或清洗后没有有效文本")

    return ValidatedUpload(
        filename=safe_name,
        extension=extension,
        text=text,
        size_bytes=len(content),
    )
