import json
import re
import random
import mimetypes
from functools import lru_cache
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, session, url_for

app = Flask(__name__)
app.config["SECRET_KEY"] = "evaluation-app-development"

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


@lru_cache(maxsize=8)
def load_json_file(filename):
    with (DATA_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def compact_text(value, max_length=180):
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


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

    return {
        "id": event.get("event_id", event.get("event_url", event.get("title", "event"))),
        "name": event.get("title", "Unbenanntes Event"),
        "type": event.get("cluster_label", "Event"),
        "description": description_text,
        "url": event.get("event_url"),
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


@app.route("/")
def index():
    personas = get_personas()
    if not personas:
        return render_template("complete.html", persona_count=0, total_count=0)

    ordered_personas = get_shuffled_persona_order(personas)
    expected_persona_id = get_expected_persona_id([persona["id"] for persona in ordered_personas])

    if expected_persona_id is None:
        return redirect(url_for("complete_page"))

    return redirect(url_for("persona_page", persona_id=expected_persona_id))


@app.route("/persona/<persona_id>")
def persona_page(persona_id):
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

    return render_template(
        "index.html",
        persona=persona,
        events=get_events_for_persona(persona),
        persona_count=len(personas),
        event_count=10,
        complete_url=url_for("complete_persona", persona_id=persona_id),
    )


@app.route("/persona/<persona_id>/complete", methods=["POST"])
def complete_persona(persona_id):
    personas = get_shuffled_persona_order(get_personas())
    if not personas:
        return jsonify({"nextUrl": url_for("complete_page"), "completed": True})

    persona_order = [persona["id"] for persona in personas]
    expected_persona_id = get_expected_persona_id(persona_order)

    if expected_persona_id is None:
        return jsonify({"nextUrl": url_for("complete_page"), "completed": True})

    if persona_id != expected_persona_id:
        return jsonify({"nextUrl": url_for("persona_page", persona_id=expected_persona_id), "completed": False}), 409

    completed_persona_ids = session.get("completed_persona_ids", [])
    if persona_id not in completed_persona_ids:
        completed_persona_ids.append(persona_id)
    session["completed_persona_ids"] = completed_persona_ids

    next_persona_id = get_expected_persona_id(persona_order)
    next_url = url_for("persona_page", persona_id=next_persona_id) if next_persona_id else url_for("complete_page")

    return jsonify({"nextUrl": next_url, "completed": next_persona_id is None})


@app.route("/complete")
def complete_page():
    persona_count = len(get_personas())
    return render_template("complete.html", persona_count=persona_count, total_count=persona_count)


@app.route("/restart")
def restart():
    session.pop("persona_order", None)
    session.pop("completed_persona_ids", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5005)
