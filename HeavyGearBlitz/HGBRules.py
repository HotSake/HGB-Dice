from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import Decimal, getcontext
from enum import Enum, auto
from itertools import groupby, product
from operator import attrgetter
from typing import Any, Callable, FrozenSet, Hashable, Iterable, List, Mapping, Tuple

from diceGame.diceProbs import all_probs_high_die, expected
from diceGame.gameObjects import BaseEffect, Component, Entity, State

# Constants, Enums, etc.
getcontext().prec = 12

# Type alias for a probability distribution function
PDF = Mapping[Decimal, Decimal]

# The following Enums act as names for steps of the roll resolution process or game
# terms. They could just as easily be strings, but using Enums reduces the chance of
# referencing a nonexistent label.
class Roles(Enum):
    Attacker = auto()
    Defender = auto()


class Ranges(Enum):
    Optimal = auto()
    Suboptimal = auto()


class AttackMethods(Enum):
    Direct = auto()
    Indirect = auto()
    Melee = auto()


class Speed(Enum):
    Combat = auto()
    Top = auto()
    Braced = auto()
    Immobilized = auto()


class CoverAmount(Enum):
    Open = auto()
    Partial = auto()
    Full = auto()


class CoverStrength(Enum):
    Light = auto()
    Heavy = auto()
    Solid = auto()


class Facings(Enum):
    Front = auto()
    Rear = auto()


class ModelTypes(Enum):
    Gear = auto()
    Vehicle = auto()
    Infantry = auto()
    Aircraft = auto()


class RerollRules(Enum):
    Never = auto()
    BelowAverage = auto()


class RollTimeSteps(Enum):
    """All the steps from declaring attack to rolling dice."""

    INITIALIZE = auto()
    CHECK_COVER = auto()
    GATHER_DICE = auto()
    GATHER_RESULT_BONUSES = auto()
    GATHER_THRESHOLD_BONUSES = auto()
    ROLL_DICE = auto()
    ADD_SKILL = auto()


class ResolveTimeSteps(Enum):
    """All the steps of resolving the attack after dice have been rolled."""

    GATHER_MODEL_DATA = auto()
    APPLY_HIT_MISS = auto()
    CALC_ATTACK_DAMAGE = auto()
    MOD_ATTACK_DAMAGE = auto()
    APPLY_ATTACK_DAMAGE = auto()
    ADD_EXTRA_EFFECTS = auto()
    APPLY_EXTRA_DAMAGE = auto()
    END_OF_ROUND = auto()
    CLEANUP = auto()


class RuleEffects(Enum):
    ModDice = auto()
    ModResult = auto()
    ModThreshold = auto()
    RearAttack = auto()
    ElevatedVTOL = auto()
    MoS = auto()
    Hit = auto()
    Miss = auto()
    Armor = auto()
    Hull = auto()
    Structure = auto()
    Speed = auto()


class AttackEffects(Enum):
    WeaponDamage = auto()
    AttackDamage = auto()
    MarginalHit = auto()
    BonusDamage = auto()
    FireMission = auto()
    TD = auto()
    AntiInfantry = auto()
    Blast = auto()


class StatusEffects(Enum):
    FireDamage = auto()
    HaywireDamage = auto()
    CorrosionDamage = auto()
    Haywired = auto()
    Corrosion = auto()
    Crippled = auto()
    Destroyed = auto()


class AnalysisEffects(Enum):
    """Effects useful for analysis but not necessarily part of game rules."""

    Damage = auto()
    Overdamage = auto()
    DamageDenied = auto()


class DebugMsg(Enum):
    GetSkill = auto()


@dataclass(frozen=True)
class Effect(BaseEffect):
    """The Effect class represents any piece of game state that must be tracked.
    Aside from their probability, States are differentiated by their Effects.

    Effects only encode data, not behavior. All Effects have a value internally,
    by convention 0 or 1 for True or False if a Boolean Effect.

    Effect objects are immutable.
    """

    name: Enum
    source: str
    value: Decimal = Decimal(1)

    def __str__(self) -> str:
        return f"{self.name.name} ({self.source}): {self.value:0.2g}"


