"""media-service — voice transcription + document parsing (PRD §6.5).

In Phase 6 this is consumed by chat-service as a Python workspace
library (no separate HTTP service yet). Chat-service still owns the
``chat.attachments`` table and the upload endpoints; media-service
just supplies the parsers, transcriber, and S3 storage adapter.

Layering follows the same hexagonal split (PRD §5.2):

- ``domain``         pure types: Audio, Document, ExtractedContent.
- ``application``    use cases: ParseDocument, TranscribeAudio +
                     ports (DocumentParser, Transcriber).
- ``infrastructure`` adapters: regex MIME parsers, faster-whisper
                     transcriber, S3 (MinIO) storage, arq tasks.
- ``interfaces``     reserved for the future standalone HTTP service.
"""
