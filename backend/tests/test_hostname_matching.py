from backend.app import main
from backend.app.hostname_matching import hostname_matches_domain, parse_hostname, url_hostname_matches_any


def test_hostname_matches_domain_accepts_exact_domains_and_valid_subdomains():
    assert hostname_matches_domain("facebook.com", "facebook.com")
    assert hostname_matches_domain("WWW.FACEBOOK.COM.", "facebook.com")
    assert hostname_matches_domain("video.fb.watch", "fb.watch")


def test_hostname_matches_domain_rejects_lookalike_domains():
    assert not hostname_matches_domain("facebook.com.attacker.example", "facebook.com")
    assert not hostname_matches_domain("attackerfacebook.com", "facebook.com")
    assert not hostname_matches_domain("fb.watch.attacker.example", "fb.watch")


def test_url_hostname_matches_any_handles_ports_paths_queries_fragments_and_case():
    assert url_hostname_matches_any(
        "https://WWW.FACEBOOK.COM.:443/reel/123?foo=1#section",
        ("facebook.com", "fb.watch"),
    )
    assert url_hostname_matches_any(
        "https://SubDomain.Instagr.Am:8443/p/example/?utm_source=test#top",
        ("instagram.com", "instagr.am"),
    )


def test_url_hostname_matches_any_rejects_malformed_and_lookalike_urls():
    assert parse_hostname("not-a-url") == ""
    assert not url_hostname_matches_any("not-a-url", ("facebook.com",))
    assert not url_hostname_matches_any("https://facebook.com.attacker.example/reel/123", ("facebook.com",))
    assert not url_hostname_matches_any("https://attackerfacebook.com/share/abc", ("facebook.com",))


def test_source_detection_uses_parsed_hostnames():
    assert main.infer_source("https://www.facebook.com./reel/123?foo=1#bar") == ("Facebook", "Facebook")
    assert main.infer_source("https://ATTACKERFACEBOOK.COM/reel/123") == ("Browser", "Web")
    assert main._detect_submission_source_type("https://sub.instagr.am/p/abc/") == "instagram"
    assert main._detect_submission_source_type("https://instagram.com.attacker.example/p/abc/") == "normal"
