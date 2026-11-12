"""Shared navigation for create-project wizard browser tests."""


def finish_sections(page):
    """Tick every Customize / Toolkit section (as its own Next button would),
    since the wizard's Next stays off until they are all done."""
    page.evaluate("() => document.querySelectorAll('.ps-cz-sec:not(.is-done) .ps-cz-next').forEach(b => b.click())")


def next_step(page):
    finish_sections(page)
    page.click(".ps-next")
