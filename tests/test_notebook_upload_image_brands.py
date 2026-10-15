"""ISO media files that are still pictures (AVIF, HEIC) share the "ftyp" box
with MP4 video. They must be refused, not stored and served as video/mp4."""

import pytest

from api import notebook


def _ftyp(brand: bytes) -> bytes:
    return b"\x00\x00\x00\x18ftyp" + brand + b"\x00\x00\x00\x00" + brand + b"mif1" + b"\x00" * 64


@pytest.mark.parametrize("brand,name", [(b"avif", "photo.avif"), (b"heic", "IMG_0001.HEIC"), (b"mif1", "photo.heif")])
def test_still_image_brands_are_refused(brand, name):
    with pytest.raises(notebook.NotebookError) as error:
        notebook.classify_upload(_ftyp(brand), name)
    assert error.value.args and "can be added" in str(error.value)


@pytest.mark.parametrize("brand,name,mime", [(b"isom", "clip.mp4", "video/mp4"), (b"qt  ", "clip.mov", "video/quicktime"), (b"M4A ", "song.m4a", "audio/mp4")])
def test_audio_and_video_brands_still_pass(brand, name, mime):
    assert notebook.classify_upload(_ftyp(brand), name) == mime
