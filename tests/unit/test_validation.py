import pytest

from app.core.config import UploadConfig
from app.core.exceptions import DocumentValidationError
from app.services.rag.validation import validate_upload


@pytest.fixture
def config() -> UploadConfig:
    return UploadConfig(max_file_size_mb=1, allowed_extensions=(".pdf", ".txt", ".md", ".docx"))


def test_accepts_valid_txt(config):
    content_type = validate_upload("notes.txt", b"hello world", config)
    assert content_type == "text/plain"


def test_rejects_disallowed_extension(config):
    with pytest.raises(DocumentValidationError):
        validate_upload("script.exe", b"MZ...", config)


def test_rejects_oversized_file(config):
    big_content = b"x" * (2 * 1024 * 1024)  # 2MB > 1MB limit
    with pytest.raises(DocumentValidationError):
        validate_upload("big.txt", big_content, config)


def test_rejects_empty_file(config):
    with pytest.raises(DocumentValidationError):
        validate_upload("empty.txt", b"", config)


def test_rejects_path_traversal_filename(config):
    with pytest.raises(DocumentValidationError):
        validate_upload("../../etc/passwd.txt", b"content", config)


def test_rejects_mislabeled_pdf(config):
    with pytest.raises(DocumentValidationError):
        validate_upload("fake.pdf", b"not really a pdf", config)


def test_accepts_real_pdf_magic_bytes(config):
    content_type = validate_upload("real.pdf", b"%PDF-1.4 rest of file", config)
    assert content_type == "application/pdf"
