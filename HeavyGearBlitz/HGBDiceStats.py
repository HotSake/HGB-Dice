from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum, auto
from functools import partial
from itertools import chain
from typing import Dict, Iterable, List, Mapping

from diceGame.gameObjects import State
from . import HGBRules as hgb

getcontext().prec = 12


class AnalysisType(Enum):
    """Enum to distinguish between boolean analyses and those with a range of
    possible values. Used to determine how to plot the results.
    """

    BOOL = auto()
    RANGE = auto()


@dataclass
class Analysis:
    """Framework of a statistical analysis that can be run on a PDF (probability
    distribution function).

    effect_params is a mapping of parameters to filter out the relevant Effects from
    the set of game States. Usually this can be done by giving the Effect name alone.

    Example: {"name": hgb.RuleEffects.MoS} would perform statistical analysis on all
        Effects with the enum hgb.RuleEffects.MoS as their name parameter.
    """

    name: str  # Name of analysis for display
    description: str  # Description of analysis
    datatype: Enum  # Type of analysis (boolean or range)
    effect_params: Mapping  # Parameters to select relevant effects from game States
    split_by_source: bool = False  # Perform sub-analysis by Effect source?
    show_if_missing: bool = False  # Show if zero probability of occurring?


# Type alias for a probability distribution function
PDF = hgb.PDF


@dataclass
class SourceResult:
    """Special class for a Result filtered by source, e.g. damage from fire only"""

    source: str
    type: AnalysisType
    totals: PDF = field(default_factory=dict)
    average: Decimal = Decimal(0)
    normalized_totals: PDF = field(default_factory=dict)
    normalized_average: Decimal = Decimal(0)
    min_totals: PDF = field(default_factory=dict)

    def __str__(self) -> str:
        out = f"source: {self.source}, type: {self.type}\n"
        out += f"totals (Avg: {self.average}):\n"
        out += "\n".join(f"\t{val:g}: {prob:0.2%}" for val, prob in self.totals.items())
        out += f"\nnormalized_totals (Avg: {self.normalized_average}):\n"
        out += "\n".join(
            f"\t{val:g}: {prob:0.2%}" for val, prob in self.normalized_totals.items()
        )
        out += f"\nmin_totals:\n"
        out += "\n".join(
            f"\t{val:g}: {prob:0.2%}" for val, prob in self.min_totals.items()
        )
        return out


def print_results(results: List[Dict]):
    for res in results:
        print(f"{res['name']} (Avg: {res['average']:0.2f})")
        print("\n".join(f"\t{k:g}: {v:0.2%}" for k, v in res["totals"].items()))
        sources = res.get("by_source", [])
        for source in sources:
            print(f"\n\t{source['name']} (Avg: {source['average']:0.2g})")
            print(
                "\n".join(f"\t\t{k:g}: {v:0.2%}" for k, v in source["totals"].items())
            )


class DefaultSourceDict(dict):
    """Dictionary subclass that creates an empty SourceResult of a specified type
    for missing keys."""

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
    """Result of a statistical analysis performed on a set of States. A Result is just
    a container for one or more PDFs giving the probability across all the given States
    that a particular effect will occur with a particular value (or at all, in the case
    of boolean effects), possibly with a further breakdown by effect source.
    """

    name: str
    type: AnalysisType

    def __post_init__(self):  # Use post_init to initialize default source type
        self.sources = DefaultSourceDict(self.type)

    def __str__(self) -> str:
        out = f"name: {self.name}, type: {self.type}\n"
        if self.sources:
            out += "\n\n".join(f"{str(source)}" for source in self.sources.values())
        return out


# Basic statistical analyses that would be useful for HGB.
basic_list = [
    Analysis(
        name="MoS",
        description="Margin of Success",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.RuleEffects.MoS},
        show_if_missing=True,
    ),
    Analysis(
        name="Hit",
        description="Hit Rate",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.RuleEffects.Hit},
        show_if_missing=True,
    ),
    Analysis(
        name="Miss",
        description="Miss Rate (including Agile if present)",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.RuleEffects.Miss},
        split_by_source=True,
        show_if_missing=True,
    ),
    Analysis(
        name="Damage",
        description="Total damage dealt",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.AnalysisEffects.Damage},
        split_by_source=True,
        show_if_missing=True,
    ),
    Analysis(
        name="Damage Denied",
        description="Damage prevented by traits",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.AnalysisEffects.DamageDenied},
        split_by_source=True,
    ),
    Analysis(
        name="Overdamage",
        description="Damage dealt in excess of H/S",
        datatype=AnalysisType.RANGE,
        effect_params={"name": hgb.AnalysisEffects.Overdamage},
        split_by_source=True,
    ),
]

