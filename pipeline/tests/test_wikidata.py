from gully_pipeline.wikidata import team_for


def test_sporting_country_comes_first():
    assert team_for(["Afghanistan"], ["Afghanistan"]) == "Afghanistan"
    assert team_for(["Wales"], ["United Kingdom"]) == "England"
    assert team_for(["Scotland"], ["United Kingdom"]) == "Scotland"


def test_citizenship_fallback_and_team_names():
    assert team_for([], ["United Kingdom"]) == "England"
    assert team_for([], ["Jamaica"]) == "West Indies"
    assert team_for([], ["Kingdom of the Netherlands"]) == "Netherlands"
    assert team_for([], ["United States"]) == "United States of America"


def test_ambiguous_or_colonial_gives_nothing_or_the_modern_team():
    assert team_for([], ["South Africa", "United Kingdom"]) is None     # dual citizen, no sporting country
    assert team_for(["England"], ["South Africa", "United Kingdom"]) == "England"
    assert team_for([], ["British Raj"]) is None
    assert team_for([], ["British Raj", "India"]) == "India"
    assert team_for([], []) is None
