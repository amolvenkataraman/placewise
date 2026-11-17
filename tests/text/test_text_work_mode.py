# ruff: noqa: E501  (the cases are verbatim sentences)
"""Remote / hybrid / onsite from a description, a source's own value, or a location string.

Descriptions are real-world sentences with organisation names replaced by "Acme"."""

import pytest

from placewise.text import detect_work_mode, structured_work_mode

# (description, location hint, structured value, expected)
CASES = [
    ("This role is remote, but distance is no barrier to impact. Our hybrid teams collaborate across geographies.", "", None, "remote"),
    ("This role has been designated as ‘Remote/Teleworker’, which means you will primarily work from home.", "", None, "remote"),
    ("Acme is a remote-first, but not remote-only company. Expect to get together quarterly.", "", None, "remote"),
    ("This position is currently remote but may eventually report to an office in Philadelphia.", "", None, "remote"),
    ("This role can be based in San Francisco or London, or fully remote.", "", None, "remote"),
    ("Ability to work remotely from the United States or Canada.", "", None, "remote"),
    ("Great benefits. #LI-Remote", "", None, "remote"),
    ("Remote Work &amp; Territory Alignment: This is a remote position aligned to a specific territory.", "", None, "remote"),
    ("Build our platform.", "Remote, US", None, "remote"),
    ("Prior experience with remote sensing systems and remote access tooling.", "", None, None),
    ("Notice to Applicants for Positions Located in NYC or Remote Positions Associated With Office in NYC Only.", "", None, None),
    ("Ability to communicate with remote teams across time zones.", "", None, None),
    ("If the role can be performed remote, the recruiter can share the salary range.", "", None, None),
    ("This is an onsite position at our HQ in San Diego, CA. Hybrid or remote options will not be available for this position.", "", None, "onsite"),
    ("Must be willing to relocate to Bastrop, TX. Remote or hybrid work not considered.", "", None, "onsite"),
    ("This is not a remote position. The primary work location is in Arlington, Texas.", "", None, "onsite"),
    ("All internships are hybrid; fully remote roles are not offered.", "", None, "hybrid"),
    ("This is not a remote position. Acme is a hybrid work environment requiring work in the office three (3) days per week.", "", None, "hybrid"),
    ("This role has been designed as 'Hybrid' with a requirement that you will work on average 2 days per week from an Acme office.", "", None, "hybrid"),
    ("Candidates must be local to Milpitas as this hybrid role requires being in office there at least 3 days each week.", "", None, "hybrid"),
    ("Acme employees are expected to work from a designated Acme office at least four days a week.", "", None, "hybrid"),
    ("Candidate must be local San Jose, CA and come into the office 2-3 days a week.", "", None, "hybrid"),
    ("40 hrs/week 50% Telecommuting Permitted.", "", None, "hybrid"),
    ("Note: This will be a hybrid onsite internship position.", "", None, "hybrid"),
    ("This role will be in-office on a hybrid schedule &mdash; Team Members work in the office 3 days per week.", "", None, "hybrid"),
    ("Roles that are based in an office are onsite Tuesday, Wednesday, and Thursday.", "", None, "hybrid"),
    ("Work Location HYBRID: Some of a team member’s work may be best done elsewhere.", "", None, "hybrid"),
    ("Junior AI/ML Engineer Location: Herndon, VA (Hybrid Work)", "", None, "hybrid"),
    ("Experience in a technical design or similar hybrid role where you built gameplay.", "", None, None),
    ("Knowledge of TSVs, hybrid bonding, and 3D integration.", "", None, None),
    ("Experience with ASR (end-to-end or hybrid CTC/attention architectures).", "", None, None),
    ("Experience working with cloud, hybrid, or on-premises platforms.", "", None, None),
    ("Work Model for this Role This role will require an on-site presence.", "", None, "onsite"),
    ("Position Role Type: Onsite U.S. Citizen, U.S. Person, or Immigration Status Requirements apply.", "", None, "onsite"),
    ("Location: 100% Onsite In Texas or Georgia", "", None, "onsite"),
    ("Able to work full-time, on-site for a minimum of 12 consecutive weeks.", "", None, "onsite"),
    ("All positions at Acme Semiconductor are full-time on-site.", "", None, "onsite"),
    ("Ability to perform work onsite at Smyrna, TN.", "", None, "onsite"),
    ("Location: Dublin, Ireland (onsite)", "", None, "onsite"),
    ("Work model Boise, ID, Main Site. Schedule is 5 days onsite.", "", None, "onsite"),
    ("We have the requirement for all staff to work on-site five days a week.", "", None, "onsite"),
    ("Internship program: 12 - 24 weeks, full-time, in-person in the Berlin office.", "", None, "onsite"),
    ("Design Engineer Intern Acme · San Jose, CA · Internship · On-site", "", None, "onsite"),
    ("Benefits include onsite lunch, an onsite gym and in-office perks.", "", None, None),
    ("Some travel may be required for complex cases that require on-site support.", "", None, None),
    ("This is a hybrid role in our London office.", "", "Remote", "remote"),
    ("Fully remote.", "", "OnSite", "onsite"),
    ("Fully remote.", "", "unspecified", "remote"),
    ("", "", "hybrid", "hybrid"),
    ("", "Hybrid - New York, NY", None, "hybrid"),
    ("Our office is great.", "Seattle, WA", None, None),
]  # fmt: skip


@pytest.mark.parametrize(("text", "hint", "structured", "expected"), CASES, ids=lambda v: str(v)[:40])
def test_detect_work_mode(text, hint, structured, expected):
    assert detect_work_mode(text, location_hint=hint, structured=structured) == expected


def test_html_and_entities_are_read_as_text():
    html = "<p>This role will be in-office on a hybrid schedule&period;</p>"
    assert detect_work_mode(html) == "hybrid"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("OnSite", "onsite"),
        ("onsite", "onsite"),
        ("On-site", "onsite"),
        ("Remote", "remote"),
        (True, "remote"),
        ("Hybrid", "hybrid"),
        ("unspecified", None),
        (None, None),
        (False, None),
        # more spellings
        ("Fully Remote", "remote"),
        ("telecommute", "remote"),
        ("Work from home", "remote"),
        ("virtual", "remote"),
        ("flexible", "hybrid"),
        ("in_office", "onsite"),
        ("In Person", "onsite"),
        ("office", "onsite"),
        # snake case
        ("remote_local", "remote"),
        ("on_site", "onsite"),
        # upper case
        ("ON_SITE", "onsite"),
        ("REMOTE", "remote"),
        ("HYBRID", "hybrid"),
    ],
)
def test_structured_work_mode(value, expected):
    assert structured_work_mode(value) == expected
