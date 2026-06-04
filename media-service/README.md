# media-service

Voice transcription and document parsing for the AI-OLive platform.

In Phase 6 this is consumed by chat-service as a Python workspace
library (no separate HTTP service). The standalone FastAPI surface
is left scaffolded under `media_service/interfaces/http/` for a
later phase.

## Layout

```
media_service/
  domain/
    entities/audio.py
    entities/document.py
    value_objects/extracted_content.py
    services/document_parser.py    # Port
    services/transcriber.py        # Port
  application/
    use_cases/parse_document.py    # Phase 6.3
    use_cases/transcribe_audio.py  # Phase 6.5
  infrastructure/
    parsing/
      pdf_parser.py                # Phase 6.4 — pypdf
      docx_parser.py               # Phase 6.4 — python-docx
    transcription/
      whisper_transcriber.py       # Phase 6.6 — faster-whisper
    storage/
      s3_storage.py                # Phase 6.7 — aioboto3 (MinIO)
```

## Test

```bash
uv run pytest media-service/tests/
```
