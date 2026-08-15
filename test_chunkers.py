"""python test_chunkers.py"""

from echorag.index import sentence_window, split_sentences, whole_passage
from echorag.schemas import Passage

P = Passage(
    passage_id="42:3",
    query_id=42,
    text_en="Cats sleep a lot. They hunt at night. Kittens need milk.",
    text_translated="बिल्लियाँ बहुत सोती हैं। वे रात में शिकार करती हैं।",
    query_type="description",
    lang="hin_Deva",
    is_gold=True,
    query="बिल्लियाँ कितना सोती हैं?",
    query_en="how much do cats sleep?",
)


def check_split_sentences():
    assert split_sentences(P.text_en) == [
        "Cats sleep a lot.",
        "They hunt at night.",
        "Kittens need milk.",
    ]


def check_whole_passage():
    chunks = whole_passage(P)
    views = [c.view for c in chunks]
    assert views == ["v1", "v2"], f"expected ['v1','v2'], got {views}"
    assert chunks[0].text == P.text_en
    assert chunks[1].text == P.text_translated
    assert all(c.parent_id == "42:3" for c in chunks)
    assert chunks[0].chunk_id == "42:3:v1", f"got {chunks[0].chunk_id}"

    only_en = P.model_copy(update={"text_translated": ""})
    assert [c.view for c in whole_passage(only_en)] == ["v1"], "skip v2 when there is no translation"


def check_sentence_window():
    chunks = sentence_window(P, window=1)
    assert len(chunks) == 3, f"one chunk per sentence, got {len(chunks)}"

    texts = [c.text for c in chunks]
    assert texts[0] == "Cats sleep a lot. They hunt at night.", f"got {texts[0]!r}"
    assert texts[1] == "Cats sleep a lot. They hunt at night. Kittens need milk."
    assert texts[2] == "They hunt at night. Kittens need milk.", (
        f"last chunk has nothing after it — a whole-passage result here means a "
        f"negative index wrapped around. Got {texts[2]!r}"
    )

    assert all(c.view == "v3" for c in chunks)
    assert all(c.parent_id == "42:3" for c in chunks)
    assert len({c.chunk_id for c in chunks}) == 3, "chunk_ids must be unique"

    assert [c.text for c in sentence_window(P, window=0)] == split_sentences(P.text_en)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("check_"):
            fn()
            print(f"✅ {name}")
    print("\nall chunker checks passed")
