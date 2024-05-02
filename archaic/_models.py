from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ObjectID:
    objectid: int = field(default=-1, init=False)


@dataclass
class GlobalID:
    globalid: str = field(default="", init=False)


@dataclass
class EditTracking:
    created_user: Optional[str] = field(default=None, init=False)
    created_date: Optional[datetime] = field(default=None, init=False)
    last_edited_user: Optional[str] = field(default=None, init=False)
    last_edited_date: Optional[datetime] = field(default=None, init=False)
