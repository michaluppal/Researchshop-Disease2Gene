"""PMCID lookup must not depend on python-requests.

pmc.ncbi.nlm.nih.gov returns HTTP 403 to python-requests on Windows, which
made every selected paper look paywalled. These tests stay offline.
"""

import json

from modules import full_text_fetcher as ft


def test_id_converter_result_is_used(monkeypatch):
    monkeypatch.setattr(ft, "_pmcid_from_id_converter", lambda pmid: "PMC11131418")

    def fail(_pmid):
        raise AssertionError("Europe PMC should not run after a converter hit")

    monkeypatch.setattr(ft, "_pmcid_from_europepmc", fail)
    assert ft._get_pmcid_for_pmid("38807759") == "PMC11131418"


def test_converter_failure_falls_back_to_europepmc(monkeypatch):
    def boom(_pmid):
        raise OSError("HTTP Error 403: Forbidden")

    monkeypatch.setattr(ft, "_pmcid_from_id_converter", boom)
    monkeypatch.setattr(ft, "_pmcid_from_europepmc", lambda pmid: "PMC10519093")
    assert ft._get_pmcid_for_pmid("37743480") == "PMC10519093"


def test_europepmc_rejects_a_different_pmid(monkeypatch):
    monkeypatch.setattr(
        ft,
        "_read_json_url",
        lambda url, timeout=20: {"resultList": {"result": [{"pmid": "999", "pmcid": "PMC1"}]}},
    )
    assert ft._pmcid_from_europepmc("38807759") is None


def test_id_converter_reads_pmcid_field(monkeypatch):
    def fake_read(url, timeout=15):
        assert "idconv" in url
        assert "ids=38807759" in url
        return {"records": [{"pmid": "38807759", "pmcid": "PMC11131418"}]}

    monkeypatch.setattr(ft, "_read_json_url", fake_read)
    assert ft._pmcid_from_id_converter("38807759") == "PMC11131418"


def test_read_json_url_decodes_body(monkeypatch):
    class _Response:
        def read(self):
            return json.dumps({"ok": True}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(ft.urllib.request, "urlopen", lambda request, timeout=15: _Response())
    assert ft._read_json_url("https://example.test") == {"ok": True}
