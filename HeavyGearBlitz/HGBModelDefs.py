from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from functools import partial
from typing import FrozenSet, Mapping, Sequence, Union

from diceGame.diceProbs import all_probs_threshold
from diceGame.gameObjects import Component, State

from .HGBRules import (
    AnalysisEffects,
    AttackEffects,
    AttackMethods,
    BasicTraitComponent,
    CoverAmount,
    DebugMsg,
    DiceBonusComponent,
    Effect,
    Facings,
    ModelTypes,
    RerollRules,
    ResolveTimeSteps,
    ResultBonusComponent,
    Roles,
    RollTimeSteps,
    RuleEffects,
    Speed,
    StatusEffects,
    ThresholdBonusComponent,
    Trait,
    apply_damage,
)


class AgileComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.APPLY_HIT_MISS] = self._agile

    def _agile(self, state: State) -> FrozenSet[State]:
        mos = state.sum_effects(name=RuleEffects.MoS)
        if mos == 0:
            eff = Effect(name=RuleEffects.Miss, source="Agile", value=Decimal(1))
            state = state.remove_effects(name=RuleEffects.Hit).add_effect(eff)
        return frozenset({state})


class BrawlComponent(Component):
    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = Decimal(value)
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._brawl

    def _brawl(self, state: State) -> FrozenSet[State]:
        if not state.get_effects(name=AttackMethods.Melee):
            return frozenset({state})

        eff = Effect(name=RuleEffects.ModDice, source="Model Brawl", value=self._value)
        return frozenset({state.add_effect(eff)})


class CoverComponent(Component):
    def __init__(self, amount: CoverAmount) -> None:
        super().__init__()
        self._amount = amount
        self._behaviors[RollTimeSteps.INITIALIZE] = self._init_cover
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._cover

    def _init_cover(self, state: State):
        eff = Effect(name=self._amount, source="Cover")
        return frozenset({state.add_effect(effect=eff)})

    def _cover(self, state: State) -> FrozenSet[State]:
        eff = None
        if state.get_effects(name=CoverAmount.Partial) or state.get_effects(
            name=CoverAmount.Full
        ):
            eff = Effect(name=RuleEffects.ModDice, source="Cover", value=1)

        return frozenset({state.add_effect(eff)})


class FacingComponent(Component):
    def __init__(self, facing: Facings) -> None:
        super().__init__()
        self._facing = facing
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._facing_dice

    def _facing_dice(self, state: State) -> FrozenSet[State]:
        """No facing bonus for Infantry, 2d6 for Vehicle, 1d6 otherwise"""
        if self._facing != Facings.Rear or state.get_effects(name=ModelTypes.Infantry):
            return frozenset({state})

        if state.get_effects(name=ModelTypes.Vehicle):
            bonus = Decimal(2)
        else:
            bonus = Decimal(1)
        eff = Effect(
            name=RuleEffects.ModDice, source=f"Facing {self._facing.name}", value=bonus
        )
        return frozenset({state.add_effect(eff)})


class ElevatedVTOLComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.INITIALIZE] = self._set_type
        self._behaviors[ResolveTimeSteps.GATHER_MODEL_DATA] = self._set_type
        self._behaviors[RollTimeSteps.GATHER_THRESHOLD_BONUSES] = self._add_elevated

    def _set_type(self, state: State) -> FrozenSet(State):
        """Flag defender type as aircraft in addition to existing type."""
        if self._parent._role == Roles.Defender:
            air_type = Effect(name=ModelTypes.Aircraft, source="Elevated VTOL")
            return frozenset({state.add_effect(effect=air_type)})
        else:
            return frozenset({state})

    def _add_elevated(self, state: State) -> FrozenSet(State):
        """Flag attacker as Elevated."""
        if self._parent._role == Roles.Attacker:
            eff = Effect(
                name=RuleEffects.ModThreshold, source="Elevated VTOL", value=-1
            )
            return frozenset({state.add_effect(eff)})
        else:
            return frozenset({state})


class FieldArmorComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.MOD_ATTACK_DAMAGE] = self._reduce_damage

    def _reduce_damage(self, state: State) -> FrozenSet[State]:
        """Reduce damage by 1, to a minimum of 1.
        Reduce AP first for analysis purposes."""
        if state.get_effects(name=RuleEffects.Miss):
            return frozenset({state})

        ap_damage = state.sum_effects(
            name=AttackEffects.AttackDamage,
            source="AP",
        )
        attack_damage = state.sum_by_filter(
            lambda e: e.name == AttackEffects.AttackDamage and e.source != "AP"
        )

        if attack_damage + ap_damage <= 1:
            return frozenset({state})

        eff = Effect(
            name=AnalysisEffects.DamageDenied, source="Field Armor", value=Decimal(1)
        )
        state = state.add_effect(eff)

        if ap_damage:
            state = state.remove_effects(name=AttackEffects.AttackDamage, source="AP")
            if ap_damage > 1:
                new_ap = Effect(
                    name=AttackEffects.AttackDamage,
                    source="AP",
                    value=Decimal(ap_damage - 1),
                )
                state = state.add_effect(new_ap)
        else:
            state = state.remove_effects(
                name=AttackEffects.AttackDamage, source="Base Rules"
            )
            new_attack = Effect(
                name=AttackEffects.AttackDamage,
                source="Base Rules",
                value=Decimal(attack_damage - 1),
            )
            state = state.add_effect(new_attack)
        return frozenset({state})


class InfantryComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.INITIALIZE] = self._set_type
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._infantry_cover
        self._behaviors[ResolveTimeSteps.GATHER_MODEL_DATA] = self._set_type
        self._behaviors[ResolveTimeSteps.CALC_ATTACK_DAMAGE] = self._cap_damage

    def _set_type(self, state: State) -> FrozenSet(State):
        """Flag model type as Infantry"""
        eff = Effect(name=ModelTypes.Infantry, source="Type")
        return frozenset({state.add_effect(effect=eff)})

    def _infantry_cover(self, state: State) -> FrozenSet(State):
        """Add 1d6 to cover bonus for Infantry"""
        if state.get_by_filter(
            lambda e: e.name in (CoverAmount.Partial, CoverAmount.Full)
        ):
            eff = Effect(
                name=RuleEffects.ModDice, source="Infantry Cover", value=Decimal(1)
            )
            state = state.add_effect(eff)
        return frozenset({state})

    def _cap_damage(self, state: State) -> FrozenSet(State):
        """Cap attack damage at 2 against non-AI weapons.
        Reduce AP first for analysis purposes."""
        if state.get_effects(name=RuleEffects.Miss) or state.get_effects(
            name=AttackEffects.AntiInfantry
        ):
            return frozenset({state})

        attack_damage = state.sum_effects(
            name=AttackEffects.AttackDamage,
            source="Base Rules",
        )
        ap_damage = state.sum_effects(
            name=AttackEffects.AttackDamage,
            source="AP",
        )

        drop = Decimal(attack_damage + ap_damage - 2)

        if drop <= 0:
            return frozenset({state})

        eff = Effect(name=AnalysisEffects.DamageDenied, source="Infantry", value=drop)
        state = state.add_effect(eff)

        ap_drop = min(drop, ap_damage)
        drop -= ap_drop

        if ap_drop:
            state = state.remove_effects(name=AttackEffects.AttackDamage, source="AP")
            if ap_damage - ap_drop:
                new_ap = Effect(
                    name=AttackEffects.AttackDamage,
                    source="AP",
                    value=ap_damage - ap_drop,
                )
                state = state.add_effect(new_ap)
        if drop:
            state = state.remove_effects(
                name=AttackEffects.AttackDamage, source="Base Rules"
            )
            new_attack = Effect(
                name=AttackEffects.AttackDamage,
                source="Base Rules",
                value=attack_damage - drop,
            )
            state = state.add_effect(new_attack)
        return frozenset({state})


class LumberingComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._lumbering

    def _lumbering(self, state: State) -> FrozenSet(State):
        """Cancel top speed bonus to defense"""
        top_defender = state.get_effects(name=Speed.Top, source=Roles.Defender)
        if top_defender:
            eff = Effect(
                name=RuleEffects.ModDice, source="Lumbering", value=Decimal(-1)
            )
            state = state.add_effect(eff)

        return frozenset({state})