class HGBEntity(Entity):
    """The HGBEntity class represents an entity within the rules of Heavy Gear Blitz
    that is part of the attack resolution process, typically a model. Game rules that
    modify state are encapsulated in Components, which are then held by Entities.

    The role parameter identifies Attacker and Defender. The app currently uses a
    BaseRules entity to hold some basic rules that should execute before Attacker
    and Defender further modify state."""

    def __init__(self, role: Roles) -> None:
        self._role = role
        super().__init__()


# Utility functions


def make_model(
    model_components: FrozenSet(Component) = None,
    weapon_components: FrozenSet(Component) = None,
    role: Roles = None,
) -> HGBEntity:
    """Bundle model and weapon Components, if present, and give them to a new HGBEntity
    with a Role. Enforces uniqueness of Components by using sets."""
    model = HGBEntity(role=role)
    if weapon_components is None:
        weapon_components = set()
    if model_components is None:
        model_components = set()
    for trait in weapon_components.union(model_components):
        model.add_component(trait)
    return model


def get_rules() -> HGBEntity:
    """Instantiate a HGBEntity to hold basic rule and analysis components."""
    rules = HGBEntity(role=None)
    rules.add_component(AttackRuleComponent())
    rules.add_component(AnalysisComponent())
    return rules


def apply_damage(state: State, filter: Mapping[str, Any]) -> State:
    """Apply specific pending damage Effects to Hull and Structure. Filter is required
    to select which Effects to apply, because damage from different sources is applied
    at different times.
    """
    if state.get_effects(name=StatusEffects.Destroyed):
        return state

    effects = state.get_effects(**filter)  # Get only desired effects
    for eff in effects:
        damage = eff.value
        source = eff.source
        hull = state.sum_effects(name=RuleEffects.Hull)
        structure = state.sum_effects(name=RuleEffects.Structure)

        hull_damage = min(damage, hull)  # Apply damage up to Hull
        hull -= hull_damage
        damage -= hull_damage  # Remove Hull damage from total
        structure_damage = min(damage, structure)  # Apply damage up to Structure
        structure -= structure_damage
        damage -= structure_damage  # Remove Structure damage from total

        # Replace Hull and Structure Effects reflecting damage done
        state = state.remove_effects(name=RuleEffects.Hull).remove_effects(
            name=RuleEffects.Structure
        )
        new_hull = Effect(name=RuleEffects.Hull, source="Hull", value=hull)
        new_structure = Effect(
            name=RuleEffects.Structure, source="Structure", value=structure
        )
        state = state.add_effect(new_hull).add_effect(new_structure)

        # Mark Destroyed and remove Crippled if needed
        if structure == 0:
            destroyed = Effect(name=StatusEffects.Destroyed, source=source)
            state = state.add_effect(destroyed).remove_effects(
                name=StatusEffects.Crippled
            )
        # Mark Crippled if needed
        elif hull == 0 and not state.get_effects(name=StatusEffects.Crippled):
            crippled = Effect(name=StatusEffects.Crippled, source=source)
            state = state.add_effect(crippled)

        # Remaining damage is Overkill. Note it for analysis.
        if damage > 0:
            overdamage = Effect(
                name=AnalysisEffects.Overdamage,
                source=source,
                value=damage,
            )
            state = state.add_effect(overdamage)

    return state


"""Type alias for keyfunc. An EffectKey should be a function that takes a State
and yields a value based on its Effects, usually by calling State.sum_effects() 
or State.sum_by_filter().

The value returned by EffectKey() will then be used to sort or group together States in 
a larger collection."""
EffectKey = Callable[[State], Decimal]


