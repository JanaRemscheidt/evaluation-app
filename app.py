import json
import re
import os
import random
import mimetypes
import uuid
from functools import lru_cache
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from dotenv import load_dotenv
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
load_dotenv()
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "evaluation-app-development")

host = os.environ.get("HOST", "0.0.0.0")
port = int(os.environ.get("PORT", 8080))
debug_mode = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"}

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def resolve_database_url():
    env_names = (
        "DATABASE_URL",
        "WASMER_DATABASE_URL",
        "MYSQL_URL",
        "MYSQL_URI",
        "MYSQL_CONNECTION_STRING",
        "DATABASE_CONNECTION_STRING",
    )

    app.logger.info(
        "Checking database env vars: %s",
        ", ".join(env_names),
    )

    for env_name in env_names:
        candidate_url = os.environ.get(env_name)

        if candidate_url:
            app.logger.info("Found database env: %s", env_name)
            return candidate_url

    app.logger.warning(
        "No database env found among: %s",
        ", ".join(env_names),
    )

    raise RuntimeError("A MySQL DATABASE_URL is required")


try:
    DATABASE_URL = resolve_database_url()

    if not DATABASE_URL.startswith("mysql"):
        raise RuntimeError("DATABASE_URL must point to MySQL")

    app.logger.info("Using MySQL database backend")

except RuntimeError:
    fallback_path = BASE_DIR / "evaluation.db"
    DATABASE_URL = f"sqlite:///{fallback_path}"

    app.logger.warning(
        "No MySQL DATABASE_URL found, falling back to SQLite at %s",
        fallback_path,
    )

engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
metadata = MetaData()

participants = Table(
    "participants",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("participant_uuid", String(64), nullable=False, unique=True),
    Column("participant_label", String(120), nullable=False, default=""),
    Column("created_at", String(32), nullable=False),
)

study_sessions = Table(
    "study_sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_uuid", String(64), nullable=False, unique=True),
    Column("participant_id", Integer, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False),
    Column("started_at", String(32), nullable=False),
    Column("finished_at", String(32)),
)

persona_blocks = Table(
    "persona_blocks",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", Integer, ForeignKey("study_sessions.id", ondelete="CASCADE"), nullable=False),
    Column("persona_id", String(64), nullable=False),
    Column("persona_name", String(255), nullable=False),
    Column("persona_bio", Text),
    Column("order_index", Integer, nullable=False),
    Column("started_at", String(32), nullable=False),
    Column("finished_at", String(32)),
    UniqueConstraint("session_id", "persona_id", name="uq_persona_blocks_session_persona"),
)

block_events = Table(
    "block_events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("persona_block_id", Integer, ForeignKey("persona_blocks.id", ondelete="CASCADE"), nullable=False),
    Column("event_id", String(255), nullable=False),
    Column("event_name", String(255), nullable=False),
    Column("event_type", String(255)),
    Column("location_name", Text),
    Column("tags_json", Text, nullable=False),
    Column("display_order", Integer, nullable=False),
)

