from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import Decimal
from operator import attrgetter
from typing import (
    Callable,
    DefaultDict,
    Dict,
    FrozenSet,
    Hashable,
    List,
)


@dataclass(frozen=True)
class BaseEffect:
    """Base Effect class has no definition. Subclass for specific game needs"""

    pass


@dataclass(order=True, frozen=True)
class State:
    """The State class represents one possible game state. State objects are immutable.

    prob: Probability of arriving at the given game state.
    effects: Set of game effects describing the game state, e.g. damage, status, etc.
    """

    prob: Decimal = Decimal(1)
    effects: FrozenSet(BaseEffect) = field(default_factory=frozenset)

    def __str__(self) -> str:
        strs = [f"Prob: {self.prob:.2%}"]
        sorted_effects = sorted(self.effects, key=str)
        strs.extend([f"\t{str(eff)}" for eff in sorted_effects])
        return "\n".join(strs)

    def add_effect(self, effect: BaseEffect = None) -> State:
        """Add an Effect to the state"""
        if effect is None:
            return self
        return replace(self, effects=self.effects.union({effect}))

    def remove_effects(self, **kwargs) -> State:
        """Removes Effects whose attributes match kwargs"""

        def filter(effect: BaseEffect) -> bool:
            return all(attrgetter(k)(effect) == v for k, v in kwargs.items())

        return replace(
            self, effects=frozenset(e for e in self.effects if not filter(e))
        )

    def remove_by_filter(self, pred: Callable[[BaseEffect], bool]) -> State:
        """Removes Effects matching a predicate"""
        return replace(self, effects=frozenset(e for e in self.effects if not pred(e)))

    def get_effects(self, **kwargs) -> FrozenSet(BaseEffect):
        """Returns Effects whose attributes match kwargs"""

        def filter(effect: BaseEffect) -> bool:
            return all(attrgetter(k)(effect) == v for k, v in kwargs.items())

        return frozenset(e for e in self.effects if filter(e))

    def get_by_filter(
        self, pred: Callable[[BaseEffect], bool]
    ) -> FrozenSet(BaseEffect):
        """Returns Effects matching a predicate"""
        return frozenset(e for e in self.effects if pred(e))

    def sum_effects(self, **kwargs) -> Decimal:
        """Returns sum of value attributes of Effects whose attributes match kwargs"""
        effects = self.get_effects(**kwargs)
        return sum(map(attrgetter("value"), effects))

    def sum_by_filter(self, pred: Callable[[BaseEffect], bool]) -> Decimal:
        """Return sum of value attributes of Effects matching a predicate"""
        effects = self.get_by_filter(pred)
        return sum(map(attrgetter("value"), effects))


# Type alias
Behavior = Callable[[State], FrozenSet[State]]
"""A Behavior is a function that operates on one State and returns an immutable
set of one or more States. This is necessary because some rules may be probabilistic
and thus cause a single input State to branch into multiple output States.
"""


class Component:
    """The Component base class encapsulates behavior that mutates state. A Component
    can have multiple behaviors that activate on specific events/messages to perform
    their functions. Messages trigger methods by dispatching through a map.

    Subclass Component to define their actual Behaviors, then map Behaviors to messages
    in the subclass's __init__() function.

    Components can express which messages they have behaviors for, so they only receive
    those messages. If passed a message for which they do not have a defined behavior,
    they return the state unchanged.
    """

    def __init__(self) -> None:
        # For safety, there is a default behavior for any message that returns the
        # passed state unchanged.
        self._behaviors: Dict[Hashable, Behavior] = defaultdict(
            lambda: self._null_behavior
        )
        self._parent: Entity = None

    def _null_behavior(self, state: State) -> FrozenSet[State]:
        return frozenset({state})

    def valid_messages(self) -> FrozenSet(Hashable):
        # Report which messages this Component responds to. May contain messages
        # for which it has a null behavior if it was erroneously passed those
        # messages previously, as they will be added to the defaultdict as keys.
        return frozenset(self._behaviors.keys())

    def run(self, msg: Hashable, state: State) -> FrozenSet[State]:
        # if self._behaviors[msg](state) is None:
        #     print(f"{self.__class__}, {msg}")
        return self._behaviors[msg](state)


class Entity:
    """A game entity that operates on the game state according to rules. It could be
    a model in the game with specific rules attached to it, or the abstract concept
    of the game rules itself.

    Entities contain Components that actually perform changes to the game state when
    triggered by certain messages, representing steps of the roll resolution process.
    Entities decide to pass on States to their Components for modification or not based
    on their Components' message subscriptions.
    """

    def __init__(self) -> None:
        self._subscriptions: DefaultDict[Hashable, List[Component]] = defaultdict(list)

    def add_component(self, component: Component):
        for msg in component.valid_messages():
            self._subscriptions[msg].append(component)
        component._parent = self

    def valid_messages(self) -> FrozenSet(Hashable):
        return frozenset(self._subscriptions.keys())

    def pass_message(self, msg: Hashable, state: State) -> FrozenSet(State):
        results = []
        working = [state]
        for component in self._subscriptions[msg]:
            while working:
                new_states = component.run(msg=msg, state=working.pop())
                results.extend(new_states)
            working, results = results, working
        return frozenset(working)


def normalize(states: FrozenSet[State]) -> FrozenSet[State]:
    """Scales all state probabilities to sum to 1. Useful to see actual probabilities
    assuming that one of the given states MUST occur.
    """
    prob_sum = sum(map(attrgetter("prob"), states))
    scale = Decimal(1) / prob_sum
    new_states = [replace(state, prob=state.prob * scale) for state in states]
    return frozenset(new_states)
