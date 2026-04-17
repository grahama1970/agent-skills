"""Discover actors and reference talent via TMDB API."""

from .tmdb_client import (  # noqa: F401
    TMDBPerson, search_people, get_person, get_person_images,
    get_person_movie_credits, get_movie_cast, search_movie, check_api,
)
from .taxonomy import (  # noqa: F401
    extract_bridge_tags_for_person, get_genre_ids_for_bridge,
    build_taxonomy_output, BRIDGE_TO_ACTOR_TYPES,
)