event_rankings = Table(
    "event_rankings",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("block_event_id", Integer, ForeignKey("block_events.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("rank_position", Integer, nullable=False),
    Column("fit_score", Integer),
    Column("saved_at", String(32), nullable=False),
)


@lru_cache(maxsize=8)
def load_json_file(filename):
    with (DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def initialize_storage():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    metadata.create_all(engine)


def utcnow_iso():
    return datetime.utcnow().isoformat()


def get_session_participant_uuid():
    participant_uuid = session.get("participant_uuid")

    if not participant_uuid:
        participant_uuid = uuid.uuid4().hex
        session["participant_uuid"] = participant_uuid

    return participant_uuid


def get_session_study_uuid():
    study_session_uuid = session.get("study_session_uuid")

    if not study_session_uuid:
        study_session_uuid = uuid.uuid4().hex
        session["study_session_uuid"] = study_session_uuid

    return study_session_uuid


def _fetch_single_row(connection, table, **filters):
    query = select(table)
    for column_name, value in filters.items():
        query = query.where(getattr(table.c, column_name) == value)
    return connection.execute(query).mappings().first()


def get_or_create_participant(connection, participant_label=None):
    participant_uuid = get_session_participant_uuid()
    participant_label = normalize_participant_label(participant_label or session.get("participant_label"))
    existing_row = _fetch_single_row(connection, participants, participant_uuid=participant_uuid)

    if existing_row is not None:
        if participant_label and existing_row["participant_label"] != participant_label:
            connection.execute(
                participants.update()
                .where(participants.c.id == existing_row["id"])
                .values(participant_label=participant_label)
            )
            existing_row = _fetch_single_row(connection, participants, participant_uuid=participant_uuid)

        if participant_label and not session.get("participant_label"):
            session["participant_label"] = participant_label

        return existing_row

    if not participant_label:
        raise ValueError("participant label is required")

    created_at = utcnow_iso()

    try:
        connection.execute(
            participants.insert().values(
                participant_uuid=participant_uuid,
                participant_label=participant_label,
                created_at=created_at,
            )
        )
    except IntegrityError:
        pass

    participant_row = _fetch_single_row(connection, participants, participant_uuid=participant_uuid)

    if participant_row is None:
        raise RuntimeError("failed to resolve participant")

    session["participant_label"] = participant_label

    return participant_row


def get_or_create_study_session(connection, participant_row):
    study_session_uuid = get_session_study_uuid()
    existing_row = _fetch_single_row(connection, study_sessions, session_uuid=study_session_uuid)

    if existing_row is not None:
        return existing_row

    started_at = utcnow_iso()

    try:
        connection.execute(
            study_sessions.insert().values(
                session_uuid=study_session_uuid,
                participant_id=participant_row["id"],
                started_at=started_at,
                finished_at=None,
            )
        )
    except IntegrityError:
        pass

    study_session_row = _fetch_single_row(connection, study_sessions, session_uuid=study_session_uuid)

    if study_session_row is None:
        raise RuntimeError("failed to resolve study session")

    return study_session_row


def get_or_create_persona_block(connection, study_session_row, persona, order_index, started_at=None):
    existing_row = connection.execute(
        select(persona_blocks).where(
            persona_blocks.c.session_id == study_session_row["id"],
            persona_blocks.c.persona_id == persona["id"],
        )
    ).mappings().first()

    if existing_row is not None:
        return existing_row

    started_at = started_at or utcnow_iso()

    try:
        connection.execute(
            persona_blocks.insert().values(
                session_id=study_session_row["id"],
                persona_id=persona["id"],
                persona_name=persona["name"],
                persona_bio=persona.get("bio", ""),
                order_index=order_index,
                started_at=started_at,
                finished_at=None,
            )
        )
    except IntegrityError:
        pass

    persona_block_row = connection.execute(
        select(persona_blocks).where(
            persona_blocks.c.session_id == study_session_row["id"],
            persona_blocks.c.persona_id == persona["id"],
        )
    ).mappings().first()

    if persona_block_row is None:
        raise RuntimeError("failed to resolve persona block")

    return persona_block_row


def finalize_persona_block(connection, persona_block_id, finished_at):
    connection.execute(
        persona_blocks.update()
        .where(persona_blocks.c.id == persona_block_id)
        .values(finished_at=finished_at)
    )


def finalize_study_session(connection, study_session_id, finished_at):
    connection.execute(
        study_sessions.update()
        .where(study_sessions.c.id == study_session_id)
        .values(finished_at=finished_at)
    )


def migrate_legacy_rankings():
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if "ranking_submissions" not in existing_tables or "ranking_submission_items" not in existing_tables:
        return

    with engine.begin() as connection:
        legacy_submissions = connection.exec_driver_sql(
            "SELECT id, submission_uuid, session_uuid, participant_label, persona_id, persona_name, persona_bio, generated_at, saved_at FROM ranking_submissions ORDER BY session_uuid, saved_at, id"
        ).mappings().all()

        if not legacy_submissions:
            return

        block_orders_by_session = {}
        session_finished_at_by_session = {}

        for submission in legacy_submissions:
            participant_uuid = str(submission["session_uuid"] or "").strip() or uuid.uuid4().hex
            participant_label = normalize_participant_label(submission["participant_label"])
            saved_at = str(submission["saved_at"] or submission["generated_at"] or utcnow_iso())
            participant_row = _fetch_single_row(connection, participants, participant_uuid=participant_uuid)

            if participant_row is None:
                connection.execute(
                    participants.insert().values(
                        participant_uuid=participant_uuid,
                        participant_label=participant_label,
                        created_at=saved_at,
                    )
                )
                participant_row = _fetch_single_row(connection, participants, participant_uuid=participant_uuid)

            if participant_row is None:
                raise RuntimeError("failed to migrate participant")

            study_session_row = _fetch_single_row(connection, study_sessions, session_uuid=participant_uuid)

            if study_session_row is None:
                connection.execute(
                    study_sessions.insert().values(
                        session_uuid=participant_uuid,
                        participant_id=participant_row["id"],
                        started_at=saved_at,
                        finished_at=None,
                    )
                )
                study_session_row = _fetch_single_row(connection, study_sessions, session_uuid=participant_uuid)

            if study_session_row is None:
                raise RuntimeError("failed to migrate study session")

            order_index = block_orders_by_session.get(study_session_row["id"], 0) + 1
            block_orders_by_session[study_session_row["id"]] = order_index
            session_finished_at_by_session[study_session_row["id"]] = saved_at

            persona_block_row = connection.execute(
                select(persona_blocks).where(
                    persona_blocks.c.session_id == study_session_row["id"],
                    persona_blocks.c.persona_id == submission["persona_id"],
                )
            ).mappings().first()

            if persona_block_row is None:
                connection.execute(
                    persona_blocks.insert().values(
                        session_id=study_session_row["id"],
                        persona_id=submission["persona_id"],
                        persona_name=submission["persona_name"],
                        persona_bio=submission["persona_bio"],
                        order_index=order_index,
                        started_at=saved_at,
                        finished_at=saved_at,
                    )
                )
                persona_block_row = connection.execute(
                    select(persona_blocks).where(
                        persona_blocks.c.session_id == study_session_row["id"],
                        persona_blocks.c.persona_id == submission["persona_id"],
                    )
                ).mappings().first()

            if persona_block_row is None:
                raise RuntimeError("failed to migrate persona block")

            legacy_items = connection.exec_driver_sql(
                "SELECT position, event_id, event_name, star_category, location_name, tags_json, event_type FROM ranking_submission_items WHERE submission_id = %s ORDER BY position",
                (submission["id"],),
            ).mappings().all()

            for item in legacy_items:
                block_event_row = connection.execute(
                    select(block_events).where(
                        block_events.c.persona_block_id == persona_block_row["id"],
                        block_events.c.event_id == item["event_id"],
                    )
                ).mappings().first()

                if block_event_row is None:
                    connection.execute(
                        block_events.insert().values(
                            persona_block_id=persona_block_row["id"],
                            event_id=item["event_id"],
                            event_name=item["event_name"],
                            event_type=item["event_type"],
                            location_name=item["location_name"],
                            tags_json=item["tags_json"] or "[]",
                            display_order=int(item["position"] or 0),
                        )
                    )
                    block_event_row = connection.execute(
                        select(block_events).where(
                            block_events.c.persona_block_id == persona_block_row["id"],
                            block_events.c.event_id == item["event_id"],
                        )
                    ).mappings().first()

                if block_event_row is None:
                    raise RuntimeError("failed to migrate block event")

                ranking_row = connection.execute(
                    select(event_rankings).where(event_rankings.c.block_event_id == block_event_row["id"])
                ).mappings().first()

                if ranking_row is None:
                    connection.execute(
                        event_rankings.insert().values(
                            block_event_id=block_event_row["id"],
                            rank_position=int(item["position"] or 0),
                            fit_score=item["star_category"],
                            saved_at=saved_at,
                        )
                    )

            finalize_persona_block(connection, persona_block_row["id"], saved_at)

        for study_session_id, finished_at in session_finished_at_by_session.items():
            finalize_study_session(connection, study_session_id, finished_at)

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS ranking_submission_items")
        connection.exec_driver_sql("DROP TABLE IF EXISTS ranking_submissions")
app.logger.info("Using database backend %s", engine.url.render_as_string(hide_password=True))


def compact_text(value, max_length=180):
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


def normalize_participant_label(value):
    if value is None:
        return ""

    normalized = re.sub(r"\s+", " ", str(value).strip())
    return normalized[:120]


def participant_label_exists(participant_label):
    if not participant_label:
        return False

    with engine.begin() as connection:
        existing_participant = connection.execute(
            select(participants.c.id).where(participants.c.participant_label == participant_label)
        ).first()

    return existing_participant is not None


initialize_storage()
migrate_legacy_rankings()


def normalize_genre_weights(values, start=0.95, step=0.08, minimum=0.35):
    if isinstance(values, dict):
        return values

    if not values:
        return {}

    return {
        value: round(max(start - (index * step), minimum), 2)
        for index, value in enumerate(values)
        if isinstance(value, str) and value.strip()
    }


def build_persona_record(persona):
    preferences = persona.get("preferences", {}) or {}
    display = persona.get("display", {}) or {}
    recommendation_profile = persona.get("recommendation_profile", {}) or {}
    behavior = persona.get("behavior", {}) or recommendation_profile.get("behavior", {}) or {}
    quote = persona.get("quote") or display.get("quote", "")
    description = persona.get("description") or display.get("description") or persona.get("summary", "")
    motivation = persona.get("motivation") or display.get("motivation", "") or behavior.get("motivation", "")
    speech = persona.get("speech") or display.get("event_reflection", "")
    avatar_style = persona.get("avatarStyle") or persona.get("avatar_style") or display.get("avatarStyle") or display.get("avatar_style") or []
    likes = persona.get("likes", []) or []
    avoid = persona.get("avoid", []) or []
    liked_genre_weights = normalize_genre_weights(preferences.get("liked_genres", {}), start=0.95, step=0.08, minimum=0.35)
    disliked_genre_weights = normalize_genre_weights(preferences.get("disliked_genres", {}), start=0.9, step=0.08, minimum=0.3)

    liked_genres = sorted(
        [
            {"name": name, "weight": weight}
            for name, weight in liked_genre_weights.items()
        ],
        key=lambda item: item["weight"],
        reverse=True,
    )
    disliked_genres = sorted(
        [
            {"name": name, "weight": weight}
            for name, weight in disliked_genre_weights.items()
        ],
        key=lambda item: item["weight"],
        reverse=True,
    )

    if not liked_genres and likes:
        liked_genres = [
            {"name": like, "weight": round(max(0.95 - (index * 0.08), 0.35), 2)}
            for index, like in enumerate(likes)
        ]

    if not disliked_genres and avoid:
        disliked_genres = [
            {"name": item, "weight": round(max(0.9 - (index * 0.08), 0.3), 2)}
            for index, item in enumerate(avoid)
        ]

    interests = []
    for tag in persona.get("tags", []):
        readable_tag = tag.replace("_", " ")
        if readable_tag not in interests:
            interests.append(readable_tag)

    for like in likes:
        if like not in interests:
            interests.append(like)

    for genre in liked_genres[:4]:
        if genre["name"] not in interests:
            interests.append(genre["name"])

    for tag in recommendation_profile.get("tags", []) or []:
        readable_tag = tag.replace("_", " ")
        if readable_tag not in interests:
            interests.append(readable_tag)

    resolved_name = persona.get("name") or display.get("name") or "Unbekannte Persona"
    name_parts = [
        part.strip(".,")
        for part in resolved_name.split()
        if part.lower() not in {"und", "der", "die", "das", "von", "zu", "van"}
    ]
    initials = "".join(part[0] for part in name_parts[:2] if part) or "?"

    return {
        "id": persona.get("id"),
        "name": resolved_name,
        "summary": description,
        "bio": description,
        "quote": quote,
        "interests": interests[:5],
        "tags": persona.get("tags", []) or recommendation_profile.get("tags", []),
        "behavior": behavior,
        "liked_genres": liked_genres,
        "disliked_genres": disliked_genres,
        "feature_preferences": persona.get("feature_preferences", {}),
        "motivation": motivation,
        "speech": speech,
        "avatar_style": avatar_style,
        "likes": likes,
        "avoid": avoid,
        "initials": initials.upper(),
    }


def build_event_record(event):
    location = event.get("location", {}) or {}
    address = location.get("address", {}) or {}
    occurrences = event.get("occurrences") or [{}]
    first_occurrence = occurrences[0] if occurrences else {}

    image_candidates = event.get("image") or []
    image = next((candidate for candidate in image_candidates if isinstance(candidate, str)), None)

    return {
        "id": event.get("@id", event.get("url", event.get("name", "event"))),
        "name": event.get("name", "Unbenanntes Event"),
        "type": event.get("@type", "Event"),
        "description": compact_text(event.get("description", ""), 220),
        "url": event.get("url"),
        "start_date": event.get("startDate") or first_occurrence.get("startDate"),
        "end_date": event.get("endDate") or first_occurrence.get("endDate"),
        "location_name": location.get("name") or address.get("addressLocality") or "Unbekannter Ort",
        "city": address.get("addressLocality"),
        "keywords": event.get("keywords", []),
        "image": image,
    }


def score_event_for_persona(persona, event):
    haystack = " ".join(
        [
            event.get("name", ""),
            event.get("description", ""),
            event.get("location_name", ""),
            event.get("type", ""),
            " ".join(event.get("keywords", [])),
        ]
    ).lower()

    score = 0.0
    preferences = persona.get("preferences", {})
    liked_genres = normalize_genre_weights(preferences.get("liked_genres", {}))
    disliked_genres = normalize_genre_weights(preferences.get("disliked_genres", {}), start=0.9, step=0.08, minimum=0.3)
    synonym_map = {
        "ausstellung": ["exhibition", "exhibitionevent", "ausstellung"],
        "vortrag, infotainment, talk": ["talk", "vortrag", "vorträge", "führungen", "guided_tour", "gespräch"],
        "workshop": ["workshop", "mitmach", "tüftel", "tinkern"],
        "film, kino": ["film", "kino"],
        "kinderprogramm": ["familie", "families", "kinder", "children", "jugendliche"],
        "musical": ["musical"],
        "jazz": ["jazz"],
        "klassik": ["klassik", "classical", "classical music", "orgel", "chormusik"],
        "poetry slam": ["poetry", "slam", "literatur"],
        "kabarett": ["kabarett", "comedy"],
        "performance": ["performance", "art"],
        "stadtführungen, erlebnisführungen": ["guided_tour", "führungen", "tour", "sightseeing"],
    }

    for genre, weight in liked_genres.items():
        genre_key = genre.lower()
        match_terms = [genre_key] + synonym_map.get(genre_key, [])
        if any(term in haystack for term in match_terms):
            score += float(weight)

    for genre, weight in disliked_genres.items():
        genre_key = genre.lower()
        match_terms = [genre_key] + synonym_map.get(genre_key, [])
        if any(term in haystack for term in match_terms):
            score -= float(weight) * 0.75

    return round(max(score, 0.0), 2)


def get_personas():
    return [build_persona_record(persona) for persona in load_json_file("personas.json")]


def normalize_submission_ranking(ranking_entries):
    normalized_entries = []

    if not isinstance(ranking_entries, list):
        raise ValueError("ranking must be a list")

    for fallback_position, entry in enumerate(ranking_entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError("ranking entry must be an object")

        event_id = str(entry.get("eventId") or "").strip()

        if not event_id:
            raise ValueError("ranking entry is missing eventId")

        normalized_entries.append(
            {
                "position": int(entry.get("position") or fallback_position),
                "event_id": event_id,
                "event_name": str(entry.get("eventName") or "Unbenanntes Event"),
                "star_category": int(entry.get("starCategory") or 0),
                "location_name": str(entry.get("location") or ""),
                "tags": [tag for tag in (entry.get("tags") or []) if isinstance(tag, str) and tag.strip()],
                "event_type": str(entry.get("eventType") or "Event"),
            }
        )

    normalized_entries.sort(key=lambda item: item["position"])

    return normalized_entries


def get_participant_uuid():
    return get_session_participant_uuid()


def save_ranking_submission(persona, payload, is_final_persona=False):
    ranking_entries = normalize_submission_ranking(payload.get("ranking", []))
    participant_label = normalize_participant_label(
        payload.get("participantLabel") or session.get("participant_label")
    )

    if len(ranking_entries) != 10:
        raise ValueError("ranking must contain exactly 10 events")

    if not participant_label:
        raise ValueError("participant label is required")

    saved_at = utcnow_iso()
    started_at = str(payload.get("generatedAt") or saved_at)
    persona_bio = payload.get("persona", {}).get("bio") or persona.get("bio", "")
    order_index = 1

    persona_block_row = None
    study_session_row = None
    participant_row = None

    with engine.begin() as connection:
        participant_row = get_or_create_participant(connection, participant_label=participant_label)
        study_session_row = get_or_create_study_session(connection, participant_row)

        existing_block = connection.execute(
            select(persona_blocks.c.id).where(
                persona_blocks.c.session_id == study_session_row["id"],
                persona_blocks.c.persona_id == persona["id"],
            )
        ).mappings().first()

        if existing_block is not None:
            raise ValueError("ranking already saved for this participant and persona")

        persona_order = session.get("persona_order", [])

        if persona["id"] in persona_order:
            order_index = persona_order.index(persona["id"]) + 1

        persona_block_row = get_or_create_persona_block(
            connection,
            study_session_row,
            persona,
            order_index,
            started_at=started_at,
        )

        for entry in ranking_entries:
            block_event_result = connection.execute(
                block_events.insert().values(
                    persona_block_id=persona_block_row["id"],
                    event_id=entry["event_id"],
                    event_name=entry["event_name"],
                    event_type=entry["event_type"],
                    location_name=entry["location_name"],
                    tags_json=json.dumps(entry["tags"], ensure_ascii=False),
                    display_order=entry["position"],
                )
            )

            block_event_id = block_event_result.inserted_primary_key[0]

            connection.execute(
                event_rankings.insert().values(
                    block_event_id=block_event_id,
                    rank_position=entry["position"],
                    fit_score=entry["star_category"],
                    saved_at=saved_at,
                )
            )

        finalize_persona_block(connection, persona_block_row["id"], saved_at)

        if is_final_persona:
            finalize_study_session(connection, study_session_row["id"], saved_at)

    return {
        "submissionId": str(persona_block_row["id"]),
        "sessionId": study_session_row["session_uuid"],
        "participantLabel": participant_row["participant_label"],
        "rankingCount": len(ranking_entries),
    }


def submission_already_exists(persona_id):
    study_session_uuid = session.get("study_session_uuid")

    if not study_session_uuid:
        return False

    with engine.begin() as connection:
        study_session_row = connection.execute(
            select(study_sessions.c.id).where(study_sessions.c.session_uuid == study_session_uuid)
        ).mappings().first()

        if study_session_row is None:
            return False

        existing_submission = connection.execute(
            select(persona_blocks.c.id).where(
                persona_blocks.c.session_id == study_session_row["id"],
                persona_blocks.c.persona_id == persona_id,
            )
        ).mappings().first()

    return existing_submission is not None


def get_persona_submission_history(persona_id):
    with engine.begin() as connection:
        submissions = connection.execute(
            select(
                persona_blocks.c.id.label("persona_block_id"),
                persona_blocks.c.session_id,
                persona_blocks.c.persona_id,
                persona_blocks.c.persona_name,
                persona_blocks.c.persona_bio,
                persona_blocks.c.order_index,
                persona_blocks.c.started_at,
                persona_blocks.c.finished_at,
                study_sessions.c.session_uuid,
                participants.c.participant_label,
            )
            .select_from(
                persona_blocks.join(study_sessions, persona_blocks.c.session_id == study_sessions.c.id).join(
                    participants, study_sessions.c.participant_id == participants.c.id
                )
            )
            .where(persona_blocks.c.persona_id == persona_id)
            .order_by(persona_blocks.c.finished_at.desc(), persona_blocks.c.id.desc())
        ).mappings().all()

        if not submissions:
            return []

        submission_ids = [submission["persona_block_id"] for submission in submissions]
        item_rows = connection.execute(
            select(
                block_events.c.persona_block_id,
                block_events.c.display_order,
                block_events.c.event_id,
                block_events.c.event_name,
                block_events.c.location_name,
                block_events.c.tags_json,
                block_events.c.event_type,
                event_rankings.c.rank_position,
                event_rankings.c.fit_score,
                event_rankings.c.saved_at,
            )
            .select_from(block_events.join(event_rankings, block_events.c.id == event_rankings.c.block_event_id))
            .where(block_events.c.persona_block_id.in_(submission_ids))
            .order_by(block_events.c.persona_block_id, block_events.c.display_order)
        ).mappings().all()

    items_by_submission = {}
    for item_row in item_rows:
        items_by_submission.setdefault(item_row["persona_block_id"], []).append(item_row)

    history = []
    for submission in submissions:
        ranking_items = []

        for item_row in items_by_submission.get(submission["persona_block_id"], []):
            ranking_items.append(
                {
                    "position": item_row["rank_position"],
                    "eventId": item_row["event_id"],
                    "eventName": item_row["event_name"],
                    "starCategory": item_row["fit_score"],
                    "locationName": item_row["location_name"],
                    "tags": json.loads(item_row["tags_json"] or "[]"),
                    "eventType": item_row["event_type"],
                }
            )

        history.append(
            {
                "submissionId": str(submission["persona_block_id"]),
                "participantLabel": submission["participant_label"],
                "sessionId": submission["session_uuid"],
                "personaId": submission["persona_id"],
                "personaName": submission["persona_name"],
                "personaBio": submission["persona_bio"],
                "generatedAt": submission["started_at"],
                "savedAt": submission["finished_at"],
                "ranking": ranking_items,
            }
        )

    return history


def build_persona_ranking_record(event):
    top_shared_features = event.get("top_shared_features") or []
    feature_summary = ", ".join(
        feature.get("feature", "")
        for feature in top_shared_features
        if isinstance(feature, dict) and feature.get("feature")
    )

    # Prefer the original event description if available (these ranking files
    # often contain the full event description). Fall back to a compact
    # summary built from cluster metadata when not present.
    original_description = event.get("description")

    if original_description:
        description_text = original_description
    else:
        description_parts = []
        cluster_label = event.get("cluster_label")
        strongest_feature_group = event.get("strongest_feature_group")

        if cluster_label:
            description_parts.append(cluster_label)
        if strongest_feature_group:
            description_parts.append(f"stark bei {strongest_feature_group}")
        if feature_summary:
            description_parts.append(feature_summary)

        description_text = " · ".join(description_parts)

    schema_type = event.get("schema_type")

    if not schema_type and isinstance(event.get("schema"), dict):
        schema_type = event["schema"].get("@type") or event["schema"].get("schema_type")

    return {
        "id": event.get("event_id", event.get("event_url", event.get("title", "event"))),
        "name": event.get("title", "Unbenanntes Event"),
        "type": event.get("cluster_label", "Event"),
        "description": description_text,
        "url": event.get("event_url"),
        "title": event.get("title", "Unbenanntes Event"),
        "venue": event.get("venue"),
        "genre": event.get("genre"),
        "category": event.get("category"),
        "schema_type": schema_type,
        "start_date": event.get("start_date"),
        "end_date": event.get("end_date"),
        "location_name": event.get("venue") or event.get("city") or "Unbekannter Ort",
        "city": event.get("city"),
        "keywords": [
            value
            for value in [event.get("cluster_label"), event.get("strongest_feature_group"), feature_summary]
            if value
        ],
        "image": event.get("image"),
        "match_score": event.get("match_score"),
        "rank": event.get("rank"),
    }


def extract_ranked_events(ranking_data):
    ranked_events = []

    top_level_events = ranking_data.get("events") or []

    for event in top_level_events:
        ranked_events.append(build_persona_ranking_record(event))

    for cluster in ranking_data.get("clusters", []):
        for event in cluster.get("selected_events", []):
            ranked_events.append(build_persona_ranking_record(event))

    return ranked_events


def get_shuffled_persona_order(personas):
    persona_ids = [persona["id"] for persona in personas]
    stored_order = session.get("persona_order")

    if stored_order and set(stored_order) == set(persona_ids) and len(stored_order) == len(persona_ids):
        ordered_personas = [next(persona for persona in personas if persona["id"] == persona_id) for persona_id in stored_order]
        return ordered_personas

    shuffled_ids = persona_ids[:]
    random.shuffle(shuffled_ids)
    session["persona_order"] = shuffled_ids
    session["completed_persona_ids"] = []
    return [next(persona for persona in personas if persona["id"] == persona_id) for persona_id in shuffled_ids]


def get_events_for_persona(persona):
    ranking_file = f"persona_rankings/events_{persona['id']}.json"
    ranking_data = load_json_file(ranking_file)
    events = extract_ranked_events(ranking_data)

    if len(events) < 10:
        return events

    return events[:10]


def get_expected_persona_id(persona_order):
    completed_persona_ids = session.get("completed_persona_ids", [])

    for persona_id in persona_order:
        if persona_id not in completed_persona_ids:
            return persona_id

    return None


def get_next_persona_url():
    personas = get_personas()

    if not personas:
        return url_for("complete_page")

    ordered_personas = get_shuffled_persona_order(personas)
    expected_persona_id = get_expected_persona_id([persona["id"] for persona in ordered_personas])

    if expected_persona_id is None:
        return url_for("complete_page")

    return url_for("persona_page", persona_id=expected_persona_id)


@app.route("/participant-label", methods=["POST"])
def update_participant_label():
    payload = request.get_json(silent=True) or {}
    participant_label = normalize_participant_label(payload.get("participantLabel"))

    if not participant_label:
        return jsonify({"error": "participantLabel is required", "saved": False}), 400

    if participant_label_exists(participant_label):
        return jsonify({"error": "participantLabel already exists", "saved": False}), 409

    session["participant_label"] = participant_label
    return jsonify({"participantLabel": participant_label, "saved": True})


@app.route("/")
def index():
    if not session.get("participant_label"):
        return render_template("start.html", participant_label="")

    return redirect(get_next_persona_url())


@app.route("/start", methods=["GET", "POST"])
def start():
    if request.method == "GET":
        return render_template("start.html", participant_label=session.get("participant_label", ""))

    payload = request.get_json(silent=True) or {}
    participant_label = normalize_participant_label(payload.get("participantLabel") or request.form.get("participantLabel"))

    if not participant_label:
        return jsonify({"error": "participantLabel is required", "saved": False}), 400

    if participant_label_exists(participant_label):
        if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
            return jsonify({"error": "participantLabel already exists", "saved": False}), 409

        return render_template(
            "start.html",
            participant_label=participant_label,
            error_message="Dieser Name ist bereits vergeben. Bitte wähle einen anderen Namen oder ein anderes Kürzel.",
        ), 409

    # Always begin a fresh round with a fresh randomized persona order.
    session.pop("persona_order", None)
    session["participant_label"] = participant_label
    session["participant_uuid"] = uuid.uuid4().hex
    session["study_session_uuid"] = uuid.uuid4().hex
    session["completed_persona_ids"] = []

    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"participantLabel": participant_label, "nextUrl": get_next_persona_url(), "saved": True})

    return redirect(get_next_persona_url())


@app.route("/persona/<persona_id>")
def persona_page(persona_id):
    if not session.get("participant_label"):
        return redirect(url_for("start"))

    personas = get_shuffled_persona_order(get_personas())
    if not personas:
        return redirect(url_for("index"))

    persona_order = [persona["id"] for persona in personas]
    expected_persona_id = get_expected_persona_id(persona_order)

    if expected_persona_id is None:
        return redirect(url_for("complete_page"))

    if persona_id != expected_persona_id:
        return redirect(url_for("persona_page", persona_id=expected_persona_id))

    persona = next(persona for persona in personas if persona["id"] == persona_id)
    persona_index = persona_order.index(persona_id) + 1

    return render_template(
        "index.html",
        persona=persona,
        events=get_events_for_persona(persona),
        persona_count=len(personas),
        persona_index=persona_index,
        event_count=10,
        complete_url=url_for("complete_persona", persona_id=persona_id),
        participant_label=session.get("participant_label", ""),
    )


@app.route("/persona/<persona_id>/complete", methods=["POST"])
def complete_persona(persona_id):
    if not session.get("participant_label"):
        return jsonify({"error": "participantLabel is required", "completed": False}), 400

    personas = get_shuffled_persona_order(get_personas())
    if not personas:
        return jsonify({"nextUrl": url_for("complete_page"), "completed": True})

    persona_order = [persona["id"] for persona in personas]
    expected_persona_id = get_expected_persona_id(persona_order)

    if expected_persona_id is None:
        return jsonify({"nextUrl": url_for("complete_page"), "completed": True})

    if persona_id != expected_persona_id:
        return jsonify({"nextUrl": url_for("persona_page", persona_id=expected_persona_id), "completed": False}), 409

    payload = request.get_json(silent=True) or {}
    completed_persona_ids = session.get("completed_persona_ids", [])
    is_final_persona = len(completed_persona_ids) + 1 >= len(personas)

    try:
        if not submission_already_exists(persona_id):
            save_ranking_submission(
                next(persona for persona in personas if persona["id"] == persona_id),
                payload,
                is_final_persona=is_final_persona,
            )
    except (StopIteration, ValueError, RuntimeError) as error:
        return jsonify({"error": str(error), "completed": False}), 400

    if persona_id not in completed_persona_ids:
        completed_persona_ids.append(persona_id)
    session["completed_persona_ids"] = completed_persona_ids

    next_persona_id = get_expected_persona_id(persona_order)
    next_url = url_for("persona_page", persona_id=next_persona_id) if next_persona_id else url_for("complete_page")

    return jsonify({"nextUrl": next_url, "completed": next_persona_id is None, "saved": True})


@app.route("/complete")
def complete_page():
    persona_count = len(get_personas())
    return render_template("complete.html", persona_count=persona_count, total_count=persona_count)


@app.route("/api/persona/<persona_id>/submissions")
def persona_submissions(persona_id):
    personas = get_personas()
    persona = next((item for item in personas if item["id"] == persona_id), None)

    if persona is None:
        return jsonify({"error": "unknown persona", "submissions": []}), 404

    submissions = get_persona_submission_history(persona_id)

    return jsonify(
        {
            "personaId": persona_id,
            "personaName": persona["name"],
            "submissionCount": len(submissions),
            "submissions": submissions,
        }
    )


@app.route("/restart")
def restart():
    session.pop("persona_order", None)
    session.pop("completed_persona_ids", None)
    session.pop("participant_label", None)
    session.pop("participant_uuid", None)
    session.pop("study_session_uuid", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=debug_mode, host=host, port=port)
