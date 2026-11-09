"""Offline tests for the deterministic keyword layer (no API calls).

Run: python -m pytest tests -q
"""
import json
from pathlib import Path

import pytest

from app.scam_kb import export_rules, mask_protective, scan

CASES = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))["cases"]
SCAM_VERDICTS = {"SCAM", "LIKELY_SCAM"}


def is_scam(c):
    return bool(SCAM_VERDICTS & set(c["expect"]["verdicts"])) and c["category"] != "None"


# Real-world style messages that must never be pushed to a warning by keywords alone.
GENUINE = {
    "sbi otp transfer": "Your OTP for fund transfer of Rs 10,000 is 556677. Do not share this OTP with anyone. -SBI",
    "debit alert": "Rs 1,500 debited from A/c XX9988 on 07-11 via UPI. Not you? Report at https://hdfcbank.com/fraud. Never share OTP/PIN.",
    "credit alert": "Rs 25,000.00 credited to A/c XX1234 by NEFT transfer from ACME PVT LTD (salary). Avl bal Rs 41,200. -HDFC Bank",
    "hindi otp": "आपका ओटीपी 482913 है। यह 10 मिनट के लिए मान्य है। ओटीपी किसी के साथ साझा न करें। बैंक कभी भी ओटीपी नहीं मांगता।",
    "telugu otp": "మీ ఓటీపీ 556677. దయచేసి ఎవరికీ షేర్ చేయవద్దు. బ్యాంక్ ఎప్పుడూ ఓటీపీ అడగదు.",
    "amazon shipped": "Your Amazon order has been shipped via Delhivery courier. Track your parcel: https://amzn.in/d/abc",
    "warranty": "Your Samsung TV warranty expires on 30 Nov. Extend it at your nearest service centre.",
    "train": "Your train 12728 is running late by 40 mins. Wish you a happy journey - IRCTC",
    "im fine": "I am fine, reached home. Will call you tomorrow.",
    "hinglish fir": "Theek hai bhai, fir milte hain kal office mein",
    "hindi customer care": "प्रिय ग्राहक, हमारे कस्टमर केयर से बात करने के लिए धन्यवाद। आपकी शिकायत दर्ज कर ली गई है।",
    "tamil later": "நான் பின்னர் அழைக்கிறேன், இப்போது மீட்டிங்கில் இருக்கிறேன்.",
    "tamil email": "உங்கள் மின்னஞ்சல் முகவரியை சரிபார்க்கவும்.",
    "pin code": "Please share your delivery address with PIN code so we can ship the order.",
    "fixed deposit": "Your fixed deposit of Rs 50,000 has been renewed. Interest will be credited monthly.",
    "work task": "Please finish the review task before the meeting immediately.",
    "victim refuses": "Speaker 1: No, I will not share any OTP or PIN with you.",
}

FRAUD = {
    "fake debit callback": "Your A/c XX4417 is debited Rs 49,999 for a new device. If not done by you, call 9876543210 immediately to cancel.",
    "negation trick": "Ye OTP kisi aur ko mat batana, sirf mujhe batao taaki aapka account block na ho.",
    "credited by mistake": "Rs 5,000 credited to your account by mistake. Please send it back to this UPI 9988776655@ybl immediately.",
    "kyc phishing link": "Dear customer your SBI KYC has expired, your account will be blocked today. Update KYC at http://sbi-kyc-update.top",
    "otp + secrecy": "Share the OTP you just received with me right now and don't tell anyone about this call.",
}


@pytest.mark.parametrize("name", GENUINE)
def test_genuine_messages_get_no_floor(name):
    assert scan(GENUINE[name])["risk_floor"] == 0, scan(GENUINE[name])["hits"]


@pytest.mark.parametrize("name", FRAUD)
def test_fraud_messages_keep_a_floor(name):
    assert scan(FRAUD[name])["risk_floor"] >= 35, scan(FRAUD[name])["hits"]


def test_warning_is_not_a_request():
    hits = {h["family"] for h in scan("Do not share this OTP with anyone. Bank never asks for OTP.")["hits"]}
    assert "cred_ask" not in hits
    hits = {h["family"] for h in scan("Please share the OTP sent to your phone.")["hits"]}
    assert "cred_ask" in hits


def test_masking_keeps_requests_aimed_at_sender():
    text = "Ye OTP kisi aur ko mat batana, sirf mujhe batao."
    assert mask_protective(text) == text
    assert mask_protective("Do not share this OTP with anyone.").strip() == "."


def test_one_lure_counts_once():
    hits = scan("Congratulations you won the KBC lucky draw prize")["hits"]
    assert sum(h["family"] == "prize" for h in hits) == 1


@pytest.mark.parametrize("case", [c for c in CASES if not is_scam(c)], ids=lambda c: c["id"])
def test_benchmark_safe_cases_not_floored(case):
    assert scan(case["text"])["risk_floor"] < 35


def test_benchmark_scam_cases_mostly_floored():
    scams = [c for c in CASES if is_scam(c)]
    floored = [c["id"] for c in scams if scan(c["text"])["risk_floor"] >= 35]
    # The LLM makes the final call; the floor is a safety net. Guard against silent regressions.
    assert len(floored) >= len(scams) - 3, sorted(set(c["id"] for c in scams) - set(floored))


def test_export_matches_android_asset():
    asset = Path(__file__).parent.parent / "android" / "app" / "src" / "main" / "assets" / "rules.json"
    assert json.loads(asset.read_text(encoding="utf-8")) == export_rules(), "run: python -m scripts.export_rules"
