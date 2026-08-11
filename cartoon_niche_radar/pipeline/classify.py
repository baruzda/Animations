from __future__ import annotations

import re
from typing import Any

from cartoon_niche_radar.models.evidence import Evidenced
from cartoon_niche_radar.models.schemas import ClassificationResult, VideoRecord
from cartoon_niche_radar.storage.export import write_jsonl
from cartoon_niche_radar.utils.config import get_settings, get_taxonomy, project_paths
from cartoon_niche_radar.utils.time import utcnow


CLASSIFIER_VERSION = "heuristic-v2"

class HeuristicClassifier:
    """Deterministic keyword classifier with explicit confidence + UNKNOWN.

    Low confidence → UNKNOWN (never invent a label).
    madeForKids is NEVER used as sole evidence for a specific age band.
    """

    def __init__(self, min_confidence: float | None = None) -> None:
        self.taxonomy = get_taxonomy()
        self.min_confidence = min_confidence or get_settings().min_confidence_for_label
        self.theme_aliases = {
            k.lower(): v for k, v in (self.taxonomy.get("theme_aliases") or {}).items()
        }
        self.version = CLASSIFIER_VERSION

    def classify(self, rec: VideoRecord) -> ClassificationResult:
        text = f"{rec.title or ''} {rec.description or ''}".lower()
        age, age_features = self._match_age_with_features(text)
        # Explicit guard: madeForKids FACT must not become estimated_target_age
        mfk = (
            rec.made_for_kids.value
            if hasattr(rec.made_for_kids, "value")
            else str(getattr(rec, "made_for_kids", "unknown"))
        )
        theme = self._match_theme(text)
        style = self._match_from_list(text, self.taxonomy.get("visual_styles", []), "visual_style")
        structure = self._match_story(text)
        hook = self._match_hook(text)
        character = self._match_character(text)
        emotion = self._match_emotion(text)
        fmt = self._match_format(rec.duration_seconds)
        dialogue = self._bool_cue(
            text,
            positive=["dialogue", "says", "voice over", "vo:", "talking"],
            negative=["no dialogue", "silent", "no talking", "mime"],
            field="dialogue",
        )
        music = self._bool_cue(
            text,
            positive=["music", "song", "soundtrack", "original sound", "beat"],
            negative=["no music", "silent comedy"],
            field="music",
        )
        recurring = self._bool_cue(
            text,
            positive=["episode", "part ", "series", "#shorts series", "recurring"],
            negative=[],
            field="recurring_character",
        )
        series_pot = self._series_potential(text, recurring)

        return ClassificationResult(
            video_id=rec.video_id,
            target_age=age,
            theme=theme,
            story_structure=structure,
            hook=hook,
            visual_style=style,
            character_type=character,
            emotional_trigger=emotion,
            format=fmt,
            series_potential=series_pot,
            dialogue=dialogue,
            music=music,
            recurring_character=recurring,
            age_confidence=float(age.confidence or 0.0),
            classifier_version=self.version,
            age_evidence_features=age_features,
            made_for_kids_fact=mfk,
            classifier="heuristic",
            classified_at=utcnow(),
        )

    def _gate(self, value: str, confidence: float, source: str, rationale: str) -> Evidenced[str]:
        if confidence < self.min_confidence:
            return Evidenced.unknown(
                rationale=f"low confidence ({confidence:.2f}) for '{value}': {rationale}",
                source=source,
            )
        return Evidenced.inference(value, confidence, source, rationale)

    def _match_age_with_features(self, text: str):
        best_id = None
        best_hits = 0
        features: list[str] = []
        for cluster in self.taxonomy.get("age_clusters", []):
            matched = [kw for kw in cluster.get("keywords", []) if kw.lower() in text]
            hits = len(matched)
            if hits > best_hits:
                best_hits = hits
                best_id = cluster.get("id")
                features = [f"kw:{kw}" for kw in matched]
        if not best_id or best_hits == 0:
            return Evidenced.unknown("no age keyword hits"), []
        conf = min(0.45 + 0.15 * best_hits, 0.9)
        return self._gate(best_id, conf, "heuristic.age_keywords", f"hits={best_hits}"), features

    def _match_age(self, text: str) -> Evidenced[str]:
        age, _ = self._match_age_with_features(text)
        return age

    def _match_theme(self, text: str) -> Evidenced[str]:
        themes = list(self.taxonomy.get("themes", []))
        scores: dict[str, int] = {}
        for theme in themes:
            token = theme.replace("_", " ")
            score = 0
            if token in text or theme in text:
                score += 2
            for part in theme.split("_"):
                if len(part) > 3 and re.search(rf"\b{re.escape(part)}\b", text):
                    score += 1
            if score:
                scores[theme] = score
        for alias, canon in self.theme_aliases.items():
            if alias in text:
                scores[canon] = scores.get(canon, 0) + 2
        if not scores:
            return Evidenced.unknown("no theme keyword hits")
        theme, score = max(scores.items(), key=lambda x: x[1])
        conf = min(0.4 + 0.12 * score, 0.92)
        return self._gate(theme, conf, "heuristic.theme_keywords", f"score={score}")

    def _match_from_list(self, text: str, options: list[str], field: str) -> Evidenced[str]:
        for opt in options:
            if opt == "unknown":
                continue
            token = opt.replace("_", " ")
            if token in text or opt in text:
                return self._gate(opt, 0.6, f"heuristic.{field}", f"token={token}")
        return Evidenced.unknown(f"no {field} cues")

    def _match_story(self, text: str) -> Evidenced[str]:
        mapping = {
            "twist": "twist_ending",
            "loop": "loop",
            "tutorial": "tutorial_explain",
            "explain": "tutorial_explain",
            "montage": "montage",
            "skit": "dialogue_skit",
            "punchline": "setup_punchline",
            "cliffhanger": "cliffhanger_series",
            "silent": "silent_visual_gag",
        }
        for token, label in mapping.items():
            if token in text:
                return self._gate(label, 0.58, "heuristic.story", f"token={token}")
        return Evidenced.unknown("no story structure cues")

    def _match_hook(self, text: str) -> Evidenced[str]:
        mapping = {
            "what if": "question_hook",
            "pov": "relatable_situation",
            "wait for": "cliffhanger",
            "you won't believe": "text_on_screen_promise",
        }
        for token, label in mapping.items():
            if token in text:
                return self._gate(label, 0.57, "heuristic.hook", f"token={token}")
        return Evidenced.unknown("no hook cues")

    def _match_character(self, text: str) -> Evidenced[str]:
        mapping = {
            "mascot": "animal_mascot",
            "duo": "duo",
            "pov": "faceless_pov",
            "episode": "recurring_protagonist",
            "series": "recurring_protagonist",
        }
        for token, label in mapping.items():
            if token in text:
                return self._gate(label, 0.56, "heuristic.character", f"token={token}")
        return Evidenced.unknown("no character cues")

    def _match_emotion(self, text: str) -> Evidenced[str]:
        mapping = {
            "funny": "humor",
            "cute": "cuteness",
            "scary": "fear_tension",
            "mystery": "curiosity",
            "wholesome": "empathy",
            "crush": "aspiration",
        }
        for token, label in mapping.items():
            if token in text:
                return self._gate(label, 0.58, "heuristic.emotion", f"token={token}")
        return Evidenced.unknown("no emotion cues")

    def _match_format(self, duration: int | None) -> Evidenced[str]:
        if duration is None:
            return Evidenced.unknown("duration missing")
        # FACT duration → INFERENCE format bucket
        if duration < 15:
            label = "micro_under_15"
        elif duration <= 30:
            label = "short_15_30"
        elif duration <= 45:
            label = "short_30_45"
        elif duration <= 60:
            label = "short_45_60"
        else:
            label = "longform_over_60"
        return Evidenced.inference(
            label,
            0.85,
            "heuristic.duration_bucket",
            rationale=f"duration_seconds={duration}",
        )

    def _bool_cue(
        self,
        text: str,
        *,
        positive: list[str],
        negative: list[str],
        field: str,
    ) -> Evidenced[bool]:
        neg = any(n in text for n in negative)
        pos = any(p in text for p in positive)
        if neg and not pos:
            return Evidenced.inference(False, 0.65, f"heuristic.{field}", "negative cue")
        if pos and not neg:
            return Evidenced.inference(True, 0.65, f"heuristic.{field}", "positive cue")
        if pos and neg:
            return Evidenced.unknown(f"conflicting {field} cues")
        return Evidenced.unknown(f"no {field} cues")

    def _series_potential(self, text: str, recurring: Evidenced[bool]) -> Evidenced[str]:
        if recurring.kind.value == "INFERENCE" and recurring.value is True:
            return Evidenced.inference(
                "high",
                min(recurring.confidence, 0.7),
                "heuristic.series_potential",
                "recurring/episode cues",
            )
        if "part" in text or "episode" in text:
            return self._gate("medium", 0.6, "heuristic.series_potential", "part/episode token")
        return Evidenced.unknown("no series potential cues")


