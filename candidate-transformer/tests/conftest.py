"""
Pytest fixtures shared across test modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def sample_resume_pdf(tmp_path_factory) -> Path:
    """
    Generate a small single-column PDF resume using reportlab.
    Planted data for adapter tests:
      - Name: Test Candidate
      - Headline: Senior Software Engineer
      - Email: test.candidate@example.com
      - Phone: +91 98765 43210
      - LinkedIn: linkedin.com/in/testcandidate
      - GitHub: github.com/testcandidate
      - Location: Mumbai, Maharashtra, India
      - Skills: Python, k8s, Docker, React
      - Experience: Software Engineer at TechCorp India  (Jan 2020 – Present)
      - Education: B.Tech in Computer Science, IIT Bombay, 2018
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    out_dir = tmp_path_factory.mktemp("resumes")
    pdf_path = out_dir / "test_resume.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    width, height = A4
    y = height - 50

    def write(text: str, size: int = 11, gap: int = 18) -> None:
        nonlocal y
        c.setFont("Helvetica", size)
        c.drawString(50, y, text)
        y -= gap

    write("Test Candidate", size=16, gap=22)
    write("Senior Software Engineer", size=12, gap=20)
    write("test.candidate@example.com | +91 98765 43210", gap=16)
    write("linkedin.com/in/testcandidate | github.com/testcandidate", gap=16)
    write("Mumbai, Maharashtra, India", gap=24)

    write("Summary", size=13, gap=18)
    write("Experienced software engineer with 5+ years building scalable systems.", gap=20)

    write("Experience", size=13, gap=18)
    write("Software Engineer", gap=14)
    write("TechCorp India | Jan 2020 - Present", gap=14)
    write("Built microservices using Python and Kubernetes.", gap=14)
    write("Led a team of 5 engineers on the data platform.", gap=20)

    write("Junior Developer", gap=14)
    write("StartupXYZ | Jun 2018 - Dec 2019", gap=14)
    write("Developed React applications for internal tools.", gap=20)

    write("Education", size=13, gap=18)
    write("IIT Bombay", gap=14)
    write("B.Tech in Computer Science", gap=14)
    write("2018", gap=20)

    write("Skills", size=13, gap=18)
    write("Python, k8s, Docker, React, SQL, Git", gap=14)

    c.save()
    return pdf_path


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