class RerollComponent(Component):
    def __init__(self, rule: RerollRules) -> None:
        super().__init__()
        self._rule = rule
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._reroll

    def _reroll(self, state: State) -> FrozenSet[State]:
        eff = Effect(name=self._rule, source="Reroll")
        return frozenset({state.add_effect(eff)})


class ResistCorrosionComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._resist

    def _resist(self, state: State) -> FrozenSet[State]:
        """Remove pending damage effect before it can be rolled"""
        if not state.get_effects(name=StatusEffects.CorrosionDamage):
            return frozenset({state})

        state = state.remove_effects(name=StatusEffects.CorrosionDamage)
        eff = Effect(
            name=AnalysisEffects.DamageDenied, source="Resist Corrosion", value=0.5
        )

        return frozenset({state.add_effect(eff)})


class ResistFireComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._resist

    def _resist(self, state: State) -> FrozenSet[State]:
        """Remove pending damage effect before it can be rolled"""
        if not state.get_effects(name=StatusEffects.FireDamage):
            return frozenset({state})

        health = state.sum_effects(name=RuleEffects.Hull) + state.sum_effects(
            name=RuleEffects.Structure
        )
        fire = state.sum_effects(name=StatusEffects.FireDamage)
        fire_probs = all_probs_threshold(dice=int(fire), sides=6, val=4)
        avg_damage = sum(
            Decimal(prob) * min(Decimal(dmg), health)
            for dmg, prob in fire_probs.items()
        )
        state = state.remove_effects(name=StatusEffects.FireDamage)
        eff = Effect(
            name=AnalysisEffects.DamageDenied, source="Resist Fire", value=avg_damage
        )

        return frozenset({state.add_effect(eff)})


class ResistHaywireComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._resist

    def _resist(self, state: State) -> FrozenSet[State]:
        """Remove pending damage effect before it can be rolled"""
        if not state.get_effects(name=StatusEffects.HaywireDamage):
            return frozenset({state})

        state = state.remove_effects(name=StatusEffects.HaywireDamage)
        eff = Effect(
            name=AnalysisEffects.DamageDenied, source="Resist Haywire", value=0.5
        )

        return frozenset({state.add_effect(eff)})


class SpeedComponent(Component):
    def __init__(self, speed: Speed) -> None:
        super().__init__()
        self._speed: Speed = speed
        self._model: Roles = None
        self._behaviors[RollTimeSteps.INITIALIZE] = self._set_speed
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._speed_mod

    def _set_speed(self, state: State):
        self._model = self._parent._role
        eff = Effect(name=self._speed, source=self._model)
        return frozenset({state.add_effect(effect=eff)})

    def _speed_mod(self, state: State):
        if self._model == Roles.Attacker:
            if self._speed in {Speed.Top, Speed.Immobilized}:
                mod = Decimal(-1)
            elif self._speed == Speed.Braced:
                mod = Decimal(1)
            else:
                return frozenset({state})
        elif self._model == Roles.Defender:
            if self._speed in {Speed.Braced, Speed.Immobilized}:
                mod = Decimal(-1)
            elif self._speed == Speed.Top:
                mod = Decimal(1)
            else:
                return frozenset({state})
        eff = Effect(
            name=RuleEffects.ModDice,
            source=self._model.name + " " + self._speed.name + " Speed",
            value=mod,
        )
        return frozenset({state.add_effect(eff)})