def group_states(states: Iterable[State], key: EffectKey) -> PDF:
    """Combine the probabilities of States by some key function.
    Returns {value: sum_of_probs}.

    Example: you have a State with probability of 0.2 and a single Damage effect
        of value 1. You have a second State with a probability of 0.3 and a single
        Damage effect of value 1. If EffectKey is extracting Damage values, then
        group_states() should include an entry of {1: 0.5} showing the combined
        probability of 0.5 to have a Damage effect with value 1."""
    states = sorted(states, key=key)

    # itertools.groupby() takes an iterable and returns an iterator that groups
    # the elements of the input according the value returned when key() is called
    # on each element. Suppose key() is a function that returns the total value of any
    # Damage effects from its input State. Then groupby() might return:
    #
    #   [
    #       (0, (states[1], states[3])),
    #       (1, (states[2], states[0])),
    #       (2, (states[4], ))
    #   ]
    #
    # This is an iterable with 3 elements, and each element is a pair consisting of
    # a key value and another iterable. The sub-iterable contains every State where
    # key(State) == value.
    #
    # The returning dictionary comprehension takes the pairs from groupby() and turns
    # them into dict entries in the form of:
    #   {value : total probability of States where that value occurred}
    #
    # See map() and operator.attrgetter() documentation for more information.
    return {k: sum(map(attrgetter("prob"), v)) for k, v in groupby(states, key=key)}


def effect_value_key(**kwargs) -> EffectKey:
    """This higher order function makes a key function for extracting the sum of values
    of matching effects from a State."""

    def key(state: State) -> Decimal:
        return state.sum_effects(**kwargs)

    return key


@dataclass(frozen=True)
class Trait:
    """Definition for Model and Weapon Traits in Heavy Gear Blitz. Each Trait
    corresponds to a Component that implements its rules. Some parameters of the
    Component may be unchanging, and some may be variable. Traits also define valid
    model roles, and may require or exclude other Traits according to HGB rules.

    factory: Requied. Partial call to instantiate the implementing Component. Will be
        completed later by applying supplied params to the partial call.
    required_params: Optional. Required parameters for this Trait to complete
        instantiating the underlying Component, most often "value".
    valid_role: Optional. List of valid model roles to have this Trait.
    requires: Optional. List of names of other Traits required to have this Trait.
    excludes: Optional. List of names of other Traits blocked BY this Trait, either
        contradictory or redundant. NOTE: exclusions are not guaranteed to be mutual!
    """

    factory: Callable
    required_params: List[str] = field(default_factory=list)
    valid_role: List[str] = field(default_factory=lambda: ["att", "def"])
    requires: List[str] = field(default_factory=list)
    excludes: List[str] = field(default_factory=list)


# Component definitions


class DiceRuleComponent(Component):
    # Create base two dice when gathering dice.
    # Performs roll on ROLL_DICE, ensures minimum 1 die
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._add_two
        self._behaviors[RollTimeSteps.ROLL_DICE] = self._roll

    def _add_two(self: DiceRuleComponent, state: State) -> FrozenSet[State]:
        """Grant the two base dice for every skill roll"""
        eff = Effect(name=RuleEffects.ModDice, source="Base Rules", value=Decimal(2))
        return frozenset({state.add_effect(eff)})

    def _roll(self: DiceRuleComponent, state: State) -> FrozenSet[State]:
        """Tally dice and return multiple states for max result probs"""
        dice = state.sum_effects(name=RuleEffects.ModDice)
        dice = max(dice, 1)
        max_probs = all_probs_high_die(dice=int(dice), sides=6)

        # Resolve rerolling below average results
        if state.get_effects(name=RerollRules.BelowAverage):
            avg = expected(max_probs)
            # Outcomes to reroll
            rerolls = [roll for roll in max_probs if roll < avg]
            # Preserve non-rerolled outcomes
            new_probs = {
                roll: prob for roll, prob in max_probs.items() if roll not in rerolls
            }
            # Zero out probability of rerolls in new set of outcomes for now.
            new_probs.update({reroll: 0.0 for reroll in rerolls})

            for reroll in rerolls:
                for roll in max_probs:
                    # The chance of rerolling to each possible value is the SUM of each
                    # chance of rolling each original roll * the chance of rolling the
                    # new roll. Because the reroll probs are the same as the original
                    # probs, we can reuse the max_probs variable for the math.
                    new_probs[roll] = new_probs[roll] + (
                        max_probs[reroll] * max_probs[roll]
                    )
            max_probs = new_probs  # Finally we can alter max_probs before proceeding.

        # Create the base set of result States for each roll outcome
        results = set()
        for val, prob in max_probs.items():
            eff = Effect(
                name=RuleEffects.ModResult,
                source="Result Die",
                value=Decimal(val),
            )
            results.add(replace(state, prob=Decimal(prob) * state.prob).add_effect(eff))
        return frozenset(results)


class AttackRuleComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.APPLY_HIT_MISS] = self._hit_miss
        self._behaviors[ResolveTimeSteps.CALC_ATTACK_DAMAGE] = self._calc_attack_damage
        self._behaviors[ResolveTimeSteps.MOD_ATTACK_DAMAGE] = self._marginal_hit
        self._behaviors[
            ResolveTimeSteps.APPLY_ATTACK_DAMAGE
        ] = self._apply_attack_damage

    def _hit_miss(self: AttackRuleComponent, state: State) -> FrozenSet[State]:
        """Determine hit or miss based on MoS"""
        mos = state.sum_effects(name=RuleEffects.MoS)
        if mos >= 0:
            eff = Effect(name=RuleEffects.Hit, source="Base Rules", value=Decimal(1))
        else:
            eff = Effect(name=RuleEffects.Miss, source="Base Rules", value=Decimal(1))
        return frozenset({state.add_effect(eff)})

    def _calc_attack_damage(
        self: AttackRuleComponent, state: State
    ) -> FrozenSet[State]:
        """Calculate attack damage and add pending marginal hit if necessary"""
        if not state.get_effects(name=RuleEffects.Hit):
            return frozenset({state})

        damage = state.sum_effects(name=AttackEffects.WeaponDamage)
        armor = state.sum_effects(name=RuleEffects.Armor)
        mos = state.sum_effects(name=RuleEffects.MoS)
        attack_damage = damage + mos - armor
        if attack_damage == 0:
            marginal_hit = Effect(name=AttackEffects.MarginalHit, source="Base Rules")
            state = state.add_effect(marginal_hit)
        attack_damage_eff = Effect(
            name=AttackEffects.AttackDamage,
            source="Base Rules",
            value=Decimal(max(attack_damage, 0)),
        )
        state = state.add_effect(attack_damage_eff)
        return frozenset({state})

    def _marginal_hit(self, state: State) -> FrozenSet[State]:
        """Add probabilistic marginal hit damage if not removed yet."""
        if not state.get_effects(name=AttackEffects.MarginalHit):
            return frozenset({state})

        state = state.remove_effects(name=AttackEffects.MarginalHit)
        no_hit = replace(state, prob=state.prob * Decimal(0.5))
        eff = Effect(
            name=AttackEffects.AttackDamage, source="Marginal Hit", value=Decimal(1)
        )
        hit = replace(no_hit).add_effect(eff)
        return frozenset({no_hit, hit})

    def _apply_attack_damage(self, state: State) -> FrozenSet[State]:
        """Reduce Hull and Structure by attack damage"""
        if state.get_effects(name=RuleEffects.Miss):
            return frozenset({state})

        # For analysis purposes, we treat AP as bonus damage above base damage.
        damage_order = ["Base Rules", "Marginal Hit", "AP"]
        for source in damage_order:
            state = apply_damage(
                state=state,
                filter={"name": AttackEffects.AttackDamage, "source": source},
            )

        return frozenset({state})


class AnalysisComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.CLEANUP] = self._cleanup

    def _cleanup(self, state: State) -> FrozenSet[State]:
        """Cleanup Effects to smooth analysis"""
        get_all_damage = lambda eff: eff.name in (
            AttackEffects.AttackDamage,
            AttackEffects.BonusDamage,
        )
        # Unify damage effects, preserving source
        for eff in state.get_by_filter(get_all_damage):
            damage = eff.value
            source = eff.source
            state = state.add_effect(
                Effect(
                    name=AnalysisEffects.Damage,
                    source=source,
                    value=damage,
                )
            )
        state = state.remove_by_filter(get_all_damage)
        # TODO: Remove unneeded Effects for analysis if slow
        return frozenset({state})


