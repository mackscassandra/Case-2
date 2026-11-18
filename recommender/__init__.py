"""Big 4 firm & city recommender: scoring engine (no UI).

    from recommender import UserInputs, recommend, load_tables
    results = recommend(load_tables(), UserInputs(salary=80000, weights={"pay": 5, "fitness_outdoors": 4}))
"""
from .data import load_tables
from .schemas import UserInputs
from .scoring import rank_offices, recommend, score_metros, score_zips
from .taxes import take_home

__all__ = ["UserInputs", "load_tables", "recommend", "score_metros", "score_zips", "rank_offices", "take_home"]
