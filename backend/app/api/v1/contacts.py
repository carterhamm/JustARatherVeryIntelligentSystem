"""
Contacts API — upload, search, CRUD for user contacts.

Supports vCard (.vcf) and CSV file uploads. All contact fields are
AES-256 encrypted at rest using per-user keys.
"""

from __future__ import annotations

import base64
import csv
import io
import json
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

router = APIRouter(tags=["Contacts"])


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
    photo: Optional[str] = None
    photo_content_type: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    birthday: Optional[str] = None
    url: Optional[str] = None
    raw_vcard: Optional[str] = None
    extra_fields: Optional[str] = None  # JSON string


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    photo: Optional[str] = None
    photo_content_type: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    birthday: Optional[str] = None
    url: Optional[str] = None
    raw_vcard: Optional[str] = None
    extra_fields: Optional[str] = None


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
    photo: Optional[str] = None
    photo_content_type: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    birthday: Optional[str] = None
    url: Optional[str] = None
    raw_vcard: Optional[str] = None
    extra_fields: Optional[str] = None
    created_at: str


class UploadResponse(BaseModel):
    imported: int
    skipped: int
    errors: int
    message: str


# ── Helpers ──────────────────────────────────────────────────────────────

_FIELDS = [
    "first_name", "last_name", "phone", "email", "company", "title", "address", "notes",
    "photo", "street", "city", "state", "postal_code", "country",
    "birthday", "url", "raw_vcard", "extra_fields",
]

# photo_content_type is NOT encrypted — it's just a MIME type (e.g. "image/jpeg"),
# not PII, and the String(64) column can't hold AES-encrypted values.


def _encrypt_contact(data: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    """Encrypt all contact string fields."""
    out = {}
    for f in _FIELDS:
        val = data.get(f) or None
        out[f] = encrypt_message(val, user_id) if val else None
    # Pass through photo_content_type unencrypted (not PII, String(64) column)
    out["photo_content_type"] = data.get("photo_content_type") or None
    return out


def _decrypt_contact(contact: Contact) -> dict[str, Any]:
    """Decrypt a Contact row into a plain dict."""
    result: dict[str, Any] = {"id": str(contact.id), "created_at": contact.created_at.isoformat()}
    for f in _FIELDS:
        val = getattr(contact, f, None)
        result[f] = decrypt_message(val, contact.user_id) if val else None
    # photo_content_type stored unencrypted (not PII)
    result["photo_content_type"] = getattr(contact, "photo_content_type", None)
    _normalize_address(result)
    return result


def _serialize_vcard_value(val: Any) -> Any:
    """Safely serialize a vCard property value to a JSON-compatible type."""
    if val is None:
        return None
    if isinstance(val, bytes):
        return base64.b64encode(val).decode("ascii")
    if isinstance(val, (str, int, float, bool)):
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, (list, tuple)):
        return [_serialize_vcard_value(v) for v in val]
    # For vobject address/name objects, convert to string
    return str(val)


