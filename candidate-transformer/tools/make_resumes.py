"""
Generate single-column PDF resumes for Stage 11 sample candidates.

Usage:
    python tools/make_resumes.py [--out-dir samples/unstructured/resumes/]

Requires: reportlab (already in project deps)
"""

from __future__ import annotations

import argparse
from pathlib import Path


# ---------------------------------------------------------------------------
# Candidate resume data
# ---------------------------------------------------------------------------

CANDIDATES = [
    {
        "filename": "aarav_sharma.pdf",
        "name": "Aarav Sharma",
        "headline": "Senior Software Engineer",
        "email": "aarav.sharma@example.com",
        "phone": "+919876543210",
        "linkedin": "linkedin.com/in/aaravsharma",
        "github": "github.com/aaravsharma",
        "location": "Mumbai, Maharashtra, India",
        "summary": "Experienced software engineer with 5+ years building scalable distributed systems.",
        "experience": [
            {
                "title": "Senior Software Engineer",
                "company": "TechCorp India",
                "dates": "Jan 2020 - Present",
                "desc": "Led development of microservices platform serving 1M+ users.",
            },
            {
                "title": "Software Engineer",
                "company": "StartupXYZ",
                "dates": "Jun 2018 - Dec 2019",
                "desc": "Built REST APIs and data pipelines using Python and Docker.",
            },
        ],
        "education": [
            {
                "institution": "IIT Bombay",
                "degree": "B.Tech in Computer Science",
                "year": "2018",
            }
        ],
        "skills": "Python, Docker, SQL, React",
    },
    {
        "filename": "ananya_iyer.pdf",
        "name": "Ananya Iyer",
        "headline": "Java Backend Developer",
        "email": "ananya.iyer@example.com",
        "phone": "",  # no phone — tests sparse resume
        "linkedin": "",
        "github": "",
        "location": "Chennai, Tamil Nadu, India",
        "summary": "Backend developer specialising in Java enterprise applications.",
        "experience": [
            {
                "title": "Software Developer",
                "company": "Infosys",
                "dates": "Aug 2021 - Present",
                "desc": "Developed Spring Boot microservices for banking clients.",
            },
        ],
        "education": [
            {
                "institution": "Anna University",
                "degree": "B.E. in Computer Science",
                "year": "2021",
            }
        ],
        "skills": "Java, Spring Boot, MySQL",
    },
    {
        "filename": "rohan_mehta.pdf",
        "name": "Rohan Mehta",
        "headline": "Full Stack Developer",
        "email": "rohan.mehta@example.com",
        "phone": "+919876506001",
        "linkedin": "linkedin.com/in/rohanmehta",
        "github": "github.com/rohanmehta",
        "location": "Pune, Maharashtra, India",
        "summary": "Full stack developer with expertise in JavaScript and Node.js ecosystems.",
        "experience": [
            {
                "title": "Full Stack Developer",
                "company": "WebCraft",
                "dates": "Mar 2021 - Present",
                "desc": "Built e-commerce platforms using React, Node.js and MongoDB.",
            },
            {
                "title": "Junior Developer",
                "company": "FreelanceWork",
                "dates": "Jan 2020 - Feb 2021",
                "desc": "Developed web applications for small business clients.",
            },
        ],
        "education": [
            {
                "institution": "Pune University",
                "degree": "B.E. in Information Technology",
                "year": "2020",
            }
        ],
        "skills": "JavaScript, Node.js, MongoDB",
    },
    {
        "filename": "diya_patel.pdf",
        "name": "Diya Patel",
        "headline": "Data Scientist",
        "email": "diya.patel@example.com",
        "phone": "+919876509001",
        "linkedin": "linkedin.com/in/diyapatel",
        "github": "",
        "location": "Ahmedabad, Gujarat, India",
        "summary": "Data scientist with 4 years of experience in ML model development and deployment.",
        "experience": [
            {
                "title": "Data Scientist",
                "company": "DataDriven Inc",
                "dates": "Jul 2020 - Present",
                "desc": "Built recommendation systems and NLP pipelines using Python and TensorFlow.",
            },
        ],
        "education": [
            {
                "institution": "IIT Ahmedabad",
                "degree": "M.Tech in Data Science",
                "year": "2020",
            }
        ],
        "skills": "Python, TensorFlow, Pandas",
    },
    {
        "filename": "aditya_rao.pdf",
        "name": "Aditya Rao",
        "headline": "Senior Backend Engineer",
        "email": "aditya.rao@example.com",
        "phone": "+919876512001",
        "linkedin": "linkedin.com/in/adityarao",
        "github": "github.com/adityarao",
        "location": "Hyderabad, Telangana, India",
        "summary": "Senior backend engineer with 7 years of experience in fintech systems.",
        "experience": [
            {
                "title": "Senior Backend Engineer",
                "company": "FinEdge",
                "dates": "Feb 2017 - Present",
                "desc": "Architected Django-based microservices handling financial transactions.",
            },
            {
                "title": "Backend Developer",
                "company": "TechStart",
                "dates": "Jan 2016 - Jan 2017",
                "desc": "Built REST APIs for insurance analytics platform.",
            },
        ],
        "education": [
            {
                "institution": "BITS Pilani",
                "degree": "B.E. in Computer Science",
                "year": "2015",
            }
        ],
        "skills": "Python, Django, PostgreSQL, Redis",
    },
    {
        "filename": "ishaan_verma.pdf",
        "name": "Ishaan Verma",
        "headline": "Platform Engineer",
        "email": "ishaan.verma@example.com",
        "phone": "+919876513000",
        "linkedin": "linkedin.com/in/ishaanverma",
        "github": "github.com/ishaanverma",
        "location": "Bengaluru, Karnataka, India",
        "summary": "Platform engineer specialising in cloud-native infrastructure and DevOps practices.",
        "experience": [
            {
                "title": "Platform Engineer",
                "company": "CloudNative",
                "dates": "Apr 2019 - Present",
                "desc": "Managed Kubernetes clusters and CI/CD pipelines using Terraform and Go.",
            },
        ],
        "education": [
            {
                "institution": "NIT Warangal",
                "degree": "B.Tech in Electronics",
                "year": "2019",
            }
        ],
        # NOTE: k8s is listed here — tests alias mapping → Kubernetes
        "skills": "k8s, Docker, Go, Terraform",
    },
]


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def _generate_pdf(candidate: dict, out_path: Path) -> None:
    """Generate a single-column prose PDF resume using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(out_path), pagesize=A4)
    width, height = A4
    y = height - 50

    def write(text: str, size: int = 11, gap: int = 18) -> None:
        nonlocal y
        if y < 60:
            c.showPage()
            y = height - 50
        c.setFont("Helvetica", size)
        c.drawString(50, y, text)
        y -= gap

    def section(title: str) -> None:
        nonlocal y
        y -= 6
        write(title, size=13, gap=18)

    # Header
    write(candidate["name"], size=16, gap=22)
    write(candidate["headline"], size=12, gap=20)

    contact_parts = []
    if candidate["email"]:
        contact_parts.append(candidate["email"])
    if candidate["phone"]:
        contact_parts.append(candidate["phone"])
    if contact_parts:
        write(" | ".join(contact_parts), gap=16)

    links_parts = []
    if candidate["linkedin"]:
        links_parts.append(candidate["linkedin"])
    if candidate["github"]:
        links_parts.append(candidate["github"])
    if links_parts:
        write(" | ".join(links_parts), gap=16)

    if candidate["location"]:
        write(candidate["location"], gap=24)

    # Summary
    section("Summary")
    write(candidate["summary"], gap=20)

    # Experience
    section("Experience")
    for exp in candidate["experience"]:
        write(exp["title"], gap=14)
        write(f"{exp['company']} | {exp['dates']}", gap=14)
        write(exp["desc"], gap=14)
        write(" ", gap=12)  # space so pdfplumber emits a blank line between blocks

    # Education
    section("Education")
    for edu in candidate["education"]:
        write(edu["institution"], gap=14)
        write(edu["degree"], gap=14)
        write(edu["year"], gap=20)

    # Skills
    section("Skills")
    write(candidate["skills"], gap=14)

    c.save()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate sample PDF resumes for Stage 11 candidates."
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).parent.parent / "samples" / "unstructured" / "resumes"),
        metavar="DIR",
        help="Output directory for generated PDFs (default: samples/unstructured/resumes/).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for candidate in CANDIDATES:
        out_path = out_dir / candidate["filename"]
        _generate_pdf(candidate, out_path)
        print(f"Generated: {out_path}")

    print(f"\nDone. {len(CANDIDATES)} resumes written to {out_dir}/")


if __name__ == "__main__":
    main()