class SkillComponent(Component):
    # activates on GATHER_RESULT_BONUSES
    # returns multiple states for different skill bonuses
    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = value
        self._behaviors[DebugMsg.GetSkill] = self._pass_skill
        self._behaviors[RollTimeSteps.GATHER_THRESHOLD_BONUSES] = self._set_threshold
        self._behaviors[RollTimeSteps.ADD_SKILL] = self._add_skill_bonus

    def _pass_skill(self, state: State) -> FrozenSet[State]:
        eff = Effect(name=DebugMsg.GetSkill, source="Skill", value=self._value)
        return frozenset({state.add_effect(eff)})

    def _set_threshold(self, state: State) -> FrozenSet[State]:
        eff = Effect(name=RuleEffects.ModThreshold, source="Skill", value=self._value)
        return frozenset({state.add_effect(eff)})

    def _add_skill_bonus(self: SkillComponent, state: State) -> FrozenSet[State]:
        dice = state.sum_effects(name=RuleEffects.ModDice) - 1
        result_die = state.sum_effects(name=RuleEffects.ModResult, source="Result Die")
        threshold = state.sum_effects(name=RuleEffects.ModThreshold)

        # sides=result_die because max roll is the result die by definition
        skill_probs = all_probs_threshold(
            dice=int(dice), sides=int(result_die), val=int(threshold)
        )

        results = set()
        for val, prob in skill_probs.items():
            eff = Effect(name=RuleEffects.ModResult, source="Skill", value=Decimal(val))
            results.add(replace(state, prob=Decimal(prob) * state.prob).add_effect(eff))
        return frozenset(results)


class StableComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[RollTimeSteps.GATHER_DICE] = self._stable

    def _stable(self, state: State) -> FrozenSet(State):
        can_stable = bool(
            state.get_effects(name=Speed.Combat, source="Attacker")
            or state.get_effects(name=Speed.Top, source="Attacker")
        )
        if can_stable:
            eff = Effect(name=RuleEffects.ModDice, source="Stable", value=Decimal(1))
            state = state.add_effect(eff)
        return frozenset({state})


class VulnCorrosionComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._take_damage

    def _take_damage(self, state: State) -> FrozenSet[State]:
        """Take pending damage before it can be rolled"""
        eff = Effect(
            name=AttackEffects.BonusDamage,
            source="Corrosion",
            value=state.sum_effects(name=StatusEffects.CorrosionDamage),
        )
        state = state.add_effect(eff)
        state = apply_damage(
            state=state,
            filter={"name": eff.name, "source": eff.source},
        )
        return frozenset({state.remove_effects(name=StatusEffects.CorrosionDamage)})


class VulnFireComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._take_damage

    def _take_damage(self, state: State) -> FrozenSet[State]:
        """Take pending damage before it can be rolled"""
        eff = Effect(
            name=AttackEffects.BonusDamage,
            source="Fire",
            value=state.sum_effects(name=StatusEffects.FireDamage),
        )
        state = state.add_effect(eff)
        state = apply_damage(
            state=state,
            filter={"name": eff.name, "source": eff.source},
        )
        return frozenset({state.remove_effects(name=StatusEffects.FireDamage)})


class VulnHaywireComponent(Component):
    def __init__(self) -> None:
        super().__init__()
        self._behaviors[ResolveTimeSteps.ADD_EXTRA_EFFECTS] = self._take_damage

    def _take_damage(self, state: State) -> FrozenSet[State]:
        """Take pending damage before it can be rolled"""
        eff = Effect(
            name=AttackEffects.BonusDamage,
            source="Haywire",
            value=state.sum_effects(name=StatusEffects.HaywireDamage),
        )
        state = state.add_effect(eff)
        state = apply_damage(
            state=state,
            filter={"name": eff.name, "source": eff.source},
        )
        return frozenset({state.remove_effects(name=StatusEffects.HaywireDamage)})