class OpenAIClassifier:
    """Optional LLM classifier — requires OPENAI_API_KEY and classifier_provider=openai."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for openai classifier")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("pip install '.[openai]'") from exc
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.fallback = HeuristicClassifier()
        self.min_confidence = settings.min_confidence_for_label

    def classify(self, rec: VideoRecord) -> ClassificationResult:
        # For safety/cost: fall back to heuristic until prompts are validated on a sample.
        # INFERENCE labels from LLM must still respect UNKNOWN below threshold.
        result = self.fallback.classify(rec)
        result.classifier = f"openai_pending_validation:{self.model}"
        return result


def get_classifier():
    provider = get_settings().classifier_provider.lower()
    if provider == "openai":
        return OpenAIClassifier()
    return HeuristicClassifier()


def run_classify(records: list[VideoRecord] | None = None) -> list[dict[str, Any]]:
    paths = project_paths()
    if records is None:
        import orjson
        from cartoon_niche_radar.models.schemas import VideoRecord as VR

        raw = paths["raw"] / "youtube_videos.jsonl"
        if not raw.exists():
            raise FileNotFoundError(f"Missing {raw}; run collect first.")
        records = [VR.model_validate(orjson.loads(line)) for line in raw.open("rb")]

    clf = get_classifier()
    out: list[dict[str, Any]] = []
    for rec in records:
        result = clf.classify(rec)
        # Force low-confidence fields to UNKNOWN already handled in classifier
        payload = result.model_dump(mode="json")
        out.append(payload)

    write_jsonl(paths["classified"] / "classifications.jsonl", out)
    return out
