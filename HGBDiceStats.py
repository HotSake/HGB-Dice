from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from functools import partial
from gameObjects import State
from itertools import chain
from typing import Any, Iterable, Mapping
from decimal import Decimal, getcontext
import HGBRules as hgb

getcontext().prec = 12


class AnalysisType(Enum):
    BOOL = auto()
    RANGE = auto()


@dataclass
class Analysis:
    name: str
    description: str
    datatype: Enum
    effect_params: Mapping
    split_by_source: bool = False
    show_if_missing: bool = False


BASIC_ANALYSES = {
    "MoS": Analysis(
        name="MoS",
        description="Margin of Success",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.RuleEffects.MoS},
        show_if_missing=True,
    ),
    "Hit": Analysis(
        name="Hit",
        description="Hit Rate",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.RuleEffects.Hit},
        show_if_missing=True,
    ),
    "Miss": Analysis(
        name="Miss",
        description="Miss Rate (including Agile if present)",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.RuleEffects.Miss},
        split_by_source=True,
        show_if_missing=True,
    ),
    "Damage": Analysis(
        name="Damage",
        description="Total damage dealt",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.AnalysisEffects.Damage},
        split_by_source=True,
        show_if_missing=True,
    ),
    "Denied": Analysis(
        name="Denied",
        description="Total damage prevented",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.AnalysisEffects.DamageDenied},
        split_by_source=True,
    ),
    "Overdamage": Analysis(
        name="Overdamage",
        description="Damage dealt in excess of H/S",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.AnalysisEffects.Overdamage},
        split_by_source=True,
    ),
}

STATUS_ANALYSES = {
    "Crippled": Analysis(
        name="Crippled",
        description="Defender crippled",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Crippled},
        split_by_source=True,
    ),
    "Destroyed": Analysis(
        name="Destroyed",
        description="Defender destroyed",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Destroyed},
        split_by_source=True,
    ),
    "Haywired": Analysis(
        name="Haywired",
        description="Defender Haywired",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Haywired},
    ),
    "Corrosion": Analysis(
        name="Corrosion",
        description="Defender has Corrosion",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Corrosion},
    ),
}

analyses = {**BASIC_ANALYSES, **STATUS_ANALYSES}


def make_normals(
    totals: Mapping[Decimal, Decimal], scale: Decimal = None
) -> Mapping[Decimal, Decimal]:
    normalized_totals = {val: prob for val, prob in totals.items() if val > 0}
    if not scale:
        total_probs = sum(normalized_totals.values())
        total_probs = Decimal(1) if total_probs == 0 else total_probs
        scale = Decimal(1) / total_probs
    return {val: prob * scale for val, prob in normalized_totals.items()}


def make_mins(totals: Mapping[Decimal, Decimal]) -> Mapping[Decimal, Decimal]:
    return {
        val: sum(prob for t_val, prob in totals.items() if t_val >= val)
        for val in totals.keys()
    }


def do_analysis(states: Iterable[State], analysis: Analysis) -> Mapping[str, Any]:
    """Analyze a collection of states for the supplied analysis type"""
    result = dict()
    group = partial(hgb.group_states, states)
    result["name"] = analysis.name
    result["type"] = analysis.datatype
    base_group = group(hgb.effect_value_key(**analysis.effect_params))
    result["totals"] = base_group
    result["average"] = Decimal(
        sum(prob * val for prob, val in result["totals"].items())
    )
    success_probs = {val: prob for val, prob in result["totals"].items() if val > 0}
    total_probs = sum(success_probs.values())
    total_probs = Decimal(1) if total_probs == 0 else total_probs
    scale = Decimal(1) / total_probs
    result["normalized_totals"] = make_normals(result["totals"], scale=scale)
    result["normalized_average"] = Decimal(
        sum(val * prob for val, prob in result["normalized_totals"].items())
    )
    if result["type"] is AnalysisType.RANGE:
        result["min_totals"] = make_mins(result["totals"])

    if analysis.split_by_source:
        effects = chain.from_iterable(
            state.get_effects(**analysis.effect_params) for state in states
        )
        sources = {eff.source for eff in effects}
        by_source = []
        for source in sources:
            source_res = {
                "name": source,
                "totals": group(
                    hgb.effect_value_key(source=source, **analysis.effect_params)
                ),
                "type": result["type"],
            }
            source_res["average"] = sum(
                prob * val for prob, val in source_res["totals"].items()
            )
            # Normalize using total scale, not source scale
            source_res["normalized_totals"] = make_normals(
                source_res["totals"], scale=scale
            )
            source_res["normalized_average"] = sum(
                val * prob for val, prob in source_res["normalized_totals"].items()
            )
            if source_res["type"] is AnalysisType.RANGE:
                source_res["min_totals"] = make_mins(source_res["totals"])
            by_source.append(source_res)
        result["by_source"] = by_source

    return result
