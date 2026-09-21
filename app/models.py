"""Pydantic models for JobPilot's API."""
from typing import Optional

from pydantic import BaseModel

VALID_STAGES = ("saved", "applied", "interview", "offer", "rejected")


class RegisterIn(BaseModel):
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class JobCreate(BaseModel):
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class ApplicationStageUpdate(BaseModel):
    stage: str


class ApplicationNotesUpdate(BaseModel):
    notes: str


class ProfileIn(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class ProfileOut(ProfileIn):
    updated_at: str


class UrlImportIn(BaseModel):
    url: str


class BoardCandidate(BaseModel):
    url: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    external_id: Optional[str] = None


class BulkImportIn(BaseModel):
    jobs: list[BoardCandidate]
