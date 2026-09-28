"""HTTP-level tests for the Flask service using its in-process test client."""

import importlib.util
import os
from fractions import Fraction

import pytest

ODDS_DIR = os.path.join(os.path.dirname(__file__), "..", "odds")


def _load_app():
    spec = importlib.util.spec_from_file_location(
        "odds_app", os.path.join(ODDS_DIR, "app.py")
    )
    module = importlib.util.module_from_spec(spec)
    # app.py does `from dice import ...`, so the odds dir must be on sys.path.
    import sys

    sys.path.insert(0, os.path.abspath(ODDS_DIR))
    spec.loader.exec_module(module)
    return module.app


@pytest.fixture()
def client():
    app = _load_app()
    app.testing = True
    return app.test_client()


def _parse_fraction(text):
    if "/" in text:
        numerator, denominator = text.split("/")
        return Fraction(int(numerator), int(denominator))
    return Fraction(int(text))


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_distribution_is_exact_and_sums_to_one(client):
    response = client.get(
        "/api/distribution",
        query_string={"n_dice": 3, "faces": 6, "keep": 2, "reroll": [1, 6]},
    )
    assert response.status_code == 200
    body = response.get_json()

    rows = body["distribution"]
    # Full, gap-free axis.
    scores = [row["score"] for row in rows]
    assert scores == list(range(2, 25))

    total = sum((_parse_fraction(row["probability"]) for row in rows), Fraction(0))
    assert total == 1
    assert _parse_fraction(body["total_probability"]) == 1

    # Fraction string matches the decimal float.
    for row in rows:
        assert float(_parse_fraction(row["probability"])) == row["decimal"]

    # Expectation computed from rows matches the dedicated field.
    expectation = sum(
        (row["score"] * _parse_fraction(row["probability"]) for row in rows),
        Fraction(0),
    )
    assert _parse_fraction(body["expected_score"]) == expectation
    assert float(expectation) == body["expected_score_decimal"]


def test_tail_probability_matches_rows(client):
    response = client.get(
        "/api/distribution",
        query_string={
            "n_dice": 2,
            "faces": 4,
            "keep": 1,
            "reroll": "1,2",
            "threshold": 6,
        },
    )
    body = response.get_json()
    threshold = body["params"]["threshold"]
    assert threshold == 6

    direct = sum(
        (
            _parse_fraction(row["probability"])
            for row in body["distribution"]
            if row["score"] >= threshold
        ),
        Fraction(0),
    )
    assert _parse_fraction(body["probability_at_least"]) == direct
    assert float(direct) == body["probability_at_least_decimal"]


def test_reroll_csv_and_repeated_params_equivalent(client):
    a = client.get(
        "/api/distribution",
        query_string={"n_dice": 2, "faces": 6, "keep": 1, "reroll": "1,6"},
    ).get_json()
    b = client.get(
        "/api/distribution",
        query_string={
            "n_dice": 2,
            "faces": 6,
            "keep": 1,
            "reroll": [1, 6],
        },
    ).get_json()
    assert a["distribution"] == b["distribution"]


def test_threshold_clamped_to_supported_axis(client):
    body = client.get(
        "/api/distribution",
        query_string={
            "n_dice": 1,
            "faces": 2,
            "keep": 1,
            "threshold": 999,
        },
    ).get_json()
    assert body["params"]["threshold"] == 4
    # Clamping to the maximum total yields the point mass at that total.
    assert _parse_fraction(body["probability_at_least"]) == Fraction(1, 4)


@pytest.mark.parametrize(
    "query",
    [
        {"n_dice": 7, "faces": 6, "keep": 1},
        {"n_dice": 1, "faces": 1, "keep": 1},
        {"n_dice": 3, "faces": 6, "keep": 4},
        {"n_dice": 3, "faces": 6, "keep": 1, "reroll": 7},
        {"n_dice": "x", "faces": 6, "keep": 1},
    ],
)
def test_invalid_inputs_return_400(client, query):
    response = client.get("/api/distribution", query_string=query)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_minimal_rule_two_sided(client):
    body = client.get(
        "/api/distribution",
        query_string={"n_dice": 1, "faces": 2, "keep": 1, "reroll": [1, 2]},
    ).get_json()
    rows = {row["score"]: _parse_fraction(row["probability"]) for row in body["distribution"]}
    # One die: P(1)=1/2, P(3)=1/4, P(4)=1/4, P(2)=0.
    assert rows[1] == Fraction(1, 2)
    assert rows[2] == Fraction(0)
    assert rows[3] == Fraction(1, 4)
    assert rows[4] == Fraction(1, 4)
