from auditor_toolkit import readability


def test_empty_text_is_zero():
    assert readability.flesch_reading_ease("") == 0.0
    assert readability.flesch_kincaid_grade("") == 0.0


def test_simple_text_is_easier_than_complex_text():
    simple = "The cat sat on the mat. It was a good day."
    complex_text = (
        "Interdisciplinary operationalization necessitates comprehensive "
        "consideration of multifactorial organizational characteristics."
    )
    assert readability.flesch_reading_ease(simple) > readability.flesch_reading_ease(complex_text)


def test_metrics_are_deterministic():
    text = "Customers can request a quote online. The form asks for the job details."
    first = (
        readability.flesch_reading_ease(text),
        readability.flesch_kincaid_grade(text),
    )
    second = (
        readability.flesch_reading_ease(text),
        readability.flesch_kincaid_grade(text),
    )
    assert first == second