MODEL_TRAIT_DEFS = {
    "Agile": Trait(
        partial(AgileComponent),
        valid_role=["def"],
    ),
    "Aircraft": Trait(
        partial(BasicTraitComponent, effect_name=ModelTypes.Aircraft, source="Type"),
        valid_role=[],
    ),
    "ANN": Trait(
        partial(ThresholdBonusComponent, source="ANN", value=-1),
    ),
    "Gear": Trait(
        partial(BasicTraitComponent, effect_name=ModelTypes.Gear, source="Type"),
        valid_role=[],
    ),
    "Brawl": Trait(
        partial(BrawlComponent),
        required_params=["value"],
    ),
    "Crippled": Trait(
        partial(DiceBonusComponent, source="Crippled", value=-1),
        valid_role=[],
    ),
    "CustomDice": Trait(
        partial(DiceBonusComponent, source="Custom"),
        required_params=["value"],
        valid_role=[],
    ),
    "CustomResult": Trait(
        partial(ResultBonusComponent, source="Custom"),
        required_params=["value"],
        valid_role=[],
    ),
    "CustomThreshold": Trait(
        partial(ThresholdBonusComponent, source="Custom"),
        required_params=["value"],
        valid_role=[],
    ),
    "ECMDefense": Trait(
        partial(DiceBonusComponent, source="ECM Defense", value=1),
        valid_role=[],
    ),
    "Armor": Trait(
        partial(BasicTraitComponent, effect_name=RuleEffects.Armor, source="Armor"),
        required_params=["value"],
        valid_role=[],
    ),
    "Skill": Trait(
        partial(SkillComponent),
        required_params=["value"],
        valid_role=[],
    ),
    "Hull": Trait(
        partial(BasicTraitComponent, effect_name=RuleEffects.Hull, source="Hull"),
        required_params=["value"],
        valid_role=[],
    ),
    "Reroll": Trait(
        partial(RerollComponent),
        required_params=["rule"],
        valid_role=[],
    ),
    "Structure": Trait(
        partial(
            BasicTraitComponent, effect_name=RuleEffects.Structure, source="Structure"
        ),
        required_params=["value"],
        valid_role=[],
    ),
    "Elevated": Trait(
        partial(ThresholdBonusComponent, source="Elevation", value=-1),
        valid_role=["att"],
    ),
    "ElevatedVTOL": Trait(
        partial(ElevatedVTOLComponent),
        excludes=["Elevated"],
    ),
    "Facing": Trait(
        partial(FacingComponent),
        required_params=["facing"],
        valid_role=[],
    ),
    "FieldArmor": Trait(
        partial(FieldArmorComponent),
        valid_role=["def"],
    ),
    "FireMission": Trait(
        partial(
            BasicTraitComponent,
            effect_name=AttackEffects.FireMission,
            source="Fire Mission",
        ),
        valid_role=[],
    ),
    "Infantry": Trait(
        partial(InfantryComponent),
        valid_role=[],
    ),
    "Cover": Trait(
        partial(CoverComponent),
        required_params=["amount"],
        valid_role=[],
    ),
    "Smoke": Trait(
        partial(DiceBonusComponent, source="Smoke", value=1),
        valid_role=[],
    ),
    "Stable": Trait(
        partial(StableComponent),
        valid_role=["att"],
    ),
    "Speed": Trait(
        partial(SpeedComponent),
        required_params=["speed"],
        valid_role=[],
    ),
    "Lumbering": Trait(
        partial(LumberingComponent),
        valid_role=["def"],
    ),
    "ResistCorrosion": Trait(
        partial(ResistCorrosionComponent),
        valid_role=["def"],
        excludes=["VulnCorrosion"],
    ),
    "ResistFire": Trait(
        partial(ResistFireComponent),
        valid_role=["def"],
        excludes=["VulnFire"],
    ),
    "ResistHaywire": Trait(
        partial(ResistHaywireComponent),
        valid_role=["def"],
        excludes=["VulnHaywire"],
    ),
    "Vehicle": Trait(
        partial(BasicTraitComponent, effect_name=ModelTypes.Vehicle, source="Type"),
        valid_role=[],
    ),
    "VulnCorrosion": Trait(
        partial(VulnCorrosionComponent),
        valid_role=["def"],
        excludes=["ResistCorrosion"],
    ),
    "VulnFire": Trait(
        partial(VulnFireComponent),
        valid_role=["def"],
        excludes=["ResistFire"],
    ),
    "VulnHaywire": Trait(
        partial(VulnHaywireComponent),
        valid_role=["def"],
        excludes=["ResistHaywire"],
    ),
}


def model_trait_to_component(name: str, **kwargs) -> Component:
    # print(f"{name}: {kwargs}")
    trait_factory = MODEL_TRAIT_DEFS[name].factory
    missing = set(MODEL_TRAIT_DEFS[name].required_params).difference(set(kwargs.keys()))
    if missing:
        print(f"Attempted to make {name} trait without required params: {missing}")
    return trait_factory(**kwargs)


def make_model_components(
    model_params: Sequence[Mapping[str, Union[str, Decimal]]]
) -> frozenset(Component):
    return frozenset(model_trait_to_component(**params) for params in model_params)