class DiceBonusComponent(Component):
    """A generic dice bonus from whatever source. Can be negative for penalties."""

    def __init__(self, source: str, value: int) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._add_dice
        self._source = source
        self._value = value

    def _add_dice(self: DiceBonusComponent, state: State) -> FrozenSet[State]:
        eff = Effect(name=RuleEffects.ModDice, source=self._source, value=self._value)
        return frozenset({state.add_effect(eff)})


class ResultBonusComponent(Component):
    """A generic result bonus from whatever source. Can be negative for penalties."""

    def __init__(self, source: str, value: int) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_RESULT_BONUSES] = self._add_result
        self._source = source
        self._value = value

    def _add_result(self: ResultBonusComponent, state: State) -> FrozenSet[State]:
        eff = Effect(name=RuleEffects.ModResult, source=self._source, value=self._value)
        return frozenset({state.add_effect(eff)})


class ThresholdBonusComponent(Component):
    """A generic skill bonus from whatever source. Can be negative for penalties."""

    def __init__(self, source: str, value: int) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_THRESHOLD_BONUSES] = self._add_threshold
        self._source = source
        self._value = value

    def _add_threshold(self: ThresholdBonusComponent, state: State) -> FrozenSet[State]:
        eff = Effect(
            name=RuleEffects.ModThreshold, source=self._source, value=self._value
        )
        return frozenset({state.add_effect(eff)})


class BasicTraitComponent(Component):
    """For setting data Effects with no extra behavior. If a Trait may trigger other
    rules but doesn't need to act on its own logic, make it an instance of this."""

    def __init__(
        self, effect_name: Enum, source: str, value: Decimal = Decimal(1)
    ) -> None:
        super().__init__()
        self._effect_name = effect_name
        self._source = source
        self._value = Decimal(value)
        self._behaviors[RollTimeSteps.INITIALIZE] = self._add_trait
        self._behaviors[ResolveTimeSteps.GATHER_MODEL_DATA] = self._add_trait

    def _add_trait(self, state: State) -> FrozenSet[State]:
        eff = Effect(name=self._effect_name, source=self._source, value=self._value)
        return frozenset({state.add_effect(eff)})


