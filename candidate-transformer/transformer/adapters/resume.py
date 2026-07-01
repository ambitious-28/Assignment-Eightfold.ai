"""
Resume adapter — PDF and DOCX. One file = one person.

Extracts: name, headline, emails, phones, links, location,
          skills, experience (company/title/dates/summary), education.

All extraction is rule-based (regex + section headers). No ML, no LLM.
Layout-heavy / multi-column resumes degrade gracefully — unrecognised
content is dropped, never invented.
"""

from __future__ import annotations

import re
from pathlib import Path

import phonenumbers

from transformer.adapters.base import FieldValue, IntermediateRecord, SourceAdapter
from transformer.models import EducationEntry, ExperienceEntry, Links, Location, SkillEntry
from transformer.normalize.dates import normalize_date, normalize_end_year
from transformer.normalize.emails import normalize_email, normalize_emails
from transformer.normalize.headline import normalize_headline
from transformer.normalize.links import normalize_github_url, normalize_linkedin_url, normalize_url
from transformer.normalize.location import normalize_location_phrase
from transformer.normalize.names import normalize_name, normalize_org_name
from transformer.normalize.phones import normalize_phone
from transformer.normalize.skills import SKILL_ALIASES, normalize_skill

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_DATE_TOKEN_RE = re.compile(
    r"(?:"
    r"\d{4}-\d{2}-\d{2}|\d{4}-\d{2}"                    # ISO
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"  # Mon YYYY
    r"|\d{1,2}/\d{4}"                                    # MM/YYYY
    r"|(?:present|current|now)"                          # open-ended
    r")",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("experience", re.compile(
        r"^(experience|work experience|employment history|professional experience)", re.IGNORECASE)),
    ("education", re.compile(
        r"^(education|academic background|qualifications|academic)", re.IGNORECASE)),
    ("skills", re.compile(
        r"^(skills|technical skills|core competencies|technologies|expertise|key skills)", re.IGNORECASE)),
    ("summary", re.compile(
        r"^(summary|profile|objective|about|professional summary)", re.IGNORECASE)),
    ("links", re.compile(
        r"^(links|profiles|social|contact)", re.IGNORECASE)),
]

_DEGREE_KEYWORDS = re.compile(
    r"\b(b\.?tech|m\.?tech|b\.?e\.?|m\.?e\.?|b\.?sc|m\.?sc|bachelor|master|mba|phd|"
    r"ph\.?d|b\.?com|m\.?com|bca|mca|b\.?a\.?|m\.?a\.?|diploma|doctorate)\b",
    re.IGNORECASE,
)

_LOCATION_PREFIX_RE = re.compile(
    r"(?:location|based in|address|city|residing at)\s*[:\-]?\s*(.+)", re.IGNORECASE
)

_NAME_BLACKLIST_RE = re.compile(r"[@\d/\\|]|https?://|www\.", re.IGNORECASE)


