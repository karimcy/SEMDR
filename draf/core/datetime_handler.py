import logging
from abc import ABC
from typing import List, Optional, Tuple, Union

import pandas as pd

from draf import helper as hp

logger = logging.getLogger(__name__)
logger.setLevel(level=logging.WARN)


class DateTimeHandler(ABC):
    @property
    def step_width(self) -> float:
        """Returns the step width of the current datetimeindex.
        e.g. 0.25 for a frequency of 15min, 0.083 for 5min."""
        return hp.get_step_width(self.freq)

    @property
    def dt_info(self) -> str:
        """Get an info string of the chosen time horizon of the case study."""
        t1_str = f"{self.dtindex_custom[0].day_name()}, {self.dtindex_custom[0]}"
        t2_str = f"{self.dtindex_custom[-1].day_name()}, {self.dtindex_custom[-1]}"
        return (
            f"t1 = {self._t1:<5} ({t1_str}),\n"
            f"t2 = {self._t2:<5} ({t2_str})\n"
            f"Length = {self.dtindex_custom.size}"
        )

    @property
    def steps_per_day(self):
        steps_per_hour = 60 / hp.int_from_freq(self.freq)
        return int(steps_per_hour * 24)

    @property
    def freq_unit(self):
        """Return human-readable frequency unit including minute-level support"""
        if self.freq == "1min":
            return "min"
        elif self.freq == "5min":
            return "5 min"
        elif self.freq == "15min":
            return "1/4 h"
        elif self.freq == "30min":
            return "1/2 h"
        elif self.freq == "60min":
            return "h"
        else:
            return self.freq  # Fallback for any other frequency

    @property 
    def is_high_resolution(self) -> bool:
        """Check if using high-resolution (sub-hourly) time steps"""
        return self.freq in ["1min", "5min", "15min", "30min"]

    def match_dtindex(
        self, data: Union[pd.DataFrame, pd.Series], resample: bool = False
    ) -> Union[pd.DataFrame, pd.Series]:
        if resample:
            data = self.resample(data)
        return data[self._t1 : self._t2 + 1]

    def resample(self, data: Union[pd.DataFrame, pd.Series]) -> Union[pd.DataFrame, pd.Series]:
        return hp.resample(
            data, year=self.year, start_freq=hp.estimate_freq(data), target_freq=self.freq
        )

    def _set_dtindex(self, year: int, freq: str) -> None:
        # Validate year
        assert year in range(1980, 2100)
        
        # Validate frequency including minute-level support
        valid_freqs = ["1min", "5min", "15min", "30min", "60min"]
        assert freq in valid_freqs, f"Frequency must be one of {valid_freqs}, got {freq}"
        
        self.year = year
        self.freq = freq
        self.dtindex = hp.make_datetimeindex(year=year, freq=freq)
        self.dtindex_custom = self.dtindex
        self._t1 = 0
        self._t2 = self.dtindex.size - 1

    def _get_int_loc_from_dtstring(self, s: str) -> int:
        return self.dtindex.get_loc(f"{self.year}-{s}")

    def _get_first_int_loc_from_dtstring(self, s: str) -> int:
        x = self._get_int_loc_from_dtstring(s)
        try:
            return x.start
        except AttributeError:
            return x

    def _get_last_int_loc_from_dtstring(self, s: str) -> int:
        x = self._get_int_loc_from_dtstring(s)
        try:
            return x.stop
        except AttributeError:
            return x

    def _get_integer_locations(self, start, steps, end) -> Tuple[int, int]:
        t1 = self._get_first_int_loc_from_dtstring(start) if isinstance(start, str) else start
        if steps is not None and end is None:
            assert t1 + steps < self.dtindex.size, "Too many steps are given."
            t2 = t1 + steps - 1
        elif steps is None and end is not None:
            t2 = self._get_last_int_loc_from_dtstring(end) if isinstance(end, str) else end
        elif steps is None and end is None:
            t2 = self.dtindex.size - 1
        else:
            raise ValueError("One of steps or end must be given.")
        return t1, t2

    def timeslice(self, start: Optional[str], stop: Optional[str]) -> "Slice":
        """Get timeslice from start and stop strings.

        Example slicing from 17th to 26th of August
            >>> ts = cs.timeslice("8-17", "8-26")
            >>> sc.params.c_EG_T[ts].plot()
        """
        start_int = None if start is None else self._get_first_int_loc_from_dtstring(start)
        stop_int = None if stop is None else self._get_last_int_loc_from_dtstring(stop)
        return slice(start_int, stop_int)

    def set_rolling_horizon(self, horizon_hours: int = 24) -> None:
        """Set a rolling horizon for real-time optimization.
        
        Args:
            horizon_hours: Number of hours to optimize ahead
        """
        steps_ahead = int(horizon_hours * 60 / hp.int_from_freq(self.freq))
        if steps_ahead > self.dtindex.size:
            logger.warning(f"Horizon {horizon_hours}h exceeds available data, using full year")
            steps_ahead = self.dtindex.size - 1
        
        self._t2 = min(self._t1 + steps_ahead - 1, self.dtindex.size - 1)
        self.dtindex_custom = self.dtindex[self._t1:self._t2 + 1]

    def dated(
        self, data: Union[pd.Series, pd.DataFrame], activated=True
    ) -> Union[pd.Series, pd.DataFrame]:
        """Add datetime index to a data entity.

        The frequency and year are taken from the CaseStudy or the Scenario object.

        Args:
            data: A pandas data entity.
            activated: If False, the data is returned without modification.

        """
        if activated:
            assert isinstance(
                data, (pd.Series, pd.DataFrame)
            ), f"No data given, but type {type(data)}"
            data = data.copy()
            dtindex_to_use = self.dtindex[data.index.min() : data.index.max() + 1]
            data.index = dtindex_to_use
        return data
