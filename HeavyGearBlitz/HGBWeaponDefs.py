from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from functools import partial
from typing import FrozenSet, Mapping, Sequence, Union

from diceGame.diceProbs import all_probs_threshold
from diceGame.gameObjects import Component, State
from .HGBRules import (
    AttackEffects,
    AttackMethods,
    BasicTraitComponent,
    CoverAmount,
    CoverStrength,
    DiceBonusComponent,
    Effect,
    ModelTypes,
    Ranges,
    ResolveTimeSteps,
    ResultBonusComponent,
    RollTimeSteps,
    RuleEffects,
    StatusEffects,
    Trait,
    apply_damage,
)


class APComponent(Component):
    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = value
        self._behaviors[ResolveTimeSteps.CALC_ATTACK_DAMAGE] = self._ap

    def _ap(self, state: State) -> FrozenSet[State]:
        """Add AP damage before MOD_ATTACK_DAMAGE step to preempt Marginal Hit rule"""
        if state.get_effects(name=RuleEffects.Miss):
            return frozenset({state})

        state = state.remove_effects(name=AttackEffects.MarginalHit)
        attack_damage = state.sum_effects(name=AttackEffects.AttackDamage)
        mos = state.sum_effects(name=RuleEffects.MoS)
        ap_damage = min(self._value, mos)
        if ap_damage == Decimal(0):
            ap_damage = Decimal(1)
        if ap_damage > attack_damage:
            ap_damage -= attack_damage
            eff = Effect(name=AttackEffects.AttackDamage, source="AP", value=ap_damage)
            state = state.add_effect(eff)

        return frozenset({state})


class AntiAirComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._AA

    def _AA(self, state: State) -> FrozenSet[State]:
        if state.get_effects(name=ModelTypes.Aircraft):
            eff = Effect(name=RuleEffects.ModDice, source="AA", value=1)
            state = state.add_effect(eff)
        return frozenset({state})


class BlastComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.CHECK_COVER] = self._blast

    def _blast(self, state: State) -> FrozenSet[State]:
        if state.get_effects(name=AttackMethods.Indirect) and state.get_effects(
            name=CoverAmount.Partial
        ):
            state = state.remove_by_filter(
                lambda e: e.name in [CoverAmount.Partial] + list(CoverStrength)
            )
        return frozenset({state})


class BrawlComponent(Component):
    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = Decimal(value)
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._brawl

    def _brawl(self, state: State) -> FrozenSet[State]:
        if not state.get_effects(name=AttackMethods.Melee):
            return frozenset({state})

        eff = Effect(name=RuleEffects.ModDice, source="Weapon Brawl", value=self._value)
        return frozenset({state.add_effect(eff)})


class HaywireComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._add_haywire
        self._behaviors[
            ResolveTimeSteps.APPLY_EXTRA_DAMAGE
        ] = self._apply_haywire_damage

    def _add_haywire(self, state: State) -> FrozenSet(State):
        if state.get_effects(name=RuleEffects.Miss) or state.get_effects(
            name=StatusEffects.Destroyed
        ):
            return frozenset({state})

        status_eff = Effect(name=StatusEffects.Haywired, source="Haywire")
        damage_eff = Effect(
            name=StatusEffects.HaywireDamage, source="Haywire", value=Decimal(1)
        )
        state = state.add_effect(status_eff).add_effect(damage_eff)

        return frozenset({state})

    def _apply_haywire_damage(self, state: State) -> FrozenSet(State):
        """Apply pending haywire damage if defender has not removed effect yet"""
        haywire = state.sum_effects(name=StatusEffects.HaywireDamage)
        dmg_probs = all_probs_threshold(dice=int(haywire), sides=6, val=4)
        state = state.remove_effects(name=StatusEffects.HaywireDamage)
        results = set()
        for val, prob in dmg_probs.items():
            if val > 0:
                eff = Effect(
                    name=AttackEffects.BonusDamage,
                    source="Haywire",
                    value=Decimal(val),
                )
                new_state = apply_damage(
                    state=replace(state, prob=Decimal(prob) * state.prob).add_effect(
                        eff
                    ),
                    filter={"name": eff.name, "source": eff.source},
                )
                results.add(new_state)
            else:
                results.add(replace(state, prob=Decimal(prob) * state.prob))
        return frozenset(results)