class ResumeAdapter(SourceAdapter):

    def can_handle(self, path: Path) -> bool:
        return path.suffix.lower() in {".pdf", ".docx"}

    def read(self, path: Path) -> list[IntermediateRecord]:
        try:
            text = self._extract_text(path)
        except Exception as exc:  # noqa: BLE001
            return [IntermediateRecord(
                source="resume",
                source_file=str(path),
                warnings=[f"Text extraction failed for {path.name}: {exc}"],
            )]

        if not text or not text.strip():
            return [IntermediateRecord(
                source="resume",
                source_file=str(path),
                warnings=[f"{path.name}: no text could be extracted"],
            )]

        warnings: list[str] = []
        fields: dict[str, FieldValue] = {}
        lines = [ln.rstrip() for ln in text.splitlines()]

        # --- Global extractions (whole text) ---
        self._extract_emails(text, fields, warnings)
        self._extract_phones(text, fields, warnings)
        self._extract_links(text, fields, warnings)

        # --- Section splitting ---
        sections = self._split_sections(lines)
        header_lines = sections.get("header", [])

        # --- Header block extractions ---
        self._extract_name_headline(header_lines, fields, warnings)
        self._extract_location_from_header(header_lines, fields, warnings)

        # --- Per-section extractions ---
        if "skills" in sections:
            self._extract_skills(sections["skills"], fields, warnings)
        if "experience" in sections:
            self._extract_experience(sections["experience"], fields, warnings)
        if "education" in sections:
            self._extract_education(sections["education"], fields, warnings)
        if "summary" in sections and "headline" not in fields:
            # Use first summary sentence as headline if no headline found
            summary_text = " ".join(ln for ln in sections["summary"] if ln.strip())
            if summary_text:
                norm, method, ok = normalize_headline(summary_text[:200])
                if ok:
                    fields["headline"] = FieldValue(
                        raw=summary_text[:200], normalized=norm, method=method, ok=ok
                    )

        return [IntermediateRecord(
            source="resume",
            source_file=str(path),
            fields=fields,
            warnings=warnings,
        )]

    # -----------------------------------------------------------------------
    # Text extraction
    # -----------------------------------------------------------------------

    def _extract_text(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            import pdfplumber
            pages: list[str] = []
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages.append(t)
            return "\n".join(pages)
        else:  # .docx
            import docx
            doc = docx.Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)

    # -----------------------------------------------------------------------
    # Global extractions
    # -----------------------------------------------------------------------

    def _extract_emails(self, text: str, fields: dict, warnings: list) -> None:
        raw_emails = _EMAIL_RE.findall(text)
        normed = normalize_emails(raw_emails)
        if normed:
            fields["emails"] = FieldValue(
                raw=raw_emails, normalized=normed, method="email_lowercased", ok=True
            )

    def _extract_phones(self, text: str, fields: dict, warnings: list) -> None:
        phones: list[str] = []
        raw_phones: list[str] = []
        for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
            raw = match.raw_string
            norm, method, ok = normalize_phone(raw)
            if ok and norm and norm not in phones:
                phones.append(norm)
                raw_phones.append(raw)
        if phones:
            fields["phones"] = FieldValue(
                raw=raw_phones, normalized=phones, method="e164_normalized", ok=True
            )

    def _extract_links(self, text: str, fields: dict, warnings: list) -> None:
        linkedin_match = _LINKEDIN_RE.search(text)
        github_match = _GITHUB_RE.search(text)
        other_urls: list[str] = []

        linkedin_val = None
        github_val = None

        if linkedin_match:
            raw = linkedin_match.group(0)
            norm, method, ok = normalize_linkedin_url(raw)
            linkedin_val = norm if ok else None

        if github_match:
            raw = github_match.group(0)
            norm, method, ok = normalize_github_url(raw)
            github_val = norm if ok else None

        # Other URLs (exclude already-captured linkedin/github)
        for url_match in _URL_RE.finditer(text):
            raw_url = url_match.group(0)
            if linkedin_match and raw_url in linkedin_match.group(0):
                continue
            if github_match and raw_url in github_match.group(0):
                continue
            norm, _, ok = normalize_url(raw_url)
            if ok and norm:
                other_urls.append(norm)

        if linkedin_val or github_val or other_urls:
            links_obj = Links(
                linkedin=linkedin_val,
                github=github_val,
                other=other_urls,
            )
            fields["links"] = FieldValue(
                raw={"linkedin": linkedin_match.group(0) if linkedin_match else None,
                     "github": github_match.group(0) if github_match else None,
                     "other": other_urls},
                normalized=links_obj,
                method="url_extracted",
                ok=True,
            )

    # -----------------------------------------------------------------------
    # Section splitting
    # -----------------------------------------------------------------------

    def _split_sections(self, lines: list[str]) -> dict[str, list[str]]:
        """
        Split lines into named sections.
        Lines before the first section header go into "header".
        """
        sections: dict[str, list[str]] = {"header": []}
        current = "header"

        for line in lines:
            stripped = line.strip()
            matched_section = None
            for section_name, pattern in _SECTION_PATTERNS:
                if pattern.match(stripped):
                    matched_section = section_name
                    break
            if matched_section:
                current = matched_section
                sections.setdefault(current, [])
            else:
                sections.setdefault(current, []).append(line)

        return sections

    # -----------------------------------------------------------------------
    # Header-block extractions
    # -----------------------------------------------------------------------

    def _extract_name_headline(self, header_lines: list[str], fields: dict, warnings: list) -> None:
        name_found = False
        headline_found = False

        for line in header_lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Skip lines with email/URL/phone-like content
            if _NAME_BLACKLIST_RE.search(stripped):
                continue
            # Skip lines that look like locations (contain comma + country-ish word)
            if re.search(r",\s*[A-Za-z]+$", stripped) and len(stripped.split()) <= 5:
                continue

            words = stripped.split()
            if not name_found and 1 <= len(words) <= 5 and stripped[0].isupper():
                norm, method, ok = normalize_name(stripped)
                if ok:
                    fields["full_name"] = FieldValue(raw=stripped, normalized=norm, method=method, ok=ok)
                    name_found = True
                    continue

            if name_found and not headline_found and 2 <= len(words) <= 10:
                norm, method, ok = normalize_headline(stripped)
                if ok:
                    fields["headline"] = FieldValue(raw=stripped, normalized=norm, method=method, ok=ok)
                    headline_found = True
                    break

    def _extract_location_from_header(self, header_lines: list[str], fields: dict, warnings: list) -> None:
        # Check for explicit "Location:" prefix first
        for line in header_lines:
            m = _LOCATION_PREFIX_RE.match(line.strip())
            if m:
                loc_text = m.group(1).strip()
                loc_dict = normalize_location_phrase(loc_text)
                loc_obj = Location(**loc_dict)
                if any(v for v in loc_dict.values()):
                    fields["location"] = FieldValue(
                        raw=loc_text, normalized=loc_obj, method="location_phrase_parsed", ok=True
                    )
                return

        # Fallback: look for "City, Region, Country" pattern in header
        for line in header_lines:
            stripped = line.strip()
            if "," in stripped and not _EMAIL_RE.search(stripped):
                loc_dict = normalize_location_phrase(stripped)
                if any(v for v in loc_dict.values()):
                    loc_obj = Location(**loc_dict)
                    fields["location"] = FieldValue(
                        raw=stripped, normalized=loc_obj, method="location_phrase_parsed", ok=True
                    )
                    return

    # -----------------------------------------------------------------------
    # Skills extraction
    # -----------------------------------------------------------------------

    def _extract_skills(self, lines: list[str], fields: dict, warnings: list) -> None:
        seen_names: set[str] = set()
        skill_entries: list[SkillEntry] = []
        raw_skills: list[str] = []

        for line in lines:
            # Split by common delimiters
            tokens = re.split(r"[,|•\-\n]+", line)
            for token in tokens:
                token = token.strip()
                if len(token) < 2:
                    continue
                norm, method, ok = normalize_skill(token)
                if ok and norm and norm not in seen_names:
                    seen_names.add(norm)
                    skill_entries.append(SkillEntry(name=norm, confidence=0.0, sources=[]))
                    raw_skills.append(token)

        if skill_entries:
            fields["skills"] = FieldValue(
                raw=raw_skills, normalized=skill_entries, method="skill_section_extracted", ok=True
            )

    # -----------------------------------------------------------------------
    # Experience extraction
    # -----------------------------------------------------------------------

    def _extract_experience(self, lines: list[str], fields: dict, warnings: list) -> None:
        entries: list[ExperienceEntry] = []
        raw_blocks: list[str] = []

        # Primary split: blank-line delimited blocks.
        # Secondary split: within each block, detect entry boundaries by the
        # pattern (non-date line) followed by (line with "|" and a date token),
        # which is the standard "Title\nCompany | Dates" signature.
        blocks = self._split_into_blocks(lines)
        split_blocks: list[list[str]] = []
        for block in blocks:
            split_blocks.extend(self._sub_split_experience_block(block))

        for block in split_blocks:
            if not block:
                continue
            entry = self._parse_experience_block(block)
            if entry.company or entry.title:
                entries.append(entry)
                raw_blocks.append("\n".join(block))

        if entries:
            fields["experience"] = FieldValue(
                raw=raw_blocks, normalized=entries, method="resume_experience_parsed", ok=True
            )

    def _parse_experience_block(self, block: list[str]) -> ExperienceEntry:
        """
        Parse one experience block. Expected format:
          Line 0: Job Title
          Line 1: Company Name | Date Range   OR   Company Name
          Line 2: Date Range (if not on line 1)
          Lines 3+: Summary / bullet points
        """
        title: str | None = None
        company: str | None = None
        start: str | None = None
        end: str | None = None
        summary_lines: list[str] = []

        non_empty = [ln.strip() for ln in block if ln.strip()]
        if not non_empty:
            return ExperienceEntry()

        date_line_idx: int | None = None
        for i, line in enumerate(non_empty):
            if _DATE_TOKEN_RE.search(line) or _YEAR_RE.search(line):
                date_line_idx = i
                break

        if date_line_idx is None:
            # No date line found — first line = title, second = company
            title = non_empty[0] if len(non_empty) > 0 else None
            company = non_empty[1] if len(non_empty) > 1 else None
            summary_lines = non_empty[2:]
        elif date_line_idx == 0:
            # Date on first line — unusual; treat whole as summary
            summary_lines = non_empty
        elif date_line_idx == 1:
            # Title | Company + date on same line, or title then date
            title = non_empty[0]
            date_line = non_empty[1]
            # Try splitting company and dates by | or –
            parts = re.split(r"\s*[|–\-]{1,2}\s*", date_line, maxsplit=1)
            if len(parts) == 2:
                company_candidate, date_part = parts
                if _DATE_TOKEN_RE.search(date_part) or _YEAR_RE.search(date_part):
                    company = company_candidate.strip()
                    start, end = self._extract_date_range(date_part)
                else:
                    company = date_line
                    start, end = self._extract_date_range(date_line)
            else:
                start, end = self._extract_date_range(date_line)
                company = None
            summary_lines = non_empty[2:]
        else:
            # Date line is at index ≥2 → title=line[0], company=line[1], rest has dates
            title = non_empty[0]
            company = non_empty[1]
            start, end = self._extract_date_range(non_empty[date_line_idx])
            summary_lines = [ln for i, ln in enumerate(non_empty)
                             if i not in (0, 1, date_line_idx)]

        # Normalize
        title_norm = normalize_name(title)[0] if title else None
        company_norm = normalize_org_name(company)[0] if company else None
        summary = " ".join(summary_lines).strip() or None

        return ExperienceEntry(
            company=company_norm,
            title=title_norm,
            start=start,
            end=end,
            summary=summary,
        )

    def _extract_date_range(self, text: str) -> tuple[str | None, str | None]:
        """Extract start and end dates from a text fragment."""
        # Look for "Present" / "Current" as end
        is_present = bool(re.search(r"\b(present|current|now)\b", text, re.IGNORECASE))

        date_tokens = _DATE_TOKEN_RE.findall(text)
        # Filter out "present" from date tokens for normalization
        real_dates = [t for t in date_tokens
                      if not re.match(r"present|current|now", t, re.IGNORECASE)]

        start = normalize_date(real_dates[0])[0] if real_dates else None
        end = (
            "Present" if is_present
            else (normalize_date(real_dates[1])[0] if len(real_dates) > 1 else None)
        )
        return start, end

    # -----------------------------------------------------------------------
    # Education extraction
    # -----------------------------------------------------------------------

    def _extract_education(self, lines: list[str], fields: dict, warnings: list) -> None:
        entries: list[EducationEntry] = []
        raw_blocks: list[str] = []

        blocks = self._split_into_blocks(lines)

        for block in blocks:
            if not block:
                continue
            entry = self._parse_education_block(block)
            if entry.institution or entry.degree:
                entries.append(entry)
                raw_blocks.append("\n".join(block))

        if entries:
            fields["education"] = FieldValue(
                raw=raw_blocks, normalized=entries, method="resume_education_parsed", ok=True
            )

    def _parse_education_block(self, block: list[str]) -> EducationEntry:
        non_empty = [ln.strip() for ln in block if ln.strip()]
        if not non_empty:
            return EducationEntry()

        institution: str | None = None
        degree: str | None = None
        field_of_study: str | None = None
        end_year: int | None = None

        for line in non_empty:
            # Extract year
            if end_year is None:
                year_val, _, ok = normalize_end_year(
                    _YEAR_RE.search(line).group(1) if _YEAR_RE.search(line) else ""
                )
                if ok:
                    end_year = year_val

            # Detect degree line
            if _DEGREE_KEYWORDS.search(line):
                # Try to split degree and field: "B.Tech in Computer Science"
                in_match = re.search(r"\bin\b(.+)", line, re.IGNORECASE)
                if in_match:
                    degree_part = line[:in_match.start()].strip()
                    field_of_study = in_match.group(1).strip()
                    deg_match = _DEGREE_KEYWORDS.search(degree_part)
                    degree = degree_part if deg_match else None
                else:
                    degree = _DEGREE_KEYWORDS.search(line).group(0).upper()
                continue

            # Institution: first non-degree line without a year
            if institution is None and not _YEAR_RE.fullmatch(line.strip()):
                institution = normalize_org_name(line)[0]

        return EducationEntry(
            institution=institution,
            degree=degree,
            field=field_of_study,
            end_year=end_year,
        )

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    def _sub_split_experience_block(self, block: list[str]) -> list[list[str]]:
        """
        Given a single block (no blank lines), detect multiple experience entries
        by looking for the signature: a non-date line immediately followed by a
        line that contains both '|' and a date token (the 'Company | Dates' line).
        Each such occurrence marks the start of a new entry (index i, the title).
        Returns the block split into sub-blocks, or [block] if no boundaries found.
        """
        non_empty = [ln for ln in block if ln.strip()]
        if len(non_empty) < 4:  # too short to contain 2 full entries
            return [block]

        # Find boundary indices: index i where non_empty[i] is a title-like line
        # (no date token) and non_empty[i+1] is a "Company | Date" line.
        boundaries: list[int] = [0]
        for i in range(1, len(non_empty) - 1):
            line = non_empty[i]
            next_line = non_empty[i + 1]
            has_date = bool(_DATE_TOKEN_RE.search(line))
            next_has_pipe_date = (
                "|" in next_line and bool(_DATE_TOKEN_RE.search(next_line))
            )
            if not has_date and next_has_pipe_date and i not in boundaries:
                boundaries.append(i)

        if len(boundaries) == 1:
            return [block]  # no secondary boundaries found

        sub_blocks = []
        for idx, start in enumerate(boundaries):
            end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(non_empty)
            sub_blocks.append(non_empty[start:end])
        return sub_blocks

    def _split_into_blocks(self, lines: list[str]) -> list[list[str]]:
        """Split lines into blocks separated by blank lines."""
        blocks: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if line.strip():
                current.append(line)
            else:
                if current:
                    blocks.append(current)
                    current = []
        if current:
            blocks.append(current)
        return blocks
