import re

from presidio_analyzer import AnalyzerEngine, PatternRecognizer, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.pattern import Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

_NLP_CONFIG = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}


class UnscrubbedPayloadError(Exception):
    """Raised when PHI would leave the machine without scrubbing."""


class PiiGuard:
    """Zero-trust egress guard: analyze + anonymize clinical text."""

    def __init__(self) -> None:
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()
        registry.add_recognizer(
            PatternRecognizer(
                supported_entity="MRN",
                patterns=[
                    Pattern("mrn", r"\b\d{7,10}\b", 0.6),
                ],
            )
        )
        nlp = NlpEngineProvider(nlp_configuration=_NLP_CONFIG).create_engine()
        self.analyzer = AnalyzerEngine(
            nlp_engine=nlp, registry=registry, supported_languages=["en"]
        )
        self.anonymizer = AnonymizerEngine()

    def _find(self, text: str):
        return self.analyzer.analyze(
            text=text, language="en", score_threshold=0.5
        )

    def assert_clean(self, text: str) -> None:
        findings = self._find(text)
        if findings:
            kinds = sorted({f.entity_type for f in findings})
            raise UnscrubbedPayloadError(
                f"PHI detected, blocked egress: {', '.join(kinds)}"
            )

    def anonymize(self, text: str) -> str:
        # Replacements can create new findings (e.g. bare "MRN" reads as ORGANIZATION).
        for _ in range(3):
            findings = self._find(text)
            if not findings:
                return text
            text = self.anonymizer.anonymize(
                text=text,
                analyzer_results=findings,
                operators={
                    "DEFAULT": OperatorConfig("replace", {"new_value": "<PHI>"}),
                    "MRN": OperatorConfig("replace", {"new_value": "<MRN>"}),
                },
            ).text
        return text


_default_guard: PiiGuard | None = None


def get_pii_guard() -> PiiGuard:
    global _default_guard
    if _default_guard is None:
        _default_guard = PiiGuard()
    return _default_guard


_PHONE = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")
