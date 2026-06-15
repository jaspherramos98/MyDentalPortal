# File: MyDentalPortal/blueprints/models/patient.py
# Boundary schema for patient documents (Phase 3 — schema validation).
#
# Lenient BY DESIGN: it guarantees the canonical nested skeleton + the key
# invariants on WRITE, while PRESERVING any extra fields (extra="allow") so the
# rich PDA field set — and any legacy field — is never silently dropped. This
# turns the previously-defensive `ensure_nested` patch into an actual guarantee
# for newly-written documents. Reads of legacy/flat docs still go through
# patients.ensure_nested, which tolerates anything.

from pydantic import BaseModel, ConfigDict, Field, field_validator
from bson import ObjectId


# The nested sections the detail/list templates expect. Declared so a write can
# never produce a doc missing them (or with a non-dict in their place).
class PatientDoc(BaseModel):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    clinic_id: ObjectId
    is_active: bool = True

    personal_info: dict = Field(default_factory=dict)
    contact_info: dict = Field(default_factory=dict)
    emergency_contact: dict = Field(default_factory=dict)
    dental_history: dict = Field(default_factory=dict)
    medical_history: dict = Field(default_factory=dict)
    referral_info: dict = Field(default_factory=dict)
    guardian_info: dict = Field(default_factory=dict)
    minor_info: dict = Field(default_factory=dict)
    insurance_info: dict = Field(default_factory=dict)

    @field_validator("clinic_id", mode="before")
    @classmethod
    def _coerce_clinic_id(cls, v):
        """Accept an ObjectId or a valid id string; reject anything else.

        A patient with no/invalid clinic is the canonical 'malformed' doc — it
        breaks every owner-scoped access query — so this is the one hard invariant.
        """
        if isinstance(v, ObjectId):
            return v
        try:
            return ObjectId(v)
        except Exception as exc:  # noqa: BLE001 - normalise to a validation error
            raise ValueError("clinic_id must be a valid ObjectId") from exc


def validate_patient(data: dict) -> dict:
    """Validate + normalise a patient document for writing.

    Returns a dict safe to insert (sections guaranteed, clinic_id an ObjectId,
    unknown fields preserved). Raises pydantic ValidationError on malformed input.
    """
    return PatientDoc.model_validate(data).model_dump()