BASIC_ANALYSES = {a.name: a for a in basic_list}

# Analyses for status effects
status_list = [
    Analysis(
        name="Crippled",
        description="Defender crippled",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Crippled},
        split_by_source=True,
    ),
    Analysis(
        name="Destroyed",
        description="Defender destroyed",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Destroyed},
        split_by_source=True,
    ),
    Analysis(
        name="Haywired",
        description="Defender Haywired",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Haywired},
    ),
    Analysis(
        name="Corrosion",
        description="Defender has Corrosion",
        datatype=AnalysisType.BOOL,
        effect_params={"name": hgb.StatusEffects.Corrosion},
    ),
]

STATUS_ANALYSES = {a.name: a for a in status_list}

analyses = {**BASIC_ANALYSES, **STATUS_ANALYSES}  # Combine analyses into one list


def make_normals(totals: PDF, scale: Decimal = None) -> PDF:
    """Return scaled probabilties of non-zero values only. By default, they are scaled
    to sum to 1.0, but can be arbitrary scaled instead using the scale parameter.
    """
    normalized_totals = {val: prob for val, prob in totals.items() if val > 0}
    if not scale:
        total_probs = sum(normalized_totals.values())
        total_probs = Decimal(1) if total_probs == 0 else total_probs
        scale = Decimal(1) / total_probs
    return {val: prob * scale for val, prob in normalized_totals.items()}


def make_mins(totals: PDF) -> PDF:
    """Transform probability of each value in PDF into probability of seeing
    AT LEAST that value."""
    return {
        val: sum(prob for t_val, prob in totals.items() if t_val >= val)
        for val in totals.keys()
    }


def do_analysis(states: Iterable[State], analysis: Analysis) -> Result:
    """Analyze a collection of states for the supplied analysis type"""
    res = Result(analysis.name, analysis.datatype)  # Initialize result
    # Make a version of group_states() with the "states" parameter pre-filled for reuse
    group = partial(hgb.group_states, states)
    # Create PDF giving probabilities of each discrete value for the specific effect
    #   being analyzed, combined from all the given States.
    # Totals is the heart of the analysis.
    totals: PDF = group(hgb.effect_value_key(**analysis.effect_params))
    average = Decimal(sum(val * prob for val, prob in totals.items()))
    # Generate normalized probabilities (assuming the effect occurs, how likely is each
    #   discrete value > 0 to occur?)
    success_probs = sum(prob for val, prob in totals.items() if val > 0)
    success_probs = Decimal(1) if success_probs == 0 else success_probs
    scale = Decimal(1) / success_probs
    normalized_totals = make_normals(totals, scale=scale)
    normalized_average = Decimal(
        sum(val * prob for val, prob in normalized_totals.items())
    )

    # Gather current analysis results without regard for source yet.
    all_res = SourceResult(
        "All",
        analysis.datatype,
        totals,
        average,
        normalized_totals,
        normalized_average,
    )
    # Mins (probability AT LEAST x) don't make sense for boolean outcomes
    if analysis.datatype is AnalysisType.RANGE:
        all_res.min_totals = make_mins(totals)

    res.sources["All"] = all_res

    if analysis.split_by_source:
        # Get all of the individual Effects from EVERY state where that Effect occurs
        # itertools.chain is used to walk an iterable of iterables.
        effects = chain.from_iterable(
            state.get_effects(**analysis.effect_params) for state in states
        )
        # Make a set of all distinct sources for the found effects
        sources = {eff.source for eff in effects}

        for source in sources:
            # Rerun the analysis with an additional filter by source this time
            totals = group(
                hgb.effect_value_key(source=source, **analysis.effect_params)
            )
            average = sum(prob * val for prob, val in totals.items())
            # Normalize using total scale, not source scale
            # This preserves the relative probabilities between sources
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
            # Again, mins don't make sense with boolean effects
            if analysis.datatype is AnalysisType.RANGE:
                source_res.min_totals = make_mins(totals)
            res.sources[source] = source_res
    return res