def _parse_vcard(content: str) -> list[dict[str, Any]]:
    """Parse vCard content into a list of contact dicts.

    Stores ALL vCard properties — known fields go into dedicated columns
    for searchability, and the complete vCard is preserved in raw_vcard.
    Any properties not mapped to a column go into extra_fields (JSON).
    """
    contacts = []
    # Split raw content into individual vCards for raw_vcard storage
    raw_cards: list[str] = []
    current: list[str] = []
    for line in content.splitlines(keepends=True):
        current.append(line)
        if line.strip().upper() == "END:VCARD":
            raw_cards.append("".join(current))
            current = []

    card_idx = 0
    for vcard in vobject.readComponents(content):
        c: dict[str, Any] = {}

        # Store the raw vCard text verbatim
        if card_idx < len(raw_cards):
            c["raw_vcard"] = raw_cards[card_idx]
        card_idx += 1

        # ── Known fields (mapped to columns) ──
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
        # Address (first one, joined + structured components)
        if hasattr(vcard, "adr"):
            adr = vcard.adr.value
            adr_street = getattr(adr, "street", "") or ""
            adr_city = getattr(adr, "city", "") or ""
            adr_region = getattr(adr, "region", "") or ""
            adr_code = getattr(adr, "code", "") or ""
            adr_country = getattr(adr, "country", "") or ""
            parts = [adr_street, adr_city, adr_region, adr_code, adr_country]
            c["address"] = ", ".join(p for p in parts if p)
            if adr_street:
                c["street"] = adr_street
            if adr_city:
                c["city"] = adr_city
            if adr_region:
                c["state"] = adr_region
            if adr_code:
                c["postal_code"] = adr_code
            if adr_country:
                c["country"] = adr_country
        # Notes
        if hasattr(vcard, "note"):
            c["notes"] = vcard.note.value
        # Photo — handle bytes, base64-encoded, and URI formats
        if hasattr(vcard, "photo"):
            try:
                photo_prop = vcard.photo
                photo_val = photo_prop.value
                params = getattr(photo_prop, "params", {}) or {}
                content_type = None
                if "TYPE" in params:
                    ptype = params["TYPE"]
                    if isinstance(ptype, list):
                        ptype = ptype[0]
                    ptype = ptype.lower()
                    content_type = f"image/{ptype}" if "/" not in ptype else ptype
                elif "MEDIATYPE" in params:
                    mt = params["MEDIATYPE"]
                    content_type = mt[0] if isinstance(mt, list) else mt
                encoding = params.get("ENCODING", [])
                if isinstance(encoding, list):
                    encoding = encoding[0] if encoding else ""
                encoding = encoding.upper() if isinstance(encoding, str) else ""
                if isinstance(photo_val, bytes):
                    c["photo"] = base64.b64encode(photo_val).decode("ascii")
                elif encoding in ("B", "BASE64"):
                    c["photo"] = photo_val.replace("\n", "").replace("\r", "").replace(" ", "")
                elif isinstance(photo_val, str) and photo_val.startswith(("http://", "https://")):
                    c["photo"] = photo_val  # URI — frontend handles http URLs
                elif isinstance(photo_val, str) and len(photo_val) > 50:
                    # Likely raw base64 without explicit encoding param
                    c["photo"] = photo_val.replace("\n", "").replace("\r", "").replace(" ", "")
                else:
                    c["photo"] = photo_val
                if not content_type:
                    content_type = "image/jpeg"
                c["photo_content_type"] = content_type
            except Exception as exc:
                logger.warning("Failed to extract photo for contact: %s", exc)
            if content_type:
                c["photo_content_type"] = content_type
            elif not content_type and isinstance(photo_val, bytes):
                c["photo_content_type"] = "image/jpeg"
        # Birthday
        if hasattr(vcard, "bday"):
            bday_val = vcard.bday.value
            if hasattr(bday_val, "isoformat"):
                c["birthday"] = bday_val.isoformat()
            else:
                c["birthday"] = str(bday_val)
        # URL
        if hasattr(vcard, "url"):
            c["url"] = vcard.url.value

        # ── Capture ALL remaining properties into extra_fields ──
        _KNOWN_PROPS = {"n", "fn", "tel", "email", "org", "title", "adr", "note",
                        "photo", "bday", "url", "version", "prodid", "rev", "uid"}
        extra: dict[str, Any] = {}
        for child in vcard.getChildren():
            prop_name = child.name.lower()
            if prop_name in _KNOWN_PROPS:
                continue
            val = _serialize_vcard_value(child.value)
            params = {k: v for k, v in (getattr(child, "params", {}) or {}).items()}
            entry = {"value": val}
            if params:
                entry["params"] = {k: v if len(v) > 1 else v[0] for k, v in params.items()}
            # Multiple values for same property (e.g., multiple phones, IMs)
            if prop_name in extra:
                existing = extra[prop_name]
                if isinstance(existing, list):
                    existing.append(entry)
                else:
                    extra[prop_name] = [existing, entry]
            else:
                extra[prop_name] = entry

        # Also capture ALL phone numbers and emails (not just first)
        if hasattr(vcard, "tel_list") and len(vcard.tel_list) > 1:
            extra["all_phones"] = []
            for tel in vcard.tel_list:
                tel_params = {k: v for k, v in (getattr(tel, "params", {}) or {}).items()}
                tel_entry: dict[str, Any] = {"value": tel.value}
                if tel_params:
                    tel_entry["params"] = {k: v if len(v) > 1 else v[0] for k, v in tel_params.items()}
                extra["all_phones"].append(tel_entry)
        if hasattr(vcard, "email_list") and len(vcard.email_list) > 1:
            extra["all_emails"] = []
            for em in vcard.email_list:
                em_params = {k: v for k, v in (getattr(em, "params", {}) or {}).items()}
                em_entry: dict[str, Any] = {"value": em.value}
                if em_params:
                    em_entry["params"] = {k: v if len(v) > 1 else v[0] for k, v in em_params.items()}
                extra["all_emails"].append(em_entry)
        # Multiple addresses
        if hasattr(vcard, "adr_list") and len(vcard.adr_list) > 1:
            extra["all_addresses"] = []
            for a in vcard.adr_list:
                av = a.value
                adr_dict = {
                    "street": getattr(av, "street", "") or "",
                    "city": getattr(av, "city", "") or "",
                    "region": getattr(av, "region", "") or "",
                    "code": getattr(av, "code", "") or "",
                    "country": getattr(av, "country", "") or "",
                }
                a_params = {k: v for k, v in (getattr(a, "params", {}) or {}).items()}
                if a_params:
                    adr_dict["params"] = {k: v if len(v) > 1 else v[0] for k, v in a_params.items()}
                extra["all_addresses"].append(adr_dict)

        if extra:
            c["extra_fields"] = json.dumps(extra, ensure_ascii=False)

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
        "street": "street", "street address": "street",
        "city": "city",
        "state": "state", "region": "state", "province": "state",
        "zip": "postal_code", "zip code": "postal_code", "postal code": "postal_code", "postal_code": "postal_code", "postcode": "postal_code",
        "country": "country",
        "birthday": "birthday", "birth date": "birthday", "birthdate": "birthday", "date of birth": "birthday",
        "website": "url", "url": "url", "web": "url", "homepage": "url",
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


