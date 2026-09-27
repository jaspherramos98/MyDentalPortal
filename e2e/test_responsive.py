"""Key pages at desktop / iPad / phone: render, no sideways overflow, no JS errors."""
import pytest

from conftest import VIEWPORTS

PAGES = ["/dashboard", "/patients", "/appointments", "/reports", "/clinics", "/settings"]

# Which elements stick out past the viewport (so a failure says WHAT overflows).
OFFENDERS = """() => {
    const vw = document.documentElement.clientWidth;
    return [...document.querySelectorAll('body *')]
        .map(e => [e, e.getBoundingClientRect()])
        .filter(([e, r]) => r.width > 0 && r.right > vw + 1)
        .slice(0, 5)
        .map(([e, r]) => `${e.tagName}#${e.id}.${String(e.className).slice(0, 50)} right=${Math.round(r.right)}`);
}"""


@pytest.mark.parametrize("viewport", list(VIEWPORTS))
@pytest.mark.parametrize("role", ["admin", "staff"])
def test_pages_fit_the_screen(open_as, role, viewport, seeded):
    s = open_as(role, viewport=viewport)
    for path in PAGES + [f"/patients/{seeded['patient']['_id']}"]:
        resp = s.goto(path)
        assert resp.status == 200, path
        overflow = s.page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 1, (f"{path} scrolls sideways by {overflow}px at {viewport}: "
                               f"{s.page.evaluate(OFFENDERS)}")


@pytest.mark.parametrize("viewport", ["ipad", "phone"])
def test_navbar_collapses_and_opens_on_small_screens(open_as, viewport):
    s = open_as("admin", viewport=viewport)
    s.goto("/dashboard")
    toggler = s.page.locator("nav .navbar-toggler")
    if not toggler.is_visible():          # iPad landscape may show the full bar
        assert s.page.locator("nav .navbar-nav").first.is_visible()
        return
    toggler.click()
    s.page.locator("nav .navbar-collapse.show").wait_for()