class FireComponent(Component):
    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = value
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._add_fire
        self._behaviors[ResolveTimeSteps.APPLY_EXTRA_DAMAGE] = self._apply_fire_damage

    def _add_fire(self, state: State) -> FrozenSet(State):
        if state.get_effects(name=RuleEffects.Miss) or state.get_effects(
            name=StatusEffects.Destroyed
        ):
            return frozenset({state})

        damage_eff = Effect(
            name=StatusEffects.FireDamage, source="Fire", value=self._value
        )
        state = state.add_effect(damage_eff)

        return frozenset({state})

    def _apply_fire_damage(self, state: State) -> FrozenSet(State):
        """Apply pending fire damage if defender has not removed effect yet"""
        fire = state.sum_effects(name=StatusEffects.FireDamage)
        dmg_probs = all_probs_threshold(dice=int(fire), sides=6, val=4)
        state = state.remove_effects(name=StatusEffects.FireDamage)
        results = set()
        for val, prob in dmg_probs.items():
            if val > 0:
                eff = Effect(
                    name=AttackEffects.BonusDamage,
                    source="Fire",
                    value=Decimal(val),
                )
                new_state = apply_damage(
                    state=replace(state, prob=Decimal(prob) * state.prob).add_effect(
                        eff
                    ),
                    filter={"name": eff.name, "source": eff.source},
                )
                results.add(new_state)
            else:
                results.add(replace(state, prob=Decimal(prob) * state.prob))
        return frozenset(results)


class CorrosionComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._add_corrosion
        self._behaviors[ResolveTimeSteps.END_OF_ROUND] = self._apply_corrosion_damage

    def _add_corrosion(self, state: State) -> FrozenSet(State):
        if state.get_effects(name=RuleEffects.Miss) or state.get_effects(
            name=StatusEffects.Destroyed
        ):
            return frozenset({state})

        status_eff = Effect(
            name=StatusEffects.Corrosion, source="Corrosion", value=Decimal(1)
        )
        damage_eff = Effect(
            name=StatusEffects.CorrosionDamage, source="Corrosion", value=Decimal(1)
        )
        state = state.add_effect(status_eff).add_effect(damage_eff)

        return frozenset({state})

    def _apply_corrosion_damage(self, state: State) -> FrozenSet(State):
        """Apply pending corrosion damage if defender has not removed effect yet"""
        corrosion = state.sum_effects(name=StatusEffects.CorrosionDamage)
        dmg_probs = all_probs_threshold(dice=int(corrosion), sides=6, val=4)
        state = state.remove_effects(name=StatusEffects.CorrosionDamage)
        results = set()
        for val, prob in dmg_probs.items():
            if val > 0:
                eff = Effect(
                    name=AttackEffects.BonusDamage,
                    source="Corrosion",
                    value=Decimal(val),
                )
                new_state = apply_damage(
                    state=replace(state, prob=Decimal(prob) * state.prob).add_effect(
                        eff
                    ),
                    filter={"name": eff.name, "source": eff.source},
                )
                results.add(new_state)
            else:
                results.add(replace(state, prob=Decimal(prob) * state.prob))
        return frozenset(results)


class AdvancedComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_RESULT_BONUSES] = self._add_result

    def _add_result(self, state: State) -> FrozenSet(State):
        """Add +1 result only if at Optimal range"""
        if state.get_effects(name=Ranges.Optimal):
            eff = Effect(name=RuleEffects.ModResult, source="Advanced", value=1)
            state = state.add_effect(effect=eff)
        return frozenset({state})


class GuidedComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._dice_mod

    def _dice_mod(self, state: State) -> FrozenSet[State]:
        """Add dice mod for guided indirect attack, if TD present"""
        if state.get_effects(name=AttackEffects.FireMission) and state.get_effects(
            name=AttackEffects.TD
        ):
            eff = Effect(name=RuleEffects.ModDice, source="Guided", value=1)
            state = state.add_effect(eff)
        return frozenset({state})


class RangeComponent(Component):
    def __init__(self, range: Ranges) -> None:
        super().__init__()
        self._range = range
        self._behaviors[RollTimeSteps.INITIALIZE] = self._set_range
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._dice_mod

    def _set_range(self, state: State) -> FrozenSet[State]:
        """Add range effect for other components"""
        eff = Effect(name=self._range, source="Range")
        return frozenset({state.add_effect(eff)})

    def _dice_mod(self, state: State) -> FrozenSet[State]:
        """Add dice mod for range"""
        if self._range == Ranges.Suboptimal and not state.get_effects(
            name=AttackMethods.Melee
        ):
            eff = Effect(
                name=RuleEffects.ModDice, source=self._range.name, value=Decimal(-1)
            )
            state = state.add_effect(eff)

        return frozenset({state})


