from app.services.pipeline.cleanup import clean_transcript


def test_clean_transcript_removes_fillers_and_adds_punctuation() -> None:
    assert clean_transcript("uh can we move google meet to 5 pm tomorrow") == (
        "Can we move google meet to 5 pm tomorrow."
    )

