from harbor.evac.household import Household, Pet, budget_lines, guide, rooms_needed

MARIA = Household(adults=2, children_ages=(7,), pets=(Pet("dog"),), evac_zone="A")
GSA_GAINESVILLE_MEALS = 6_800


def test_maria_budget_matches_the_api_example():
    lines = budget_lines(MARIA, days=3, nights=3, meals_rate_cents=GSA_GAINESVILLE_MEALS,
                         meals_source="gsa_per_diem_fy2025")
    assert [(l.label, l.amount_cents) for l in lines] == [
        ("Food and water: 2 adults + 1 child, 3 days", 56_100),
        ("Pets: dog, 3 nights (Harbor estimate)", 7_500),
        ("Supplies: kit, water, chargers (Harbor estimate)", 12_000),
    ]


def test_maria_guide():
    g = guide(MARIA)
    assert g.needs == ["everyone", "kids", "pets"]
    assert g.rooms == 1
    assert g.route.drives and g.route.rest_stop_every_hours == 2
    assert g.shelter_filter.pets and not g.shelter_filter.wheelchair
    assert {c.need for c in g.checklists} == {"everyone", "kids", "pets"}
    assert g.evacuation_reasons == ["ZONE_A"]
    assert any(c.kind == "pets" for c in g.advice)


def test_rooms_scale_with_people():
    assert rooms_needed(Household(adults=2, children_ages=(3, 6))) == 1
    assert rooms_needed(Household(adults=2, children_ages=(3, 6, 9))) == 2


def test_older_couple_without_a_car():
    g = guide(Household(adults=0, seniors=2, has_car=False, oxygen=True, mobility="walker"))
    assert not g.route.drives
    assert g.route.max_drive_hours_per_day == 6 and g.route.extra_leave_buffer_hours == 3
    assert g.route.prefer_regional_destination
    assert g.shelter_filter.ground_floor and g.shelter_filter.special_needs_shelter
    kinds = {c.kind for c in g.advice}
    assert {"no_car", "special_needs_shelter", "early_refill"} <= kinds
    medical = next(c for c in g.checklists if c.need == "medical")
    assert any("oxygen" in item for item in medical.items)


def test_dialysis_means_leave_early_and_plan_with_doctor():
    g = guide(Household(adults=1, dialysis=True))
    assert "POWER_OR_MEDICAL" in g.evacuation_reasons
    assert any(c.kind == "leave_early_medical" for c in g.advice)
    special = next(c for c in g.advice if c.kind == "special_needs_shelter")
    assert special.deadline_hours_before_landfall == 72


def test_mobile_home_always_evacuates_and_goes_regional():
    g = guide(Household(adults=1, home_type="mobile", evac_zone="none"))
    assert g.evacuation_reasons == ["MOBILE_HOME"]
    assert g.route.prefer_regional_destination


def test_infant_adds_supplies_and_needs_a_fridge():
    h = Household(adults=2, children_ages=(1,))
    supplies = budget_lines(h, days=2, nights=2, meals_rate_cents=6_800, meals_source="gsa")[-1]
    assert supplies.amount_cents == 3_000 + 1_000 * 3 * 2 + 1_500 * 2
    assert guide(h).shelter_filter.fridge
    assert "infants" in guide(h).needs


def test_every_checklist_cites_a_ready_gov_page():
    g = guide(Household(adults=1, seniors=1, children_ages=(0,), pets=(Pet("cat", 2),),
                        mobility="wheelchair", refrigerated_meds=True))
    assert all(c.source_url.startswith("https://www.ready.gov/") for c in g.checklists)
