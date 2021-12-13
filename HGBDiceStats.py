from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import partial
from gameObjects import State
from itertools import chain
from typing import Any, Dict, Iterable, List, Mapping
from decimal import Decimal, getcontext
import HGBRules as hgb
import pprint

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


PDF = Mapping[Decimal, Decimal]


@dataclass
class SourceResult:
    source: str
    type: AnalysisType
    totals: PDF = field(default_factory=dict)
    average: Decimal = Decimal(0)
    normalized_totals: PDF = field(default_factory=dict)
    normalized_average: Decimal = Decimal(0)
    min_totals: PDF = field(default_factory=dict)

    def __str__(self) -> str:
        return ""  # TODO Manually define print. Maybe pprint PDFs, need more \n


class DefaultSourceDict(dict):
    def __init__(self, type: AnalysisType):
        self._type = type
        super().__init__()

    def __missing__(self, key: str) -> SourceResult:
        self[key] = value = SourceResult(
            key,
            self._type,
        )
        return value


@dataclass
class Result:
    name: str
    type: AnalysisType

    def __post_init__(self):  # Use post_init to initialize from other fields
        self.sources = DefaultSourceDict(self.type)

    def __str__(self) -> str:
        out = f"name: {self.name}, type: {self.type}\n"
        if self.sources:
            out += "\n".join(f"{str(source)}" for source in self.sources.values())
        return out


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
        description="Damage prevented by traits",
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


# TODO: Figure out why (no agile -> agile) is showing identical results sometimes
def do_analysis(states: Iterable[State], analysis: Analysis) -> Result:
    """Analyze a collection of states for the supplied analysis type"""
    res = Result(analysis.name, analysis.datatype)
    group = partial(hgb.group_states, states)
    totals = group(hgb.effect_value_key(**analysis.effect_params))
    average = Decimal(sum(val * prob for val, prob in totals.items()))
    success_probs = sum(prob for val, prob in totals.items() if val > 0)
    success_probs = Decimal(1) if success_probs == 0 else success_probs
    scale = Decimal(1) / success_probs
    normalized_totals = make_normals(totals, scale=scale)
    normalized_average = Decimal(
        sum(val * prob for val, prob in normalized_totals.items())
    )
    all_res = SourceResult(
        "All",
        analysis.datatype,
        totals,
        average,
        normalized_totals,
        normalized_average,
    )
    if analysis.datatype is AnalysisType.RANGE:
        all_res.min_totals = make_mins(totals)

    res.sources["All"] = all_res

    if analysis.split_by_source:
        effects = chain.from_iterable(
            state.get_effects(**analysis.effect_params) for state in states
        )
        sources = {eff.source for eff in effects}

        for source in sources:
            totals = group(
                hgb.effect_value_key(source=source, **analysis.effect_params)
            )
            average = sum(prob * val for prob, val in totals.items())
            # Normalize using total scale, not source scale
            normalized_totals = make_normals(totals, scale=scale)
            normalized_average = sum(
                val * prob for val, prob in normalized_totals.items()
            )
            source_res = SourceResult(
                source,
                analysis.datatype,
                totals,
                average,
                normalized_totals,
                normalized_average,
            )
            if analysis.datatype is AnalysisType.RANGE:
                source_res.min_totals = make_mins(totals)
            res.sources[source] = source_res
    return res
