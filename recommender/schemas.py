"""What the user tells us. Nothing here is ever saved to disk."""
from __future__ import annotations

from dataclasses import dataclass, field

SERVICE_LINES = ("Audit", "Tax", "Advisory")
FIRMS = ("Deloitte", "PwC", "EY", "KPMG")


@dataclass
class UserInputs:
    service_line: str = "Audit"
    # Salary. If `salary` is set it is treated as a national base and scaled to each metro
    # with the BLS accountant wage ratio. If None, the base comes from salary_base.csv.
    salary: float | None = None
    firms: tuple[str, ...] = FIRMS                 # firms the user is open to

    # 1-5 importance per category (0 or missing = skip). Keys match criteria.yaml categories.
    weights: dict[str, float] = field(default_factory=dict)

    # Hard filters (None = no filter)
    no_state_income_tax: bool = False
    exclude_states: tuple[str, ...] = ()
    max_rent: float | None = None                  # monthly, Zillow ZORI
    max_miles_to_office: float | None = 20.0
    min_walk_index: float | None = None

    top_n_metros: int = 5
    top_n_zips: int = 5

    def __post_init__(self):
        if self.service_line not in SERVICE_LINES:
            raise ValueError(f"service_line must be one of {SERVICE_LINES}")
        bad = [f for f in self.firms if f not in FIRMS]
        if bad:
            raise ValueError(f"Unknown firms: {bad}")
        for k, v in self.weights.items():
            if not 0 <= v <= 5:
                raise ValueError(f"Weight for {k} must be 0-5, got {v}")
        if self.salary is not None and self.salary <= 0:
            raise ValueError("salary must be positive")
