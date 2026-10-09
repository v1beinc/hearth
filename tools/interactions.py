"""The same cabin coordinates and cat schedule as hearth.frag, for native clicks."""
import math


def scene_point(x, y, width, height):
    fit = min(width / 320, height / 180)
    return (x - width / 2) / fit + 160, (y - height / 2) / fit + 90


def cat_position(time, showcase=False, life=True):
    if not life:
        return None
    world = time * (8 if showcase else 1)
    slot = math.floor(world / 260)
    age = world % 260 - 18
    # Integer arithmetic matches GPU scheduling without sin/hash precision drift.
    if age < 0 or age > 156 or (slot > 0 and (slot * 7 + 3) % 11 < 3 and not showcase):
        return None

    def smooth(low, high, value):
        value = max(0, min(1, (value - low) / (high - low)))
        return value * value * (3 - 2 * value)

    arrive, depart = smooth(0, 17, age), smooth(137, 156, age)
    return math.floor(342 - 163 * arrive + 163 * depart), depart > 0


class Interactions:
    def __init__(self):
        self.triggered = {}

    def click(self, target, time):
        self.triggered[target] = time

    def uniforms(self, time):
        def age(target):
            return max(0, time - self.triggered[target]) if target in self.triggered else None

        fuel_age, coffee_age, pet_age = age("wood"), age("coffee"), age("cat")
        fuel = 0 if fuel_age is None else (.25 + .75 * (1 - math.exp(-fuel_age / 2))) * math.exp(-fuel_age / 65)
        coffee = 0 if coffee_age is None else math.exp(-coffee_age / 45)
        pet = 0 if pet_age is None or pet_age > 4 else max(0, 1 - pet_age / 4)
        return fuel, coffee, pet, 0 if pet_age is None else min(pet_age, 4)

    def target(self, p, time, values):
        x, y = p
        cat = cat_position(time, values.get("uShowcase", 0) > .5, values.get("uLife", 1) > .5)
        if cat and cat[0] - 29 <= x <= cat[0] + 29 and 12 <= y <= 49:
            return "cat"
        if 72 <= x <= 89 and 48 <= y <= 60:
            return "coffee"
        if 223 <= x <= 268 and 25 <= y <= 49:
            return "wood"
        return None
