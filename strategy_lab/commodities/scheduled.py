"""A declared scheduled-settlement proxy, never a certified exchange archive."""

import pandas as pd
from pandas.tseries.holiday import (
    AbstractHolidayCalendar, Holiday, GoodFriday, USMartinLutherKingJr,
    USPresidentsDay, USMemorialDay, USLaborDay, USThanksgivingDay,
    nearest_workday, sunday_to_monday,
)


def scheduled_sessions(start, end):
    """Return a rule calendar and exclusions independent of observed price dates.

    Applies a common US commodity settlement-date proxy. Early-close clocks,
    unexpected closures and historical rule/publication vintages are not modeled.
    New Year falling on Saturday does not remove the preceding Friday.
    """
    holidays = AbstractHolidayCalendar(rules=[
        Holiday("New Year", month=1, day=1, observance=sunday_to_monday),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]).holidays(start, end, return_name=True)
    weekdays = pd.bdate_range(start, end)
    sessions = weekdays.difference(holidays.index)
    closures = holidays.rename("rule").rename_axis("date").reset_index()
    closures["evidence"] = "rules-based proxy; individual historical notice not certified"
    return sessions, closures
