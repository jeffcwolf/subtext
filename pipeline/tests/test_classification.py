"""Speaker-role and section classification contracts for load_transcripts.

These pin the heuristics described in the module docstring: roles are learned
from the introduction, the Q&A boundary is the operator's hand-off to the first
analyst (not the opening disclaimer), and analysts are the voices the operator
announces.
"""

import load_transcripts as lt


def test_person_name_strips_firm_suffix():
    assert lt.person_name("Mike McMullen") == "Mike McMullen"
    assert (
        lt.person_name("William Douglas Parker - American Airlines Group, Inc.")
        == "William Douglas Parker"
    )


def test_person_name_preserves_intra_name_hyphen():
    assert lt.person_name("Julien Dumoulin-Smith") == "Julien Dumoulin-Smith"


def test_surname_is_last_token():
    assert lt._surname("Doug Parker") == "Parker"
    assert lt._surname("Peter Oppenheimer - Goldman Sachs") == "Oppenheimer"


def test_role_from_own_label_reads_chief_title_after_separator():
    assert lt.role_from_own_label("Peter Oppenheimer, CFO") == "CFO"
    assert lt.role_from_own_label("Tim Cook - Chief Executive Officer") == "CEO"
    # A bare name carries no title, so no role can be read from the label alone.
    assert lt.role_from_own_label("Mike McMullen") is None


def test_find_qa_start_skips_the_disclaimer_and_finds_the_real_open():
    segments = [
        {
            "speaker": "Operator",
            "text": "Following the presentation, we will conduct a "
            "question-and-answer session.",
        },
        {"speaker": "Tim Cook", "text": "Thanks for joining. Revenue grew."},
        {
            "speaker": "Operator",
            "text": "Our first question comes from the line of John Smith with Big Bank.",
        },
        {"speaker": "John Smith", "text": "Can you talk about margins?"},
    ]
    # Index 0 only *describes* the upcoming Q&A; the real open is the routing turn.
    assert lt.find_qa_start(segments) == 2


def test_is_nonspeaker_flags_roster_headers_and_boilerplate():
    assert lt.is_nonspeaker("Executives")
    assert lt.is_nonspeaker("Q&A")
    assert lt.is_nonspeaker("Corporate Participants")
    assert lt.is_nonspeaker("- - -")  # punctuation-only artifact


def test_is_nonspeaker_keeps_real_speakers_including_unlabelled_ones():
    assert not lt.is_nonspeaker("Tim Cook")
    # An empty label is a real but unlabelled speaker — it must be kept.
    assert not lt.is_nonspeaker("")


def test_extract_announced_analysts_reads_operator_routing_only():
    segments = [
        {
            "speaker": "Operator",
            "text": "Our first question comes from the line of Jane Doe with Big Bank.",
        },
        {
            "speaker": "Operator",
            "text": "Next question is from John Smith of Aequitas.",
        },
        {
            "speaker": "Tim Cook",
            "text": "This is not an operator line, so it is ignored.",
        },
    ]
    full, surnames = lt.extract_announced_analysts(segments)
    assert {"Jane Doe", "John Smith"} <= full
    assert {"Doe", "Smith"} <= surnames


def test_find_qa_start_returns_len_when_no_qa_detected():
    segments = [
        {"speaker": "Operator", "text": "Welcome to the call."},
        {"speaker": "Tim Cook", "text": "Hello."},
    ]
    assert lt.find_qa_start(segments) == len(segments)


def test_classify_transcript_end_to_end():
    segments = [
        {
            "speaker": "Operator",
            "text": "Welcome. With me are Tim Cook, our Chief Executive Officer, "
            "and Luca Maestri, our Chief Financial Officer.",
        },
        {"speaker": "Tim Cook", "text": "We had a strong quarter."},
        {"speaker": "Luca Maestri", "text": "Revenue was up."},
        {
            "speaker": "Operator",
            "text": "Our first question comes from the line of Jane Doe with Big Bank.",
        },
        {"speaker": "Jane Doe", "text": "How are margins trending?"},
        {"speaker": "Tim Cook", "text": "Margins improved."},
    ]
    out = list(lt.classify_transcript(segments))
    sections = [o[0] for o in out]
    speakers = [o[1] for o in out]
    roles = [o[2] for o in out]

    # Executives are identified from the introduction and their prepared remarks
    # (before the Q&A open) are tagged prepared_remarks.
    assert (roles[1], sections[1]) == ("CEO", "prepared_remarks")
    assert (roles[2], sections[2]) == ("CFO", "prepared_remarks")
    # The operator-announced voice is an analyst asking a question.
    assert (speakers[4], roles[4], sections[4]) == (
        "Jane Doe",
        "Analyst",
        "qa_question",
    )
    # The CEO answering after the Q&A open is a qa_response.
    assert (roles[5], sections[5]) == ("CEO", "qa_response")