# May eventually rename Scenario to Interaction and add a higher level Scenario class
# to handle Interactions with multiple defenders
class Scenario:
    def __init__(
        self: Scenario,
        attacker: HGBEntity(role=Roles.Attacker),
        defender: HGBEntity(role=Roles.Defender),
        base_rules: HGBEntity = None,
        start_states: FrozenSet[State] = None,
    ) -> None:
        self._start_states = start_states
        self._attacker = attacker
        self._defender = defender
        self._attacker.add_component(DiceRuleComponent())
        self._defender.add_component(DiceRuleComponent())
        if base_rules is None:
            base_rules = get_rules()
        self._base_rules = base_rules
        if start_states is None:
            start_states = frozenset({State(prob=Decimal(1))})
        self._start_states = start_states

    def pass_states(
        self: Scenario, entity: HGBEntity, msg: Hashable, states: FrozenSet[State]
    ) -> FrozenSet[State]:
        """Pass the current message and each current State to the given Entity and
        collect the resulting States. This is where the Entity's Components get a
        chance to execute their Behaviors to modify or split a State."""
        if msg not in entity.valid_messages():
            return states
        results = []
        working = list(states)
        while working:
            results.extend(entity.pass_message(msg=msg, state=working.pop()))

        return frozenset(results)

    def get_rolls(self) -> Tuple[FrozenSet[State], FrozenSet[State]]:
        """Run the initial time steps of the attack resolution process to get
        attacker and defender roll results."""
        init_steps = [
            RollTimeSteps.INITIALIZE,
            RollTimeSteps.CHECK_COVER,
        ]
        pre_roll = [
            RollTimeSteps.GATHER_DICE,
            RollTimeSteps.GATHER_RESULT_BONUSES,
            RollTimeSteps.GATHER_THRESHOLD_BONUSES,
        ]
        start_states = self._start_states
        for step in init_steps:
            for entity in [self._base_rules, self._attacker, self._defender]:
                start_states = self.pass_states(
                    entity=entity,
                    msg=step,
                    states=start_states,
                )
        att_rolls = self.pass_states(
            entity=self._attacker, msg=DebugMsg.GetSkill, states=start_states
        )
        def_rolls = self.pass_states(
            entity=self._defender, msg=DebugMsg.GetSkill, states=start_states
        )

        for step in pre_roll:
            att_rolls = self.pass_states(
                entity=self._base_rules, msg=step, states=att_rolls
            )
            att_rolls = self.pass_states(
                entity=self._attacker, msg=step, states=att_rolls
            )
            def_rolls = self.pass_states(
                entity=self._base_rules, msg=step, states=def_rolls
            )
            def_rolls = self.pass_states(
                entity=self._defender, msg=step, states=def_rolls
            )
        return (att_rolls, def_rolls)

    def describe_rolls(self) -> Mapping[str, str]:
        """Get skill, dice pool, result bonus, and TN for attacker/defender rolls
        in string format."""
        att_rolls, def_rolls = self.get_rolls()
        # Just get one possible roll each from Attacker and Defender.
        for att_state in att_rolls:
            break
        for def_state in def_rolls:
            break
        results = []
        # Extract skill, dice pool, result bonus, and TN for attacker and defender.
        for state in (att_state, def_state):
            skill = state.sum_effects(name=DebugMsg.GetSkill)
            threshold_mod = state.sum_effects(name=RuleEffects.ModThreshold)
            dice = max(state.sum_effects(name=RuleEffects.ModDice), 1)
            result_mod = state.sum_effects(name=RuleEffects.ModResult)
            results.append(
                " ".join(
                    [
                        f"Skill {skill:g}",
                        f"{int(dice):g}d6",
                        f"{int(result_mod):+g}R",
                        f"TN: {int(threshold_mod):g}",
                    ]
                )
            )
        return {"attacker": results[0], "defender": results[1]}

    def evaluate(self) -> FrozenSet[State]:
        """Perform the complete attack resolution process for this scenario."""
        att_rolls, def_rolls = self.get_rolls()
        entities = [self._base_rules, self._attacker, self._defender]

        # Apply base rules, then model specific mods for Attacker and Defender.
        for step in [RollTimeSteps.ROLL_DICE, RollTimeSteps.ADD_SKILL]:
            att_rolls = self.pass_states(
                entity=self._base_rules, msg=step, states=att_rolls
            )
            att_rolls = self.pass_states(
                entity=self._attacker, msg=step, states=att_rolls
            )
            def_rolls = self.pass_states(
                entity=self._base_rules, msg=step, states=def_rolls
            )
            def_rolls = self.pass_states(
                entity=self._defender, msg=step, states=def_rolls
            )

        # Convert pairs of roll results to MoS states
        mos_probs = defaultdict(Decimal)
        # Compare each possible attacker roll to each possible defender roll
        for att_state, def_state in product(att_rolls, def_rolls):
            att_roll = att_state.sum_effects(name=RuleEffects.ModResult)
            def_roll = def_state.sum_effects(name=RuleEffects.ModResult)
            mos = att_roll - def_roll
            mos_probs[mos] = mos_probs[mos] + (att_state.prob * def_state.prob)

        mos_states = set()
        for mos, prob in mos_probs.items():
            eff = Effect(name=RuleEffects.MoS, source="Base Rules", value=mos)
            mos_states.add(State(prob=prob, effects=frozenset({eff})))
        mos_states = frozenset(mos_states)

        # Evalute results for each unique MoS
        for step in ResolveTimeSteps:
            for entity in entities:  # Base rules, Attacker, then Defender
                # Remember, mos_states is an immutable frozenset. It is recreated with
                # or without changes during each entity's turn in each step.
                mos_states = self.pass_states(
                    entity=entity, msg=step, states=mos_states
                )

        return mos_states


if __name__ == "__main__":
    pass
