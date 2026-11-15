"""Temporary diagnostic. Prints what the daily-question code actually looks like on disk."""
import inspect

import main
import ui.dashboard as dash
import ui.event_card as ec

print("--- MissionView.show_daily ---")
print(inspect.signature(dash.MissionView.show_daily)
      if hasattr(dash.MissionView, "show_daily") else "MISSING")
print("--- EventCard.show_daily ---")
print(inspect.signature(ec.EventCard.show_daily)
      if hasattr(ec.EventCard, "show_daily") else "MISSING")
print("--- Controller._daily_prompt ---")
print("present" if hasattr(main.Controller, "_daily_prompt") else "MISSING")
print("--- Controller._offer_daily source ---")
print(inspect.getsource(main.Controller._offer_daily))
print("--- MissionView.show_daily source ---")
if hasattr(dash.MissionView, "show_daily"):
    print(inspect.getsource(dash.MissionView.show_daily))
print("--- EventCard.show_daily source ---")
if hasattr(ec.EventCard, "show_daily"):
    print(inspect.getsource(ec.EventCard.show_daily))
