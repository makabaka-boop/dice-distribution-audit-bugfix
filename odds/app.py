"""Flask service returning exact dice distributions as reduced fractions."""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Dict, List

from flask import Flask, jsonify, request

from dice import (
    MAX_DICE,
    MAX_FACES,
    MIN_DICE,
    MIN_FACES,
    expected_score,
    probability_at_least,
    top_k_distribution,
    validate_params,
)


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health() -> Any:
        return jsonify(status="ok")

    @app.get("/api/distribution")
    def distribution() -> Any:
        # Reroll faces may be repeated params (?reroll=1&reroll=2) or a
        # comma-separated list (?reroll=1,2).  A wholly empty/whitespace
        # parameter contributes no faces; a gap inside a list (e.g. "1,,2")
        # is a malformed token and is rejected below, never silently dropped.
        raw_reroll: List[str] = []
        for part in request.args.getlist("reroll"):
            if not part.strip():
                continue
            raw_reroll.extend(piece.strip() for piece in part.split(","))

        raw_params = {
            "n_dice": request.args.get("n_dice", "1"),
            "faces": request.args.get("faces", "6"),
            "keep": request.args.get("keep", "1"),
            "threshold": request.args.get("threshold", ""),
        }

        try:
            n_dice = _to_int(raw_params["n_dice"], "原骰数")
            faces = _to_int(raw_params["faces"], "面数")
            keep = _to_int(raw_params["keep"], "保留颗数")
            reroll = [_to_int(r, "重掷面") for r in raw_reroll]
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

        try:
            n_dice, faces, keep, reroll_set = validate_params(
                n_dice, faces, keep, reroll
            )
        except ValueError as exc:
            return jsonify(error=str(exc)), 400

        exact = top_k_distribution(n_dice, faces, keep, reroll_set)

        min_score = keep
        max_score = keep * 2 * faces
        missing = [
            s for s in range(min_score, max_score + 1) if s not in exact
        ]
        if missing:
            # Impossible totals still appear with probability 0 so the
            # client always gets the full, gap-free score axis.
            for score in missing:
                exact[score] = Fraction(0)
            exact = dict(sorted(exact.items()))

        expectation = expected_score(exact)
        total_probability = sum(exact.values(), Fraction(0))

        # Threshold defaults to faces + 1 on a single kept die, i.e. the
        # smallest "bonus-die" total; clamped into the supported axis.
        if raw_params["threshold"]:
            try:
                threshold = _to_int(raw_params["threshold"], "阈值")
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
        else:
            threshold = faces + 1
        threshold = max(min_score, min(max_score, threshold))

        at_least = probability_at_least(exact, threshold)

        distribution_records = [
            {
                "score": score,
                "probability": _fraction_string(probability),
                "decimal": float(probability),
            }
            for score, probability in exact.items()
        ]

        return jsonify(
            {
                "params": {
                    "n_dice": n_dice,
                    "faces": faces,
                    "keep": keep,
                    "reroll": sorted(reroll_set),
                    "threshold": threshold,
                },
                "limits": {
                    "n_dice": [MIN_DICE, MAX_DICE],
                    "faces": [MIN_FACES, MAX_FACES],
                },
                "distribution": distribution_records,
                "expected_score": _fraction_string(expectation),
                "expected_score_decimal": float(expectation),
                "probability_at_least": _fraction_string(at_least),
                "probability_at_least_decimal": float(at_least),
                "total_probability": _fraction_string(total_probability),
            }
        )

    return app


def _to_int(raw: str, label: str) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label}必须是整数") from None


def _fraction_string(value: Fraction) -> str:
    """Reduced fraction; omit the denominator when it is 1."""
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