_STATE_ABBREVS: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def _normalize_address(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize state names to 2-letter abbreviations and title-case cities."""
    state = data.get("state")
    if state and isinstance(state, str):
        s = state.strip()
        abbrev = _STATE_ABBREVS.get(s.lower())
        if abbrev:
            data["state"] = abbrev
        elif len(s) == 2:
            data["state"] = s.upper()
        elif len(s) > 2:
            # Try matching anyway (handles partial matches like "Ut" → "UT")
            abbrev = _STATE_ABBREVS.get(s.lower())
            if abbrev:
                data["state"] = abbrev

    city = data.get("city")
    if city and isinstance(city, str):
        data["city"] = city.strip().title()

    country = data.get("country")
    if country and isinstance(country, str):
        c = country.strip()
        # Common normalizations
        if c.lower() in ("us", "usa", "united states", "united states of america"):
            data["country"] = "US"
        elif len(c) == 2:
            data["country"] = c.upper()
        else:
            data["country"] = c.title()

    # Rebuild combined address from components if components exist
    parts = []
    for f in ("street", "city", "state", "postal_code", "country"):
        v = data.get(f)
        if v and isinstance(v, str) and v.strip():
            parts.append(v.strip())
    if parts:
        data["address"] = ", ".join(parts)

    return data


def _is_duplicate(raw: dict[str, Any], existing: list[dict[str, Any]]) -> bool:
    """Check if a contact matches any existing contact by name + phone/email."""
    first = (raw.get("first_name") or "").strip().lower()
    last = (raw.get("last_name") or "").strip().lower()
    phone = _normalize_phone(raw.get("phone") or "")
    email = (raw.get("email") or "").strip().lower()
    if not first:
        return False
    for ex in existing:
        ex_first = (ex.get("first_name") or "").strip().lower()
        ex_last = (ex.get("last_name") or "").strip().lower()
        if first != ex_first or last != ex_last:
            continue
        # Same name — check phone or email
        if phone and _normalize_phone(ex.get("phone") or "") == phone:
            return True
        if email and (ex.get("email") or "").strip().lower() == email:
            return True
        # Same full name with no phone/email to compare — treat as duplicate
        if not phone and not email:
            return True
    return False


def _normalize_phone(p: str) -> str:
    """Strip non-digits for phone comparison."""
    return "".join(c for c in p if c.isdigit())[-10:] if p else ""


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_contacts(
    file: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Upload contacts from one or more .vcf or .csv files."""
    imported, skipped, errors = 0, 0, 0

    # Load existing contacts for duplicate detection
    existing_rows = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    existing_decrypted = [_decrypt_contact(c) for c in existing_rows.scalars().all()]

    for upload_file in file:
        content = (await upload_file.read()).decode("utf-8", errors="ignore")
        filename = (upload_file.filename or "").lower()

        if filename.endswith(".vcf") or "BEGIN:VCARD" in content[:200]:
            parsed = _parse_vcard(content)
        elif filename.endswith(".csv"):
            parsed = _parse_csv(content)
        else:
            skipped += 1
            continue

        for raw in parsed:
            try:
                _normalize_address(raw)
                if _is_duplicate(raw, existing_decrypted):
                    skipped += 1
                    continue
                encrypted = _encrypt_contact(raw, current_user.id)
                contact = Contact(user_id=current_user.id, **encrypted)
                db.add(contact)
                imported += 1
                # Add to existing list so subsequent entries in same import are checked
                existing_decrypted.append(raw)
            except Exception:
                logger.exception("Failed to import contact")
                errors += 1

    if imported > 0:
        await db.commit()

    return UploadResponse(
        imported=imported,
        skipped=skipped,
        errors=errors,
        message=f"Imported {imported} contacts."
        + (f" {skipped} duplicates skipped." if skipped else "")
        + (f" {errors} errors." if errors else ""),
    )


@router.post("", response_model=ContactResponse)
async def create_contact(
    body: ContactCreate,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Create a single contact."""
    data = body.model_dump()
    _normalize_address(data)
    encrypted = _encrypt_contact(data, current_user.id)
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


@router.get("/duplicates")
async def find_duplicates(
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Find suspected duplicate contacts (same name + phone or email)."""
    result = await db.execute(
        select(Contact).where(Contact.user_id == current_user.id)
    )
    all_contacts = [_decrypt_contact(c) for c in result.scalars().all()]

    # Group by normalized name
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in all_contacts:
        key = f"{(c.get('first_name') or '').strip().lower()}|{(c.get('last_name') or '').strip().lower()}"
        groups[key].append(c)

    # Return only groups with 2+ contacts
    duplicates = []
    for key, members in groups.items():
        if len(members) >= 2:
            duplicates.append({
                "name": key.replace("|", " ").strip(),
                "count": len(members),
                "contacts": [ContactResponse(**m) for m in members],
            })

    return {"duplicate_groups": duplicates, "total_duplicates": sum(g["count"] for g in duplicates)}


@router.put("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    current_user: User = Depends(get_current_active_user_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Update a contact. Only provided (non-None) fields are changed."""
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.user_id == current_user.id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field in _FIELDS:
            encrypted = encrypt_message(value, current_user.id) if value else None
            setattr(contact, field, encrypted)

    await db.commit()
    await db.refresh(contact)
    return ContactResponse(**_decrypt_contact(contact))


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
