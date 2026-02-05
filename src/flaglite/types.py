"""FlagLite SDK type definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class User:
    """User information."""
    id: str
    username: str
    email: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class Project:
    """Project information."""
    id: str
    name: str


@dataclass
class Environment:
    """Environment information."""
    id: str
    name: str
    key: str


@dataclass
class SignupResponse:
    """Response from signup."""
    user: User
    api_key: str
    token: str
    project: Project
    environments: List[Environment]

    @classmethod
    def from_dict(cls, data: dict) -> SignupResponse:
        """Create from API response dict."""
        return cls(
            user=User(
                id=data["user"]["id"],
                username=data["user"]["username"],
                email=data["user"].get("email"),
                created_at=data["user"].get("created_at"),
            ),
            api_key=data["api_key"],
            token=data["token"],
            project=Project(
                id=data["project"]["id"],
                name=data["project"]["name"],
            ),
            environments=[
                Environment(
                    id=env["id"],
                    name=env["name"],
                    key=env["key"],
                )
                for env in data["environments"]
            ],
        )


@dataclass
class LoginResponse:
    """Response from login."""
    user: User
    token: str

    @classmethod
    def from_dict(cls, data: dict) -> LoginResponse:
        """Create from API response dict."""
        return cls(
            user=User(
                id=data["user"]["id"],
                username=data["user"]["username"],
                email=data["user"].get("email"),
                created_at=data["user"].get("created_at"),
            ),
            token=data["token"],
        )
