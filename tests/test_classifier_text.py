from canditrack.classifiers.text import normalize


def test_normalize_decodes_double_entities_and_removes_invisible_chars():
    text = "  Python &amp;amp; SQL\u034f\u00ad\r\n\t \u200c Remoto &lt;100%&gt; "

    assert normalize(text) == "Python & SQL Remoto <100%>"


def test_normalize_empty():
    assert normalize("") == ""
