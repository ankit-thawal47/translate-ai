from app.services.pipeline.audio import SessionAudioBuffer


def test_audio_buffer_prepends_init_chunk_for_window() -> None:
    buffer = SessionAudioBuffer(session_id="abc")
    buffer.add_chunk(b"HEADER")
    buffer.add_chunk(b"BODY1")
    buffer.add_chunk(b"BODY2")

    assert buffer.build_window() == b"HEADERBODY1BODY2"

