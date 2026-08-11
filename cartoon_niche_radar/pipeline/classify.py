from __future__ import annotations

import re
from typing import Any

from cartoon_niche_radar.models.evidence import Evidenced
from cartoon_niche_radar.models.schemas import ClassificationResult, VideoRecord
from cartoon_niche_radar.storage.export import write_jsonl
from cartoon_niche_radar.utils.config import get_settings, get_taxonomy, project_paths
from cartoon_niche_radar.utils.time import utcnow


CLASSIFIER_VERSION = "heuristic-v3"
OPENAI_CLASSIFIER_VERSION = "openai-v1"


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
        from cartoon_niche_radar.utils.shorts import duration_bin

        mapping = {
            "under_15": "micro_under_15",
            "15_30": "short_15_30",
            "30_45": "short_30_45",
            "45_60": "short_45_60",
            "60_90": "short_60_90",
            "90_180": "short_90_180",
            "over_180": "over_180",
        }
        label = mapping.get(duration_bin(duration).value, "unknown")
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
    """Real structured OpenAI classification. Failures report FALLBACK_HEURISTIC explicitly."""

    def __init__(self, client: Any = None) -> None:
        settings = get_settings()
        if not settings.openai_api_key and client is None:
            raise ValueError("OPENAI_API_KEY required for openai classifier")
        self.model = settings.openai_model
        self.min_confidence = settings.min_confidence_for_label
        self.version = OPENAI_CLASSIFIER_VERSION
        self.fallback = HeuristicClassifier()
        if client is not None:
            self.client = client
        else:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("pip install '.[openai]'") from exc
            self.client = OpenAI(api_key=settings.openai_api_key)

    def classify(self, rec: VideoRecord) -> ClassificationResult:
        try:
            payload = self._request(rec)
            return self._parse(rec, payload)
        except Exception as exc:  # noqa: BLE001 — explicit fallback path
            result = self.fallback.classify(rec)
            result.classifier = "FALLBACK_HEURISTIC"
            result.classifier_version = f"{CLASSIFIER_VERSION}+fallback_from_openai"
            # Preserve explicit failure signal in age evidence
            feats = list(result.age_evidence_features or [])
            feats.append(f"openai_error={type(exc).__name__}")
            result.age_evidence_features = feats
            return result

    def _request(self, rec: VideoRecord) -> dict:
        import json

        system = (
            "You classify short-form animated YouTube videos. "
            "Return ONLY valid JSON. "
            "Never invent concrete age from madeForKids alone. "
            "If evidence is weak, set value null and confidence 0. "
            "For hook and story_structure always return null unless transcript/content evidence is provided."
        )
        user = {
            "title": rec.title,
            "description": (rec.description or "")[:2000],
            "tags": rec.tags,
            "duration_seconds": rec.duration_seconds,
            "made_for_kids_FACT": rec.made_for_kids.value
            if hasattr(rec.made_for_kids, "value")
            else rec.made_for_kids,
            "language": rec.language,
            "channel_subscribers": rec.channel_subscribers,
            "youtube_content_type": rec.youtube_content_type,
            "fields": [
                "target_age",
                "theme",
                "visual_style",
                "character_type",
                "emotional_trigger",
                "dialogue",
                "music",
                "series_potential",
                "hook",
                "story_structure",
            ],
            "age_values": ["2-5", "6-8", "9-12", "13-17", "18-24"],
            "note": "hook/story_structure require content evidence; otherwise null",
        }
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)

    def _parse(self, rec: VideoRecord, payload: dict) -> ClassificationResult:
        def field(name: str, *, allow_without_content: bool = True) -> Evidenced:
            raw = payload.get(name)
            if isinstance(raw, dict):
                value = raw.get("value")
                conf = float(raw.get("confidence") or 0)
                feats = list(raw.get("evidence_features") or [])
            else:
                value, conf, feats = raw, float(payload.get(f"{name}_confidence") or 0.5), []
            if name in {"hook", "story_structure"} and not allow_without_content:
                return Evidenced.unknown(
                    "no content evidence for hook/story_structure",
                    source="openai",
                )
            if value is None or conf < self.min_confidence:
                return Evidenced.unknown(
                    f"low confidence or null for {name}",
                    source="openai",
                )
            return Evidenced.inference(
                value, conf, "openai", rationale=";".join(feats) if feats else None
            )

        # hook/story always UNKNOWN unless payload includes content_evidence=true
        content_ok = bool(payload.get("content_evidence"))
        age = field("target_age")
        fmt = self.fallback._match_format(rec.duration_seconds)
        mfk = (
            rec.made_for_kids.value
            if hasattr(rec.made_for_kids, "value")
            else str(getattr(rec, "made_for_kids", "unknown"))
        )
        return ClassificationResult(
            video_id=rec.video_id,
            target_age=age,
            theme=field("theme"),
            story_structure=field("story_structure", allow_without_content=content_ok),
            hook=field("hook", allow_without_content=content_ok),
            visual_style=field("visual_style"),
            character_type=field("character_type"),
            emotional_trigger=field("emotional_trigger"),
            format=fmt,
            series_potential=field("series_potential"),
            dialogue=field("dialogue"),
            music=field("music"),
            recurring_character=Evidenced.unknown("not requested in openai schema"),
            age_confidence=float(age.confidence or 0),
            classifier_version=self.version,
            age_evidence_features=["provider=openai"],
            made_for_kids_fact=mfk,
            classifier="openai",
            classified_at=utcnow(),
        )


class OptionalLocalClassifier:
    """Optional local embeddings path — INFERENCE only, never FACT."""

    def __init__(self) -> None:
        self.fallback = HeuristicClassifier()
        self.version = "optional_local-v0"

    def classify(self, rec: VideoRecord) -> ClassificationResult:
        # Scaffold only — requires optional deps; otherwise explicit fallback.
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            result = self.fallback.classify(rec)
            result.classifier = "FALLBACK_HEURISTIC"
            result.classifier_version = f"{CLASSIFIER_VERSION}+local_unavailable"
            return result
        result = self.fallback.classify(rec)
        result.classifier = "optional_local_pending"
        result.classifier_version = self.version
        return result


def get_classifier():
    provider = get_settings().classifier_provider.lower()
    if provider == "openai":
        return OpenAIClassifier()
    if provider in {"optional_local", "local"}:
        return OptionalLocalClassifier()
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
        out.append(result.model_dump(mode="json"))

    write_jsonl(paths["classified"] / "classifications.jsonl", out)
    return out
