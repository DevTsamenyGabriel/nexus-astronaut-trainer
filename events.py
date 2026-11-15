"""events.py (Atlas). Event table. Every effect is a fixed SIMULATION VALUE.
Effect keys: power/oxygen/water/food (+/- points), stress (all crew),
radiation (all crew, sim units; 100 = planning reference limit),
shielding, co2, crew_time (adds readiness-costing repair debt), dust_days."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    effects: dict
    note: str   # Fixed consequence text shown after choosing.


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    destinations: tuple
    day_min: int
    day_max: int
    chance: float      # Chance per day (simulation value).
    effects: dict      # Applied immediately when the event fires.
    question: str
    options: tuple


EVENTS = [
    Event("dust_storm", "Dust storm", ("mars",), 3, 28, 0.08,
          {"power": -12, "dust_days": 5},
          "A dust storm cuts sunlight to the arrays for several days. What do you do?",
          (Option("storm_shelter", "Shelter in place, cut non-essential loads",
                  {"stress": 3, "power": 4}, "Loads cut. Crew restless but safe."),
           Option("storm_eva", "EVA to clean the panels",
                  {"radiation": 3, "dust_days": -2, "crew_time": 1}, "Panels cleaned. The storm clears sooner, with some exposure."),
           Option("storm_reserve", "Ride it out on battery reserves",
                  {"power": -8}, "Reserves drain hard."))),
    Event("solar_particle", "Solar particle event", ("moon", "mars"), 2, 29, 0.06,
          {"radiation": 6},
          "A solar particle event is arriving. An EVA is scheduled. Decide.",
          (Option("spe_shelter", "Move everyone to the shelter",
                  {"radiation": -4, "stress": 4, "crew_time": 1}, "Shielded. Exposure stays low, schedule slips."),
           Option("spe_postpone", "Postpone the EVA, stay in the habitat",
                  {"radiation": 2, "stress": 1}, "Moderate exposure, EVA delayed."),
           Option("spe_continue", "Finish the EVA",
                  {"radiation": 9, "stress": -2}, "Work done, high exposure."))),
    Event("scrubber_fault", "CO2 scrubber fault", ("moon", "mars"), 2, 29, 0.07,
          {"co2": 15, "stress": 4, "oxygen": -3},
          "The CO2 scrubber is failing and cabin CO2 is climbing.",
          (Option("scrub_swap", "Swap in a spare cartridge",
                  {"co2": -12, "water": -3}, "CO2 falls. Spare cartridge used."),
           Option("scrub_repair", "Repair the unit by hand",
                  {"co2": -18, "crew_time": 2, "stress": 2}, "Best CO2 fix, costs crew time."),
           Option("scrub_ignore", "Monitor and defer",
                  {"co2": 10, "stress": 5}, "CO2 keeps rising."))),
    Event("crop_blight", "Crop blight", ("moon", "mars"), 4, 28, 0.06,
          {"food": -12},
          "Blight is spreading through the growth trays.",
          (Option("blight_destroy", "Destroy the infected trays",
                  {"food": -6, "stress": 2}, "Spread stopped, more food lost."),
           Option("blight_treat", "Treat the trays with water-intensive wash",
                  {"water": -5, "food": -2}, "Most of the crop is saved."),
           Option("blight_eat", "Harvest early and eat now",
                  {"food": 5, "stress": 3}, "Short-term food, weaker crop."))),
    Event("equipment_failure", "Equipment failure", ("moon", "mars"), 3, 29, 0.07,
          {"crew_time": 2},
          "A pump controller fails. Repairs will take crew time.",
          (Option("equip_full", "Full repair",
                  {"crew_time": 2, "power": -2}, "Fixed properly."),
           Option("equip_patch", "Quick patch",
                  {"crew_time": 1, "power": -5}, "Holds, but wastes power."),
           Option("equip_cannibalize", "Cannibalize a spare system",
                  {"crew_time": 1, "oxygen": -2, "stress": 2}, "Quick, but a spare is gone."))),
    Event("micrometeoroid", "Micrometeoroid leak", ("moon", "mars"), 5, 29, 0.04,
          {"oxygen": -10, "stress": 3},
          "A micrometeoroid has punctured a module wall. Air is leaking.",
          (Option("leak_seal", "Seal the module and repair",
                  {"crew_time": 2, "oxygen": -2}, "Sealed, with a small extra loss."),
           Option("leak_isolate", "Isolate the module permanently",
                  {"oxygen": 3, "shielding": -5, "stress": 3}, "Air saved, habitat space lost."),
           Option("leak_patch", "Emergency patch kit",
                  {"oxygen": -5, "crew_time": 1}, "Temporary fix."))),
    Event("regolith_dust", "Regolith dust in the airlock", ("moon",), 3, 29, 0.07,
          {"stress": 3, "oxygen": -2},
          "Abrasive lunar dust is fouling the airlock seals.",
          (Option("dust_clean", "Deep-clean the airlock",
                  {"crew_time": 1, "water": -2}, "Seals restored."),
           Option("dust_replace", "Replace the seals",
                  {"crew_time": 2, "power": -2}, "Reliable fix."),
           Option("dust_ignore", "Keep going",
                  {"oxygen": -4, "stress": 2}, "Slow leak continues."))),
    Event("crew_symptoms", "Crew radiation symptoms", ("moon", "mars"), 99, 99, 0.0,
          {"stress": 3},
          "A crew member reports nausea and fatigue after the EVA. Decide.",
          (Option("symptom_standdown", "Stand the crew member down and monitor them",
                  {"stress": 1, "crew_time": 1}, "Crew member rests. Monitoring continues, schedule slips."),
           Option("symptom_continue", "Send them back out to finish the EVA",
                  {"radiation": 5, "stress": 4}, "Work finishes, but exposure and stress rise."),
           Option("symptom_ignore", "Log it and keep the schedule",
                  {"radiation": 2, "stress": 3}, "Symptoms unchecked, stress climbs."))),
]

EVENT_BY_ID = {e.id: e for e in EVENTS}


def eligible(destination, day):
    """Events that can trigger for this destination and day."""
    return [e for e in EVENTS if destination in e.destinations and e.day_min <= day <= e.day_max]
