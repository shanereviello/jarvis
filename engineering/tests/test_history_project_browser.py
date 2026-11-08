"""Opt-in actual Chromium over signed ASGI fixtures; no listener or live Access.

RRAS_UI_BROWSER_TESTS=1 and a separately installed Playwright browser are required.
The application code, API, JWT verifier, scoped service and SQLite store are real;
only browser network transport is fulfilled in-process with synthetic signatures.
"""
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_history_projects import projects, create, save, designate, assignment, submit, read, state, P1, P2, REPO, NON_GIT
from test_history_project_web import project_reader
from test_engineering_history_local import store, request, module
from test_history_web import web, key, access, client_call, ORIGIN

pytestmark = pytest.mark.skipif(os.environ.get('RRAS_UI_BROWSER_TESTS') != '1', reason='opt-in installed Chromium test')


def test_reporting_reference_and_verified_private_capture_browser(projects,project_reader,key,tmp_path):
    import json
    from test_history_reporting import request as report_request
    from test_history_evidence import upload,manifest
    playwright=pytest.importorskip('playwright.sync_api')
    reporting=module('reporting').Reporting(projects.store);reporting.migrate(reporting.migration_plan()['expected_sha256'])
    evidence=module('evidence').Evidence(projects.store);evidence.migrate(evidence.migration_plan()['expected_sha256'])
    reporting.submit(report_request(projects,project_mapping=True));reporting.submit(report_request(projects))
    checkpoint=report_request(projects,'checkpoint.report')
    checkpoint['body']['observations']=['BROWSER-REFERENCE-FINDING <img src=x onerror="window.injected=true">']
    reporting.submit(checkpoint)
    reporting.submit(report_request(projects,'attempt.record'))
    raw='VISIBLE-CAPTURE-RESULT\n<img src=x onerror="window.injected=true">\nUnicode: Ω\n'.encode()
    evidence.upload(upload(raw));capture=manifest(projects,raw);reporting.submit(capture)
    unmapped=manifest(projects,b'',context=False);unmapped['body']['artifact_id']='cap_'+'9'*32;reporting.submit(unmapped)
    app=web('app').create_app(project_reader,access(key));errors=[];corrupt=[False]
    with ThreadPoolExecutor(max_workers=1) as requests,playwright.sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1100})
        page.on('pageerror',lambda error:errors.append(str(error)))
        def fulfill(route):
            path=route.request.url.removeprefix(ORIGIN)
            response=requests.submit(client_call,app,key,path,route.request.method).result(timeout=12)
            body=response.content
            if corrupt[0] and path.startswith('/api/workspace/artifact') and 'index=' in path:
                value=response.json();value['chunk']['data_base64']='Y29ycnVwdA=='
                body=json.dumps(value).encode()
            route.fulfill(status=response.status_code,headers=dict(response.headers),body=body)
        page.route(ORIGIN+'/**',fulfill);page.goto(ORIGIN)
        page.locator('#work-list .work-card').click()
        page.get_by_role('heading',name='Engineering reporting',exact=True).wait_for()
        playwright.expect(page.locator('#detail')).to_contain_text('BROWSER-REFERENCE-FINDING')
        page.get_by_role('tab',name='Work',exact=True).click()
        page.locator('#detail .doc-card').click()
        page.get_by_role('tab',name='Timeline',exact=True).click()
        playwright.expect(page.locator('#detail')).to_contain_text('BROWSER-REFERENCE-FINDING')
        assert page.locator('#detail img').count()==0
        page.get_by_role('tab',name='Evidence',exact=True).click()
        page.get_by_role('button',name='Inspect captured evidence v1',exact=True).click()
        page.get_by_role('heading',name='Captured engineering evidence',exact=True).wait_for()
        page.get_by_role('button',name='Preview captured text',exact=True).click()
        playwright.expect(page.locator('#detail pre')).to_contain_text('VISIBLE-CAPTURE-RESULT')
        playwright.expect(page.locator('#detail')).to_contain_text('Exact full artifact verified')
        assert page.evaluate('window.injected') is None and page.locator('#detail img').count()==0
        with page.expect_download() as download:
            page.get_by_role('button',name='Download verified full export',exact=True).click()
        path=tmp_path/'capture.md';download.value.save_as(path);assert path.read_bytes()==raw
        corrupt[0]=True;page.get_by_role('button',name='Preview captured text',exact=True).click()
        playwright.expect(page.locator('#notice')).to_contain_text('could not be read or verified')
        assert 'VISIBLE-CAPTURE-RESULT' not in page.locator('#detail').inner_text()
        corrupt[0]=False;page.get_by_role('button',name='Refresh',exact=True).click()
        page.select_option('#repository','repository:jarvis')
        page.get_by_role('button',name='Scope details and history',exact=True).click()
        page.get_by_role('heading',name='Unmapped captured evidence',exact=True).wait_for()
        playwright.expect(page.locator('#detail')).to_contain_text('Unmapped; explicit association required')
        browser.close()
    assert not errors


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
    old = projects.read(REPO, {'view': 'work', 'work_id': 'wrk_' + '1' * 32})
    head = old['work_revision_sha256']
    projects.store.submit(request('outcome.record', 'browser-v1-outcome', head, dict(work_item_id='wrk_' + '1' * 32,
        work_revision_sha256=head, outcome='completed_claim', summary='Reported original scope complete', references=[])))
    revised = dict(old['work'], revision=2)
    projects.store.submit(request('work.revise', 'browser-v2-scope', head, revised))
    state(projects, 'completed', [{'work_item_id': 'wrk_' + '1' * 32, 'disposition': 'deferred', 'reason': 'Explicit fixture disposition'}])
    closeout = read(projects)['closeouts'][0]
    state(projects, 'active')
    from test_history_scopes import envelope
    registry = module('scopes').Scopes(projects.store)
    scope_head = projects.read(REPO, {'view': 'scope'})['metadata']['head']
    registry.submit(envelope(revision=2, head=scope_head, name='Jarvis engineering'))
    repositories = ['jarvis', 'robot_ws', 'tooling_repo']
    for index, repo in enumerate(repositories[1:], 3):
        selected = {'kind': 'repository', 'id': repo}
        registry.submit(envelope(selected, name='Repository display name'))
        create(projects, 'prj_' + str(index) * 32, selected)
    service = module('access').Access(projects.store, dict(contract='engineering-history-access.v2',
        principals=[dict(uid=1000, private_read=repositories, write=[], category_read=['jarvis-non-git'], category_write=[])]))
    contract = module('contract')
    def call(message):
        return contract.decode(contract.encoded(service.dispatch(1000, message)), max_bytes=2 * 1024 * 1024)
    reader = web('history').Reader(repositories, call, ['jarvis-non-git'])
    app = web('app').create_app(reader, access(key))
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
        playwright.expect(page.locator('#work-list .work-card')).to_have_count(4)
        assert page.locator('#repository optgroup[label="Other repositories"] option').get_attribute('value') == 'repository:tooling_repo'
        for repo in ('robot_ws', 'tooling_repo'):
            page.select_option('#repository', 'repository:' + repo)
            playwright.expect(page.locator('#work-list .work-card')).to_have_count(1)
            page.locator('#work-list .work-card').click()
            playwright.expect(page.locator('#breadcrumb')).to_contain_text(repo)
        page.select_option('#repository', 'repository:jarvis')
        playwright.expect(page.locator('#work-list .work-card')).to_have_count(1)
        page.get_by_role('button', name='Scope details and history', exact=True).click()
        page.get_by_role('heading', name='Jarvis engineering', exact=True).wait_for()
        page.get_by_role('heading', name='Scope revision history', exact=True).wait_for()
        page.get_by_role('button', name='View scope revision 1', exact=True).click()
        page.get_by_role('heading', name='Jarvis display name', exact=True).wait_for()
        page.locator('#work-list .work-card').click()
        page.get_by_role('tab', name='Architecture', exact=True).wait_for()
        if os.environ.get('RRAS_UI_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(os.environ['RRAS_UI_SCREENSHOT_DIR']) / 'project-workspace-synthetic-preview.png'), full_page=True)
        for tab in ('Overview', 'Work', 'Architecture', 'Baselines', 'History'):
            playwright.expect(page.get_by_role('tab', name=tab, exact=True)).to_have_count(1)
            page.get_by_role('tab', name=tab, exact=True).click()
            playwright.expect(page.get_by_role('tab', name=tab, exact=True)).to_have_attribute('aria-selected', 'true')
            if tab == 'Work':
                playwright.expect(page.locator('#record-panel .doc-card')).to_have_count(1)
                playwright.expect(page.locator('#record-panel')).to_contain_text('Last recorded activity')
                playwright.expect(page.locator('#record-panel')).to_contain_text('Outcome for scope revision 1 · Earlier scope revision')
            elif tab == 'Architecture':
                page.get_by_role('button', name='Download exact Markdown', exact=True).wait_for()
                page.get_by_role('heading', name='Governing designation history', exact=True).wait_for()
                playwright.expect(page.locator('#record-panel')).to_contain_text('Submitting principal')
            elif tab == 'Baselines':
                page.get_by_text('a' * 40, exact=True).wait_for()
            elif tab == 'History':
                playwright.expect(page.locator('#record-panel .record-card')).not_to_have_count(0)
            else:
                page.get_by_role('heading', name='Intended outcome', exact=True).wait_for()
                page.get_by_role('heading', name='Reported outcomes · current scope', exact=True).wait_for()
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
        page.get_by_role('tab', name='Overview', exact=True).click()
        page.get_by_role('button', name='Inspect closeout #' + str(closeout['sequence']), exact=True).click()
        playwright.expect(page.locator('.snapshot-note')).to_contain_text('At closeout on')
        assert 'Not recorded' not in page.locator('.snapshot-note').inner_text()
        playwright.expect(page.locator('#breadcrumb')).to_contain_text('Jarvis display name')
        page.get_by_role('tab', name='Work', exact=True).click()
        playwright.expect(page.locator('#record-panel .doc-card')).to_have_count(1)
        page.get_by_role('button', name='Return to current project', exact=True).click()
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
