"""
Contacts API — upload, search, CRUD for user contacts.

Supports vCard (.vcf) and CSV file uploads. All contact fields are
AES-256 encrypted at rest using per-user keys.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from typing import Any, Optional

import vobject
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user_or_service, get_db
from app.core.encryption import decrypt_message, encrypt_message
from app.models.contact import Contact
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts", tags=["Contacts"])


# ── Schemas ──────────────────────────────────────────────────────────────

class ContactCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None


class ContactResponse(BaseModel):
    id: str
    first_name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    created_at: str


class UploadResponse(BaseModel):
    imported: int
    skipped: int
    errors: int
    message: str


# ── Helpers ──────────────────────────────────────────────────────────────

_FIELDS = ["first_name", "last_name", "phone", "email", "company", "title", "address", "notes"]


def _encrypt_contact(data: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    """Encrypt all contact string fields."""
    out = {}
    for f in _FIELDS:
        val = data.get(f) or None
        out[f] = encrypt_message(val, user_id) if val else None
    return out


def _decrypt_contact(contact: Contact) -> dict[str, Any]:
    """Decrypt a Contact row into a plain dict."""
    result: dict[str, Any] = {"id": str(contact.id), "created_at": contact.created_at.isoformat()}
    for f in _FIELDS:
        val = getattr(contact, f, None)
        result[f] = decrypt_message(val, contact.user_id) if val else None
    return result


def _parse_vcard(content: str) -> list[dict[str, Any]]:
    """Parse vCard content into a list of contact dicts."""
    contacts = []
    for vcard in vobject.readComponents(content):
        c: dict[str, Any] = {}
        # Name
        if hasattr(vcard, "n"):
            n = vcard.n.value
            c["first_name"] = getattr(n, "given", "") or ""
            c["last_name"] = getattr(n, "family", "") or ""
        elif hasattr(vcard, "fn"):
            parts = vcard.fn.value.split(" ", 1)
            c["first_name"] = parts[0]
            c["last_name"] = parts[1] if len(parts) > 1 else ""
        else:
            continue  # Skip contacts with no name

        if not c.get("first_name", "").strip():
            continue

        # Phone (first one)
        if hasattr(vcard, "tel"):
            c["phone"] = vcard.tel.value
        # Email (first one)
        if hasattr(vcard, "email"):
            c["email"] = vcard.email.value
        # Company
        if hasattr(vcard, "org"):
            org = vcard.org.value
            c["company"] = org[0] if isinstance(org, list) and org else str(org)
        # Title
        if hasattr(vcard, "title"):
            c["title"] = vcard.title.value
        # Address (first one, joined)
        if hasattr(vcard, "adr"):
            adr = vcard.adr.value
            parts = [
                getattr(adr, "street", ""),
                getattr(adr, "city", ""),
                getattr(adr, "region", ""),
                getattr(adr, "code", ""),
                getattr(adr, "country", ""),
            ]
            c["address"] = ", ".join(p for p in parts if p)
        # Notes
        if hasattr(vcard, "note"):
            c["notes"] = vcard.note.value

        contacts.append(c)
    return contacts


def _parse_csv(content: str) -> list[dict[str, Any]]:
    """Parse CSV content into contact dicts. Expects header row."""
    contacts = []
    reader = csv.DictReader(io.StringIO(content))
    # Map common CSV header variants to our fields
    field_map = {
        "first name": "first_name", "firstname": "first_name", "first_name": "first_name", "given name": "first_name",
        "last name": "last_name", "lastname": "last_name", "last_name": "last_name", "family name": "last_name",
        "phone": "phone", "phone number": "phone", "mobile": "phone", "telephone": "phone",
        "email": "email", "e-mail": "email", "email address": "email",
        "company": "company", "organization": "company", "org": "company",
        "title": "title", "job title": "title",
        "address": "address",
        "notes": "notes", "note": "notes",
    }
    for row in reader:
        c: dict[str, Any] = {}
        for csv_col, value in row.items():
            if not value or not csv_col:
                continue
            key = field_map.get(csv_col.lower().strip())
            if key and key not in c:
                c[key] = value.strip()
        if c.get("first_name"):
            contacts.append(c)
    return contacts


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_contacts(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Upload contacts from a .vcf or .csv file."""
    content = (await file.read()).decode("utf-8", errors="ignore")
    filename = (file.filename or "").lower()

    if filename.endswith(".vcf") or "BEGIN:VCARD" in content[:200]:
        parsed = _parse_vcard(content)
    elif filename.endswith(".csv"):
        parsed = _parse_csv(content)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported format. Upload a .vcf or .csv file.",
        )

    imported, skipped, errors = 0, 0, 0
    for raw in parsed:
        try:
            encrypted = _encrypt_contact(raw, current_user.id)
            contact = Contact(user_id=current_user.id, **encrypted)
            db.add(contact)
            imported += 1
        except Exception:
            logger.exception("Failed to import contact")
            errors += 1

    if imported > 0:
        await db.commit()

    return UploadResponse(
        imported=imported,
        skipped=skipped,
        errors=errors,
        message=f"Imported {imported} contacts." + (f" {errors} errors." if errors else ""),
    )


@router.post("", response_model=ContactResponse)
async def create_contact(
    body: ContactCreate,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Create a single contact."""
    encrypted = _encrypt_contact(body.model_dump(), current_user.id)
    contact = Contact(user_id=current_user.id, **encrypted)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return ContactResponse(**_decrypt_contact(contact))


@router.get("", response_model=list[ContactResponse])
async def list_contacts(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List all contacts for the current user."""
    result = await db.execute(
        select(Contact)
        .where(Contact.user_id == current_user.id)
        .order_by(Contact.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    contacts = result.scalars().all()
    return [ContactResponse(**_decrypt_contact(c)) for c in contacts]


@router.get("/search", response_model=list[ContactResponse])
async def search_contacts(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Search contacts by decrypting and matching in memory.

    At the 2-user scale this is fine. For large datasets,
    add a search index column.
    """
    result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    contacts = result.scalars().all()
    query_lower = q.lower()
    matches = []
    for c in contacts:
        decrypted = _decrypt_contact(c)
        searchable = " ".join(
            str(v) for v in decrypted.values() if v and isinstance(v, str)
        ).lower()
        if query_lower in searchable:
            matches.append(ContactResponse(**decrypted))
    return matches[:50]


@router.get("/count")
async def count_contacts(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Return the number of contacts for the current user."""
    result = await db.execute(
        select(func.count()).select_from(Contact).where(Contact.user_id == current_user.id)
    )
    return {"count": result.scalar() or 0}


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Delete a contact."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()
    return {"deleted": True}


@router.delete("")
async def delete_all_contacts(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Delete all contacts for the current user."""
    result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    contacts = result.scalars().all()
    for c in contacts:
        await db.delete(c)
    await db.commit()
    return {"deleted": len(contacts)}
