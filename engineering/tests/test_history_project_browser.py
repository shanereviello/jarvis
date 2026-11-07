"""Opt-in actual Chromium over signed ASGI fixtures; no listener or live Access.

RRAS_UI_BROWSER_TESTS=1 and a separately installed Playwright browser are required.
The application code, API, JWT verifier, scoped service and SQLite store are real;
only browser network transport is fulfilled in-process with synthetic signatures.
"""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_history_projects import projects, create, save, designate, assignment, submit, read, P1, P2, REPO, NON_GIT
from test_history_project_web import project_reader
from test_engineering_history_local import store, request
from test_history_web import web, key, access, client_call, ORIGIN

pytestmark = pytest.mark.skipif(os.environ.get('RRAS_UI_BROWSER_TESTS') != '1', reason='opt-in installed Chromium test')


def test_project_workspace_browser(projects, project_reader, key, tmp_path):
    playwright = pytest.importorskip('playwright.sync_api')
    save(projects, 2, '# Architecture\n\nRevised design.\n')
    baseline = submit(projects, 'baseline.record', dict(baseline_id='bas_' + '5' * 32, version=1,
        previous_sha256=None, commit='a' * 40, ref='main', label='Initial source', reason='Selected commit',
        source_reference=None, verified_at=None))['receipt']['effect']['baseline']
    submit(projects, 'baseline.select', dict(role='current', version=1,
        baseline_sha256=baseline['baseline_sha256'], reason='Selected reference'))
    create(projects, P2, NON_GIT)
    non_git = read(projects, P2, NON_GIT)
    metadata = {k: non_git[k] for k in ('revision','name','overview','intended_outcome','in_scope','out_of_scope','owner','change_summary')}
    metadata.update(revision=2, name='Non-Git planning')
    submit(projects, 'project.revise', metadata, P2, NON_GIT)
    extra = request(key='unassigned-browser')
    extra['body'].update(work_item_id='wrk_' + 'b' * 32, repository_id='jarvis', title='Unassigned browser work')
    projects.store.submit(extra)
    app = web('app').create_app(project_reader, access(key))
    unavailable = [False]
    signed_out = [False]
    errors = []
    with ThreadPoolExecutor(max_workers=1) as requests, playwright.sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        page.on('pageerror', lambda error: errors.append(str(error)))
        def fulfill(route):
            url = route.request.url
            path = url.removeprefix(ORIGIN)
            if signed_out[0] and path.startswith('/api/'):
                route.fulfill(status=403, body='Access unavailable.')
                return
            if unavailable[0] and path.startswith('/api/'):
                route.fulfill(status=503, body='History unavailable.')
                return
            if path.startswith('/cdn-cgi/access/logout'):
                signed_out[0] = True
                route.fulfill(status=200, body='Signed out')
                return
            response = requests.submit(client_call, app, key, path, route.request.method).result(timeout=12)
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
        page.route(ORIGIN + '/**', fulfill)
        page.goto(ORIGIN)
        playwright.expect(page.locator('#work-list .work-card')).to_have_count(2)
        page.select_option('#repository', 'repository:jarvis')
        playwright.expect(page.locator('#work-list .work-card')).to_have_count(1)
        page.locator('#work-list .work-card').click()
        page.get_by_role('tab', name='Architecture', exact=True).wait_for()
        if os.environ.get('RRAS_UI_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(os.environ['RRAS_UI_SCREENSHOT_DIR']) / 'project-workspace-synthetic-preview.png'), full_page=True)
        for tab in ('Overview', 'Work', 'Architecture', 'Baselines', 'History'):
            assert page.get_by_role('tab', name=tab, exact=True).count() == 1
            page.get_by_role('tab', name=tab, exact=True).click()
            playwright.expect(page.get_by_role('tab', name=tab, exact=True)).to_have_attribute('aria-selected', 'true')
            if tab == 'Work':
                playwright.expect(page.locator('#record-panel .doc-card')).to_have_count(1)
            elif tab == 'Architecture':
                page.get_by_role('button', name='Download exact Markdown', exact=True).wait_for()
            elif tab == 'Baselines':
                page.get_by_text('a' * 40, exact=True).wait_for()
            elif tab == 'History':
                playwright.expect(page.locator('#record-panel .record-card')).not_to_have_count(0)
            else:
                page.get_by_role('heading', name='Intended outcome', exact=True).wait_for()
            assert page.locator('#notice').is_hidden()
        page.get_by_role('tab', name='Architecture', exact=True).click()
        page.get_by_role('button', name='Download exact Markdown', exact=True).wait_for()
        assert page.locator('.document-source').first.inner_text() == '# Architecture\n\nOriginal design.\n'
        with page.expect_download() as saved:
            page.get_by_role('button', name='Download exact Markdown', exact=True).click()
        output = tmp_path / 'download.md'
        saved.value.save_as(output)
        assert output.read_text() == '# Architecture\n\nOriginal design.\n'
        page.get_by_label('Compare from version').select_option('1')
        page.get_by_label('Compare to version').select_option('2')
        page.get_by_role('button', name='Compare', exact=True).click()
        playwright.expect(page.locator('.compare-controls pre')).to_contain_text('+Revised design.')
        page.get_by_role('tab', name='Work', exact=True).click()
        page.locator('#record-panel .doc-card').click()
        page.get_by_role('tab', name='Timeline', exact=True).wait_for()
        assert page.get_by_role('tab', name='Evidence', exact=True).count() == 1
        page.get_by_role('button', name='← Back to project', exact=True).click()
        page.get_by_role('tab', name='Baselines', exact=True).click()
        page.get_by_text('a' * 40, exact=True).wait_for()
        page.select_option('#repository', 'non_git:jarvis-non-git')
        page.locator('#work-list .work-card').click()
        page.get_by_role('tab', name='Baselines', exact=True).click()
        page.get_by_text('Not applicable — non-Git project', exact=True).wait_for()
        page.select_option('#repository', 'repository:jarvis')
        page.select_option('#view', 'unassigned')
        page.get_by_role('heading', name='Unassigned browser work', exact=True).wait_for()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.locator('#view').is_visible()
        page.set_viewport_size({'width': 1440, 'height': 1100})
        page.locator('#work-list .work-card').click()
        page.get_by_role('tab', name='Overview', exact=True).wait_for()
        unavailable[0] = True
        page.get_by_role('button', name='Refresh', exact=True).click()
        playwright.expect(page.locator('#operator')).to_have_text('Access unavailable')
        assert 'Unassigned browser work' not in page.locator('#detail').inner_text()
        assert page.locator('#repository').is_disabled()
        unavailable[0] = False
        page.get_by_role('button', name='Refresh', exact=True).click()
        page.locator('#work-list').get_by_role('heading', name='Unassigned browser work', exact=True).wait_for()
        page.get_by_role('link', name='Sign out', exact=True).click()
        page.get_by_text('Signed out', exact=True).wait_for()
        page.goto(ORIGIN)
        playwright.expect(page.locator('#operator')).to_have_text('Access unavailable')
        assert 'Unassigned browser work' not in page.locator('#detail').inner_text()
        assert errors == []
        browser.close()