class MethodComponent(Component):
    def __init__(self, method: AttackMethods) -> None:
        super().__init__()
        self._method = method
        self._behaviors[RollTimeSteps.INITIALIZE] = self._set_method
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._dice_mod

    def _set_method(self, state: State) -> FrozenSet[State]:
        """Add attack method effect for other components"""
        eff = Effect(name=self._method, source="Attack Method")
        return frozenset({state.add_effect(eff)})

    def _dice_mod(self, state: State) -> FrozenSet[State]:
        """Add dice mod for attack method"""
        mod = 0
        if self._method == AttackMethods.Indirect:
            mod -= 1
            if state.get_effects(name=AttackEffects.FireMission):
                mod += 1
        eff = Effect(name=RuleEffects.ModDice, source=self._method.name, value=mod)

        return frozenset({state.add_effect(eff)})


WEAPON_TRAIT_DEFS = {
    "Damage": Trait(
        partial(BasicTraitComponent, effect_name=AttackEffects.WeaponDamage),
        required_params=["value"],
        valid_role=[],
    ),
    "Range": Trait(
        partial(RangeComponent),
        required_params=["range"],
        valid_role=[],
    ),
    "Advanced": Trait(
        partial(AdvancedComponent),
    ),
    "AESecondary": Trait(
        partial(DiceBonusComponent, source="AE Secondary Target", value=-1),
        valid_role=[],
    ),
    "AntiAir": Trait(
        partial(AntiAirComponent),
    ),
    "Precise": Trait(
        partial(ResultBonusComponent, source="Precise", value=1),
    ),
    "AntiInfantry": Trait(
        partial(
            BasicTraitComponent,
            effect_name=AttackEffects.AntiInfantry,
            source="AntiInfantry",
        ),
    ),
    "AP": Trait(
        partial(APComponent),
        required_params=["value"],
    ),
    "Blast": Trait(partial(BlastComponent)),
    "FireMission": Trait(
        partial(
            BasicTraitComponent,
            effect_name=AttackEffects.FireMission,
            source="Fire Mission",
        ),
        valid_role=[],
    ),
    "Burst": Trait(
        partial(DiceBonusComponent, source="Burst"),
        required_params=["value"],
    ),
    "Focus": Trait(
        partial(DiceBonusComponent, source="Focus", value=1),
        valid_role=[],
    ),
    "Frag": Trait(
        partial(DiceBonusComponent, source="Frag", value=2),
    ),
    "Splitting": Trait(
        partial(DiceBonusComponent, source="Split", value=-1),
    ),
    "Link": Trait(
        partial(DiceBonusComponent, source="Link", value=1),
    ),
    "Brawl": Trait(
        partial(BrawlComponent),
        required_params=["value"],
    ),
    "Guided": Trait(
        partial(GuidedComponent),
    ),
    "Method": Trait(
        partial(MethodComponent),
        required_params=["method"],
        valid_role=[],
    ),
    "Haywire": Trait(
        partial(HaywireComponent),
    ),
    "Fire": Trait(
        partial(FireComponent),
        required_params=["value"],
    ),
    "Corrosion": Trait(
        partial(CorrosionComponent),
    ),
    "TD": Trait(
        partial(BasicTraitComponent, effect_name=AttackEffects.TD, source="TD"),
        valid_role=[],
    ),
}


# MELEE_ONLY_TRAITS = ["Brawl"]
# RANGED_ONLY_TRAITS = ["Guided"]


def weapon_trait_to_component(name: str, **kwargs) -> Component:
    # print(f"{name}: {kwargs}")
    trait_factory = WEAPON_TRAIT_DEFS[name].factory
    missing = set(WEAPON_TRAIT_DEFS[name].required_params).difference(
        set(kwargs.keys())
    )
    if missing:
        print(f"Attempted to make {name} trait without required params: {missing}")
    return trait_factory(**kwargs)


def make_weapon_components(
    weapon_params: Sequence[Mapping[str, Union[str, Decimal]]]
) -> frozenset(Component):
    return frozenset(weapon_trait_to_component(**params) for params in weapon_params)


if __name__ == "__main__":
    pass
